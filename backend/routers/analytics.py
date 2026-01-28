from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
import io
import asyncio
import logging

from concurrent.futures import ThreadPoolExecutor

# Импортируем сервис и модели
from analysis_service import analysis_service
from services.supply import supply_service
from services.pdf_generator import pdf_generator
from database import get_db, User, ProductCost, SupplySettings
from dependencies import get_current_user
from wb_api.statistics import WBStatisticsAPI
from config.plans import get_limit, has_feature, get_plan_config
from mock_service import mock_service

# Main analytics router (Data endpoints)
router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

# Finance router (Report endpoints to match frontend requests)
finance_router = APIRouter(prefix="/api/finance", tags=["Finance"])

executor = ThreadPoolExecutor(max_workers=2)

# --- НОВЫЙ СЕРВИС: ВОРОНКА ПРОДАЖ ---
# --- ОБНОВЛЕННЫЙ СЕРВИС: ВОРОНКА ПРОДАЖ ---
@router.get("/funnel")
async def get_sales_funnel(
    days: int = Query(30, ge=7, le=365),
    nm_ids: Optional[str] = Query(None, description="Comma-separated list of Item IDs"),
    user: User = Depends(get_current_user),
):
    """
    Получение точных исторических данных для воронки.
    Приоритет отдается API Статистики (V1) для финансов.
    """
    # 1. Проверка лимитов тарифа
    limit_days = get_limit(user.subscription_plan, "history_days")
    if days > limit_days:
        days = limit_days

    if not user.wb_api_token:
        raise HTTPException(status_code=400, detail="Требуется API токен WB")
    
    if user.wb_api_token == "DEMO":
        return mock_service.get_funnel(days)

    date_to = datetime.now()
    date_from = date_to - timedelta(days=days)
    
    date_to_str = date_to.strftime("%Y-%m-%d")
    date_from_str = date_from.strftime("%Y-%m-%d")

    # Parse nm_ids
    filter_ids = set()
    if nm_ids:
        try:
            filter_ids = {int(x.strip()) for x in nm_ids.split(",") if x.strip().isdigit()}
        except ValueError:
            pass

    wb_api = WBStatisticsAPI(user.wb_api_token)

    try:
        # 1. Запускаем параллельные запросы
        task_v3 = wb_api.get_sales_funnel_full(user.wb_api_token, date_from_str, date_to_str, nm_ids=list(filter_ids))
        task_orders = wb_api.get_orders(days=days)
        task_sales = wb_api.get_sales(days=days)
        
        funnel_total, orders_history, sales_history = await asyncio.gather(task_v3, task_orders, task_sales)

        # 2. Инициализация структуры графика по дням
        chart_data = {}
        for i in range(days):
            d = (date_from + timedelta(days=i)).strftime("%Y-%m-%d")
            chart_data[d] = {
                "date": d,
                "visitors": 0,  
                "cart": 0,      
                "orders": 0,    
                "buyouts": 0,   
                "orders_sum": 0, 
                "buyouts_sum": 0 
            }

        # 3. Обработка ЗАКАЗОВ (V1 - Точные данные)
        total_orders_exact = 0
        total_revenue_exact = 0
        
        if orders_history:
            for order in orders_history:
                if filter_ids and order.get("nmId") not in filter_ids:
                    continue
                if order.get("isCancel"): 
                    continue

                d_raw = order.get("date", "")
                d = d_raw[:10]
                
                if d in chart_data:
                    # FIX: Расчет цены (fallback если API вернул 0)
                    price = order.get("priceWithDiscount", 0)
                    if price == 0:
                        total_price = order.get("totalPrice", 0)
                        discount = order.get("discountPercent", 0)
                        price = total_price * (1 - discount/100)
                    
                    chart_data[d]["orders"] += 1
                    chart_data[d]["orders_sum"] += price
                    total_orders_exact += 1
                    total_revenue_exact += price

        # 4. Обработка ВЫКУПОВ (V1 - Точные данные)
        total_buyouts_exact = 0
        total_buyouts_sum_exact = 0

        if sales_history:
            for sale in sales_history:
                if filter_ids and sale.get("nmId") not in filter_ids:
                    continue
                if sale.get("isStorno") or not sale.get("saleID", "").startswith("S"):
                    continue

                d_raw = sale.get("date", "")
                d = d_raw[:10]
                
                if d in chart_data:
                    # FIX: Расчет цены (fallback)
                    price = sale.get("priceWithDiscount", 0)
                    if price == 0:
                        total_price = sale.get("totalPrice", 0)
                        discount = sale.get("discountPercent", 0)
                        price = total_price * (1 - discount/100)

                    chart_data[d]["buyouts"] += 1
                    chart_data[d]["buyouts_sum"] += price
                    total_buyouts_exact += 1
                    total_buyouts_sum_exact += price

        # 5. Обработка ТРАФИКА (V3 -> Распределение)
        v3_visitors = funnel_total.get("visitors", 0)
        v3_carts = funnel_total.get("addToCart", 0)
        
        is_exact = total_orders_exact > 0
        
        final_orders = total_orders_exact if is_exact else funnel_total.get("ordersCount", 0)
        final_revenue = total_revenue_exact if is_exact else funnel_total.get("ordersSum", 0)
        final_buyouts = total_buyouts_exact if is_exact else funnel_total.get("buyoutsCount", 0)
        final_buyouts_sum = total_buyouts_sum_exact if is_exact else funnel_total.get("buyoutsSum", 0)

        # Распределение трафика
        sorted_dates = sorted(chart_data.keys())
        
        if is_exact and total_orders_exact > 0:
            views_per_order = v3_visitors / total_orders_exact
            carts_per_order = v3_carts / total_orders_exact
            
            remaining_views = v3_visitors
            remaining_carts = v3_carts
            
            for d in sorted_dates:
                orders_today = chart_data[d]["orders"]
                if orders_today > 0:
                    day_views = int(orders_today * views_per_order)
                    day_carts = int(orders_today * carts_per_order)
                    chart_data[d]["visitors"] = day_views
                    chart_data[d]["cart"] = day_carts
                    remaining_views -= day_views
                    remaining_carts -= day_carts
            
            if days > 0:
                base_views = max(0, int(remaining_views / days))
                base_carts = max(0, int(remaining_carts / days))
                for d in sorted_dates:
                    chart_data[d]["visitors"] += base_views
                    chart_data[d]["cart"] += base_carts
        else:
            avg_views = int(v3_visitors / days) if days > 0 else 0
            avg_carts = int(v3_carts / days) if days > 0 else 0
            
            for d in sorted_dates:
                chart_data[d]["visitors"] = avg_views
                chart_data[d]["cart"] = avg_carts
                if not is_exact:
                    chart_data[d]["orders"] = int(final_orders / days)
                    chart_data[d]["orders_sum"] = int(final_revenue / days)

        # Конверсии
        cr_view_cart = (v3_carts / v3_visitors * 100) if v3_visitors > 0 else 0
        cr_cart_order = (final_orders / v3_carts * 100) if v3_carts > 0 else 0
        cr_order_buyout = (final_buyouts / final_orders * 100) if final_orders > 0 else 0
        
        final_chart = [chart_data[d] for d in sorted_dates]

        return {
            "period": f"{days} дн.",
            "totals": {
                "visitors": v3_visitors,
                "cart": v3_carts,
                "orders": final_orders,
                "buyouts": final_buyouts,
                "revenue": int(final_revenue), # Принудительно int для красоты
                "buyouts_revenue": int(final_buyouts_sum)
            },
            "conversions": {
                "view_to_cart": round(cr_view_cart, 1),
                "cart_to_order": round(cr_cart_order, 1),
                "order_to_buyout": round(cr_order_buyout, 1)
            },
            "chart": final_chart,
            "is_exact": is_exact
        }

    except Exception as e:
        logger.error(f"Funnel Error: {e}", exc_info=True)
        return {
            "period": f"{days} дн.",
            "totals": {"visitors": 0, "cart": 0, "orders": 0, "buyouts": 0, "revenue": 0, "buyouts_revenue": 0},
            "conversions": {"view_to_cart": 0, "cart_to_order": 0, "order_to_buyout": 0},
            "chart": [],
            "error": str(e)
        }

