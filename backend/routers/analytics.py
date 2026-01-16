from fastapi import APIRouter, Depends, Query, HTTPException
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

# Импортируем сервис и модели
from analysis_service import analysis_service
from services.supply import supply_service
from database import get_db, User, ProductCost, SupplySettings
from dependencies import get_current_user
from wb_api.statistics import WBStatisticsAPI

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

@router.get("/abc-xyz")
async def get_abc_xyz_stats(
    days: int = Query(30, ge=7, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Эндпоинт для получения матрицы ABC/XYZ.
    """
    date_from = datetime.now() - timedelta(days=days)
    
    # SQL для получения агрегированных данных
    # Используем text() для сырого SQL, так как это агрегация
    query = text("""
        SELECT 
            sku, 
            date(created_at) as date, 
            SUM(price_final) as revenue, 
            SUM(quantity) as qty
        FROM orders
        WHERE user_id = :uid 
          AND created_at >= :date_from
        GROUP BY sku, date(created_at)
    """)
    
    try:
        result = await db.execute(query, {"uid": user.id, "date_from": date_from})
        raw_data = [dict(row) for row in result.mappings().all()]
    except Exception as e:
        print(f"DB Error: {e}")
        raw_data = [] 

    # Вызываем метод через инстанс сервиса
    analysis_result = analysis_service.economics.calculate_abc_xyz(raw_data)
    
    return analysis_result

@router.get("/forensics/returns")
async def get_return_forensics_endpoint(
    days: int = Query(30, ge=7, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    4.3 Получение данных по проблемным возвратам (размеры, склады).
    """
    date_to = datetime.now()
    date_from = date_to - timedelta(days=days)
    
    # Обращаемся к ClickHouse через сервис
    # Если ClickHouse недоступен (ошибка пароля), метод вернет пустые списки или ошибку
    data = await analysis_service.economics.get_return_forensics(user.id, date_from, date_to)
    return data

@router.get("/finance/cash-gap")
async def get_cash_gap_forecast(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    4.4 Прогноз кассовых разрывов на основе Supply Chain.
    """
    if not user.wb_api_token:
        raise HTTPException(status_code=400, detail="WB API Token required")

    # 1. Получаем настройки поставок из БД (ИСПРАВЛЕНО)
    stmt = select(SupplySettings).where(SupplySettings.user_id == user.id)
    settings_res = await db.execute(stmt)
    settings = settings_res.scalars().first()
    
    # Используем настройки или дефолтные значения
    config = {
        "lead_time": settings.lead_time if settings else 7,
        "min_stock_days": settings.min_stock_days if settings else 14,
        "abc_a_share": settings.abc_a_share if settings else 80
    }

    # 2. Получаем данные остатков и заказов (через сервис Supply)
    # Создаем экземпляр API с токеном пользователя
    wb_api = WBStatisticsAPI(user.wb_api_token)
    try:
        turnover_data = await wb_api.get_turnover_data()
    except Exception as e:
        # Если ошибка API WB, возвращаем пустой результат, чтобы фронт не падал
        print(f"WB API Error: {e}")
        return {"total_needed_soon": 0, "nearest_gap_date": None, "timeline": []}

    stocks = turnover_data.get("stocks", [])
    orders = turnover_data.get("orders", [])
    
    # 3. Рассчитываем Supply Metrics (чтобы знать velocity и ROP)
    supply_analysis = supply_service.analyze_supply(stocks, orders, config)

    # 4. Получаем себестоимость из БД
    if not supply_analysis:
        return {"total_needed_soon": 0, "nearest_gap_date": None, "timeline": []}

    skus = [i['sku'] for i in supply_analysis]
    
    # Загружаем себестоимость товаров
    costs_stmt = select(ProductCost).where(
        ProductCost.user_id == user.id, 
        ProductCost.sku.in_(skus)
    )
    costs_res = await db.execute(costs_stmt)
    costs = costs_res.scalars().all()
    costs_map = {c.sku: c.cost_price for c in costs}

    # 5. Считаем разрывы
    result = supply_service.calculate_cash_gap(supply_analysis, costs_map)
    return result