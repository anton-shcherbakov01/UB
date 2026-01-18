from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
import io
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Импортируем сервис и модели
from analysis_service import analysis_service
from services.supply import supply_service
from database import get_db, User, ProductCost, SupplySettings
from dependencies import get_current_user
from wb_api.statistics import WBStatisticsAPI
from config.plans import get_limit

# Note: Frontend seems to be requesting /api/finance for reports based on logs.
# Ensure this router is mounted correctly or frontend requests are updated.
router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

executor = ThreadPoolExecutor(max_workers=2)

@router.get("/abc-xyz")
async def get_abc_xyz_stats(
    days: int = Query(30, ge=7, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Эндпоинт для получения матрицы ABC/XYZ.
    Проверяет лимит history_days по тарифу.
    """
    # Получаем лимит истории для текущего тарифа
    history_limit = get_limit(user.subscription_plan, "history_days")
    if days > history_limit:
        from config.plans import get_plan_config
        plan_config = get_plan_config(user.subscription_plan)
        raise HTTPException(
            status_code=403,
            detail=f"Период {days} дней недоступен на вашем тарифе. Доступно: {history_limit} дней. Текущий план: {plan_config.get('name', user.subscription_plan)}"
        )
    
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
    Требует feature 'forensics' (analyst, strategist планы).
    """
    from config.plans import has_feature, get_plan_config
    
    if not has_feature(user.subscription_plan, "forensics"):
        plan_config = get_plan_config(user.subscription_plan)
        raise HTTPException(
            status_code=403,
            detail=f"Форензика возвратов доступна только на тарифе Аналитик или выше. Текущий план: {plan_config.get('name', user.subscription_plan)}"
        )
    
    # Проверяем лимит истории
    history_limit = get_limit(user.subscription_plan, "history_days")
    if days > history_limit:
        raise HTTPException(
            status_code=403,
            detail=f"Период {days} дней недоступен на вашем тарифе. Доступно: {history_limit} дней."
        )
    
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
    Требует feature 'forensics_cashgap' (только strategist план).
    """
    from config.plans import has_feature, get_plan_config
    
    if not has_feature(user.subscription_plan, "forensics_cashgap"):
        plan_config = get_plan_config(user.subscription_plan)
        raise HTTPException(
            status_code=403,
            detail=f"Cash Gap анализ доступен только на тарифе Стратег. Текущий план: {plan_config.get('name', user.subscription_plan)}"
        )
    
    if not user.wb_api_token:
        raise HTTPException(status_code=400, detail="WB API Token required")

    # 1. Получаем настройки поставок из БД
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

@router.get("/report/forensics-pdf")
async def generate_forensics_pdf(
    days: int = Query(30, ge=7, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Generate Forensics PDF report"""
    from config.plans import has_feature, get_plan_config
    
    if not has_feature(user.subscription_plan, "forensics"):
        plan_config = get_plan_config(user.subscription_plan)
        raise HTTPException(
            status_code=403,
            detail=f"Форензика возвратов доступна только на тарифе Аналитик или выше. Текущий план: {plan_config.get('name', user.subscription_plan)}"
        )
    
    date_to = datetime.now()
    date_from = date_to - timedelta(days=days)
    
    # Get forensics data
    forensics_data = await analysis_service.economics.get_return_forensics(user.id, date_from, date_to)
    
    # Generate PDF in executor
    from services.pdf_generator import pdf_generator
    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(
        executor,
        pdf_generator.create_forensics_pdf,
        forensics_data
    )
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="forensics_report_{days}days.pdf"'}
    )

@router.get("/report/cashgap-pdf")
async def generate_cashgap_pdf(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Generate Cash Gap PDF report"""
    from config.plans import has_feature, get_plan_config
    
    if not has_feature(user.subscription_plan, "forensics_cashgap"):
        plan_config = get_plan_config(user.subscription_plan)
        raise HTTPException(
            status_code=403,
            detail=f"Cash Gap анализ доступен только на тарифе Стратег. Текущий план: {plan_config.get('name', user.subscription_plan)}"
        )
    
    # Get cash gap data (same logic as get_cash_gap_forecast)
    if not user.wb_api_token:
        raise HTTPException(status_code=400, detail="WB API Token required")
    
    # Reuse the logic from get_cash_gap_forecast
    # NOTE: Code duplication kept to preserve file structure/integrity as requested
    
    stmt = select(SupplySettings).where(SupplySettings.user_id == user.id)
    settings_res = await db.execute(stmt)
    settings = settings_res.scalars().first()
    
    config = {
        "lead_time": settings.lead_time if settings else 7,
        "min_stock_days": settings.min_stock_days if settings else 14,
        "abc_a_share": settings.abc_a_share if settings else 80
    }
    
    wb_api = WBStatisticsAPI(user.wb_api_token)
    try:
        turnover_data = await wb_api.get_turnover_data()
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
    stocks = turnover_data.get("stocks", [])
    orders = turnover_data.get("orders", [])
    supply_analysis = supply_service.analyze_supply(stocks, orders, config)
    
    if not supply_analysis:
        # Return a generated PDF saying no data instead of JSON error
        # to ensure the user gets a file
        cashgap_data = {"status": "empty", "message": "Нет данных для анализа"}
    else:
        skus = [i['sku'] for i in supply_analysis]
        costs_stmt = select(ProductCost).where(
            ProductCost.user_id == user.id, 
            ProductCost.sku.in_(skus)
        )
        costs_res = await db.execute(costs_stmt)
        costs = costs_res.scalars().all()
        costs_map = {c.sku: c.cost_price for c in costs}
        
        cashgap_data = supply_service.calculate_cash_gap(supply_analysis, costs_map)
    
    # Generate PDF in executor
    from services.pdf_generator import pdf_generator
    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(
        executor,
        pdf_generator.create_cashgap_pdf,
        cashgap_data
    )
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type='application/pdf',
        headers={'Content-Disposition': 'attachment; filename="cashgap_forecast.pdf"'}
    )
    