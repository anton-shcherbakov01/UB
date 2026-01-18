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
from config.plans import get_limit, has_feature, get_plan_config

# Note: Frontend seems to be requesting /api/finance for reports based on logs.
# Ensure this router is mounted correctly or frontend requests are updated.
router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

# Finance router (Report endpoints to match frontend requests)
finance_router = APIRouter(prefix="/api/finance", tags=["Finance"])

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

# --- НОВЫЙ СЕРВИС: ВОРОНКА ПРОДАЖ ---
@router.get("/funnel")
async def get_sales_funnel(
    days: int = Query(30, ge=7, le=365),
    user: User = Depends(get_current_user),
):
    """
    Получение данных для построения воронки продаж.
    Ограничивает глубину истории в зависимости от тарифа.
    """
    # 1. Проверка лимитов тарифа
    limit_days = get_limit(user.subscription_plan, "history_days")
    if days > limit_days:
        # Если запрашивают больше, чем положено - режем молча или кидаем ошибку
        # Для UX лучше просто обрезать дату, но предупредить фронт
        days = limit_days

    if not user.wb_api_token:
        raise HTTPException(status_code=400, detail="Требуется API токен WB")

    date_to = datetime.now()-timedelta(days=1)
    date_from = date_to - timedelta(days=days)
    
    date_to_str = date_to.strftime("%Y-%m-%d 23:59:59")
    date_from_str = date_from.strftime("%Y-%m-%d 00:00:00")

    wb_api = WBStatisticsAPI(user.wb_api_token)

    try:
        # 1. Получаем агрегированные данные воронки (Просмотры, Корзины) из V2
        # Это тяжелый запрос, он дает сумму за период
        funnel_total = await wb_api.get_sales_funnel_full(user.wb_api_token, date_from_str, date_to_str)
        
        # 2. Получаем исторические данные по заказам и выкупам из V1 (они точные по дням)
        # Нам нужно распределить "Просмотры" и "Корзины" по дням пропорционально заказам,
        # так как WB не отдает историю просмотров по дням через API V2 просто так.
        orders_history = await wb_api.get_orders(days=days)
        sales_history = await wb_api.get_sales(days=days)

        # Подготовка структуры графика
        chart_data = {}
        # Инициализируем дни
        for i in range(days):
            d = (date_from + timedelta(days=i)).strftime("%Y-%m-%d")
            chart_data[d] = {
                "date": d,
                "visitors": 0,
                "cart": 0,
                "orders": 0,
                "buyouts": 0,
                "orders_sum": 0
            }

        # Заполняем точные данные (Заказы)
        total_orders_count_period = 0
        for order in orders_history:
            d = order.get("date", "")[:10]
            if d in chart_data and not order.get("isCancel"):
                chart_data[d]["orders"] += 1
                chart_data[d]["orders_sum"] += order.get("priceWithDiscount", 0)
                total_orders_count_period += 1

        # Заполняем точные данные (Выкупы)
        for sale in sales_history:
            d = sale.get("date", "")[:10]
            if d in chart_data and not sale.get("isStorno") and sale.get("saleID", "").startswith("S"):
                chart_data[d]["buyouts"] += 1

        # 3. Аппроксимация Просмотров и Корзин по дням
        # Если у нас есть общие суммы, мы распределяем их по дням, коррелируя с заказами.
        # Это допущение, но оно необходимо для красивого графика, т.к. точной истории API не дает.
        
        total_visitors = funnel_total.get("visitors", 0)
        total_carts = funnel_total.get("addToCart", 0)
        
        # Конверсии периода
        cr_cart_order = (total_orders_count_period / total_carts) if total_carts > 0 else 0.1 # Fallback 10%
        cr_view_cart = (total_carts / total_visitors) if total_visitors > 0 else 0.05 # Fallback 5%

        sorted_dates = sorted(chart_data.keys())
        final_chart = []

        for date_key in sorted_dates:
            day_stats = chart_data[date_key]
            orders = day_stats["orders"]
            
            # Реверс-инжиниринг для графика:
            # Если были заказы, восстанавливаем примерное кол-во корзин и просмотров
            # Если заказов не было, берем среднее "шумовое" значение
            
            if orders > 0:
                estimated_carts = int(orders / cr_cart_order) if cr_cart_order > 0 else orders * 10
                estimated_visitors = int(estimated_carts / cr_view_cart) if cr_view_cart > 0 else estimated_carts * 20
            else:
                # "Шум" в дни без заказов (1/days от остатка)
                estimated_carts = max(0, int((total_carts - total_orders_count_period) / days))
                estimated_visitors = max(0, int((total_visitors - (total_orders_count_period * 20)) / days))

            day_stats["cart"] = estimated_carts
            day_stats["visitors"] = estimated_visitors
            final_chart.append(day_stats)

        # Формируем итоговый ответ
        return {
            "period": f"{days} дн.",
            "limit_used": days,
            "max_limit": limit_days,
            "totals": {
                "visitors": total_visitors,
                "cart": total_carts,
                "orders": total_orders_count_period,
                "buyouts": sum(d["buyouts"] for d in final_chart),
                "revenue": sum(d["orders_sum"] for d in final_chart)
            },
            "conversions": {
                "view_to_cart": round(cr_view_cart * 100, 1),
                "cart_to_order": round(cr_cart_order * 100, 1),
                "order_to_buyout": round((sum(d["buyouts"] for d in final_chart) / total_orders_count_period * 100), 1) if total_orders_count_period else 0
            },
            "chart": final_chart
        }

    except Exception as e:
        print(f"Funnel Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))