# backend/routers/analytics.py

from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from datetime import datetime, timedelta
# Импортируем нашу функцию расчета
from analysis_service import analysis_service
from services.supply import supply_service
# Импорт зависимостей БД (примерный)
from database import get_db, User, get_current_user 
from sqlalchemy import text # Или использование ORM
from wb_api.statistics import WBStatisticsAPI

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

@router.get("/abc-xyz")
async def get_abc_xyz_stats(
    days: int = Query(30, ge=7, le=365),
    user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """
    Эндпоинт для получения матрицы ABC/XYZ.
    """
    # 1. Определяем диапазон дат
    date_from = datetime.now() - timedelta(days=days)
    
    # 2. SQL запрос для получения "сырых" данных: SKU, Дата, Выручка, Штуки
    # Группируем по дням, чтобы XYZ мог посчитать стабильность спроса
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
    
    # Выполняем запрос (синтаксис зависит от вашей ORM/Драйвера, здесь пример для SQLAlchemy)
    try:
        result = await db.execute(query, {"uid": user.id, "date_from": date_from})
        raw_data = [dict(row) for row in result.mappings().all()]
    except Exception as e:
        # Если данных нет или ошибка БД, можно вернуть пустой список для теста
        print(f"DB Error: {e}")
        raw_data = [] 

    # 3. Передаем данные в наш калькулятор
    # calculate_abc_xyz ожидает List[dict] с ключами: sku, date, revenue, qty
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
    
    # Вызываем метод из EconomicsModule (через фасад analysis_service)
    # Нужно убедиться, что метод добавлен в analysis_service.py как прокси
    # Либо вызывать напрямую: analysis_service.economics.get_return_forensics
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
        return {"status": "error", "message": "No WB Token"}

    # 1. Получаем настройки поставок
    settings_res = await db.execute(select("SupplySettings").where("user_id" == user.id)) # Псевдокод, используйте реальную модель
    # (Упрощение: используем дефолты, если нет настроек)
    config = {"lead_time": 7, "min_stock_days": 14, "abc_a_share": 80}

    # 2. Получаем данные остатков и заказов (через сервис Supply)
    wb_api = WBStatisticsAPI(user.wb_api_token)
    turnover_data = await wb_api.get_turnover_data()
    
    # 3. Рассчитываем Supply Metrics (чтобы знать velocity и ROP)
    supply_analysis = supply_service.analyze_supply(
        turnover_data.get("stocks", []), 
        turnover_data.get("orders", []), 
        config
    )

    # 4. Получаем себестоимость из БД
    skus = [i['sku'] for i in supply_analysis]
    stmt = select(ProductCost).where(ProductCost.user_id == user.id, ProductCost.sku.in_(skus))
    costs = (await db.execute(stmt)).scalars().all()
    costs_map = {c.sku: c.cost_price for c in costs}

    # 5. Считаем разрывы
    result = supply_service.calculate_cash_gap(supply_analysis, costs_map)
    return result