# --- EXISTING ANALYTICS ROUTES ---

@router.get("/abc-xyz")
async def get_abc_xyz_stats(
    days: int = Query(30, ge=7, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    history_limit = get_limit(user.subscription_plan, "history_days")
    if days > history_limit:
        plan_config = get_plan_config(user.subscription_plan)
        raise HTTPException(
            status_code=403,
            detail=f"Период {days} дней недоступен на вашем тарифе. Доступно: {history_limit} дней."
        )
    
    date_from = datetime.now() - timedelta(days=days)
    
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

    analysis_result = analysis_service.economics.calculate_abc_xyz(raw_data)
    
    return analysis_result

@router.get("/forensics/returns")
async def get_return_forensics_endpoint(
    days: int = Query(30, ge=7, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not has_feature(user.subscription_plan, "forensics"):
        raise HTTPException(status_code=403, detail="Доступно на тарифе Аналитик+")
    
    history_limit = get_limit(user.subscription_plan, "history_days")
    if days > history_limit:
        days = history_limit 
    
    date_to = datetime.now()
    date_from = date_to - timedelta(days=days)
    
    try:
        data = await analysis_service.economics.get_return_forensics(user.id, date_from, date_to)
        return data
    except Exception as e:
        return {"status": "error", "message": "Ошибка базы данных"}

@router.get("/finance/cash-gap")
async def get_cash_gap_forecast(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not has_feature(user.subscription_plan, "forensics_cashgap"):
        raise HTTPException(status_code=403, detail="Доступно на тарифе Стратег")
    
    if not user.wb_api_token:
        raise HTTPException(status_code=400, detail="WB API Token required")

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
        return {"total_needed_soon": 0, "nearest_gap_date": None, "timeline": []}

    stocks = turnover_data.get("stocks", [])
    orders = turnover_data.get("orders", [])
    
    supply_analysis = supply_service.analyze_supply(stocks, orders, config)

    if not supply_analysis:
        return {"total_needed_soon": 0, "nearest_gap_date": None, "timeline": []}

    skus = [i['sku'] for i in supply_analysis]
    
    costs_stmt = select(ProductCost).where(
        ProductCost.user_id == user.id, 
        ProductCost.sku.in_(skus)
    )
    costs_res = await db.execute(costs_stmt)
    costs = costs_res.scalars().all()
    costs_map = {c.sku: c.cost_price for c in costs}

    result = supply_service.calculate_cash_gap(supply_analysis, costs_map)
    return result

# --- FINANCE ROUTER ---

@finance_router.get("/report/forensics-pdf")
async def generate_forensics_pdf(
    days: int = Query(30, ge=7, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not has_feature(user.subscription_plan, "forensics"):
        raise HTTPException(status_code=403, detail="Upgrade plan")
    
    date_to = datetime.now()
    date_from = date_to - timedelta(days=days)
    
    try:
        forensics_data = await analysis_service.economics.get_return_forensics(user.id, date_from, date_to)
    except Exception:
        forensics_data = {"status": "error", "message": "Database Error"}
    
    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(executor, pdf_generator.create_forensics_pdf, forensics_data)
    
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="report.pdf"'})

@finance_router.get("/report/cashgap-pdf")
async def generate_cashgap_pdf(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not has_feature(user.subscription_plan, "forensics_cashgap"):
        raise HTTPException(status_code=403, detail="Upgrade plan")
    
    if not user.wb_api_token:
        raise HTTPException(status_code=400, detail="WB API Token required")

    try:
        stmt = select(SupplySettings).where(SupplySettings.user_id == user.id)
        settings_res = await db.execute(stmt)
        settings = settings_res.scalars().first()
        
        config = {
            "lead_time": settings.lead_time if settings else 7,
            "min_stock_days": settings.min_stock_days if settings else 14,
            "abc_a_share": settings.abc_a_share if settings else 80
        }
        
        wb_api = WBStatisticsAPI(user.wb_api_token)
        turnover_data = await wb_api.get_turnover_data()
        
        stocks = turnover_data.get("stocks", [])
        orders = turnover_data.get("orders", [])
        
        supply_analysis = supply_service.analyze_supply(stocks, orders, config)
        
        if not supply_analysis:
            cashgap_data = {"status": "empty", "message": "Нет данных"}
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
            
    except Exception as e:
        cashgap_data = {"status": "error", "message": str(e)}

    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(executor, pdf_generator.create_cashgap_pdf, cashgap_data)
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type='application/pdf', headers={'Content-Disposition': 'attachment; filename="report.pdf"'})