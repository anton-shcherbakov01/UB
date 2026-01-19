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
from services.pdf_generator import pdf_generator
from database import get_db, User, ProductCost, SupplySettings
from dependencies import get_current_user
from wb_api.statistics import WBStatisticsAPI
from config.plans import get_limit, has_feature, get_plan_config

# Main analytics router (Data endpoints)
router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

# Finance router (Report endpoints to match frontend requests)
finance_router = APIRouter(prefix="/api/finance", tags=["Finance"])

executor = ThreadPoolExecutor(max_workers=2)

# --- НОВЫЙ СЕРВИС: ВОРОНКА ПРОДАЖ ---
@router.get("/funnel")
async def get_sales_funnel(
    days: int = Query(30, ge=7, le=365),
    nm_ids: Optional[str] = Query(None, description="Comma-separated list of Item IDs"),
    user: User = Depends(get_current_user),
):
    """
    Получение данных для построения воронки продаж.
    Ограничивает глубину истории в зависимости от тарифа.
    """
    # 1. Проверка лимитов тарифа
    limit_days = get_limit(user.subscription_plan, "history_days")
    if days > limit_days:
        days = limit_days

    if not user.wb_api_token:
        raise HTTPException(status_code=400, detail="Требуется API токен WB")

    date_to = datetime.now()
    date_from = date_to - timedelta(days=days)
    
    date_to_str = date_to.strftime("%Y-%m-%d")
    date_from_str = date_from.strftime("%Y-%m-%d")

    # Parse nm_ids
    filter_ids = []
    if nm_ids:
        try:
            filter_ids = [int(x.strip()) for x in nm_ids.split(",") if x.strip().isdigit()]
        except ValueError:
            pass

    wb_api = WBStatisticsAPI(user.wb_api_token)

    try:
        # 1. Получаем агрегированные данные воронки (Просмотры, Корзины) из V3
        funnel_total = await wb_api.get_sales_funnel_full(user.wb_api_token, date_from_str, date_to_str, nm_ids=filter_ids)
        
        # 2. Получаем исторические данные по заказам и выкупам из V1 (они точные по дням)
        await asyncio.sleep(1)
        orders_history = await wb_api.get_orders(days=days)
        
        await asyncio.sleep(1) 
        sales_history = await wb_api.get_sales(days=days)

        # Подготовка структуры графика
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

        # Фильтруем и заполняем точные данные (Заказы)
        total_orders_count_period = 0
        total_orders_sum_v1 = 0
        
        if orders_history:
            for order in orders_history:
                if filter_ids and order.get("nmId") not in filter_ids:
                    continue

                d = order.get("date", "")[:10]
                if d in chart_data and not order.get("isCancel"):
                    chart_data[d]["orders"] += 1
                    chart_data[d]["orders_sum"] += order.get("priceWithDiscount", 0)
                    total_orders_count_period += 1
                    total_orders_sum_v1 += order.get("priceWithDiscount", 0)

        # Фильтруем и заполняем точные данные (Выкупы)
        total_buyouts_count_v1 = 0
        total_buyouts_sum_v1 = 0

        if sales_history:
            for sale in sales_history:
                if filter_ids and sale.get("nmId") not in filter_ids:
                    continue

                d = sale.get("date", "")[:10]
                # isStorno - это возврат, saleID startswith S - продажа
                if d in chart_data and not sale.get("isStorno") and sale.get("saleID", "").startswith("S"):
                    chart_data[d]["buyouts"] += 1
                    chart_data[d]["buyouts_sum"] += sale.get("priceWithDiscount", 0)
                    total_buyouts_count_v1 += 1
                    total_buyouts_sum_v1 += sale.get("priceWithDiscount", 0)

        # 3. Данные из V3 (Точные общие цифры)
        v3_visitors = funnel_total.get("visitors", 0)
        v3_carts = funnel_total.get("addToCart", 0)
        v3_orders_count = funnel_total.get("ordersCount", 0)
        v3_orders_sum = funnel_total.get("ordersSum", 0)
        v3_buyouts_count = funnel_total.get("buyoutsCount", 0)
        v3_buyouts_sum = funnel_total.get("buyoutsSum", 0)
        
        # --- FALLBACK MECHANISM ---
        # Если API V1 отвалился (вернул 0 из-за лимитов), но V3 вернул данные - используем V3.
        use_fallback = False
        if total_orders_sum_v1 == 0 and v3_orders_sum > 0:
            use_fallback = True
            final_orders_count = v3_orders_count
            final_orders_sum = v3_orders_sum
            final_buyouts_count = v3_buyouts_count
            final_buyouts_sum = v3_buyouts_sum
        else:
            final_orders_count = total_orders_count_period
            final_orders_sum = total_orders_sum_v1
            final_buyouts_count = total_buyouts_count_v1
            final_buyouts_sum = total_buyouts_sum_v1

        # Конверсии периода
        cr_cart_order = (final_orders_count / v3_carts) if v3_carts > 0 else 0.0
        cr_view_cart = (v3_carts / v3_visitors) if v3_visitors > 0 else 0.0

        sorted_dates = sorted(chart_data.keys())
        final_chart = []

        # Средние значения для fallback
        avg_order_sum = final_orders_sum / days if days > 0 else 0
        avg_order_cnt = final_orders_count / days if days > 0 else 0
        avg_buyout_sum = final_buyouts_sum / days if days > 0 else 0
        avg_buyout_cnt = final_buyouts_count / days if days > 0 else 0
        
        for date_key in sorted_dates:
            day_stats = chart_data[date_key]
            
            if use_fallback:
                # Заполняем средними значениями
                day_stats["orders"] = int(avg_order_cnt)
                day_stats["orders_sum"] = int(avg_order_sum)
                day_stats["buyouts"] = int(avg_buyout_cnt)
                day_stats["buyouts_sum"] = int(avg_buyout_sum)
                orders_metric = int(avg_order_cnt)
            else:
                orders_metric = day_stats["orders"]
            
            # Аппроксимация для Воронки (Просмотры/Корзины)
            if orders_metric > 0:
                estimated_carts = int(orders_metric / cr_cart_order) if cr_cart_order > 0 else orders_metric * 5
                estimated_visitors = int(estimated_carts / cr_view_cart) if cr_view_cart > 0 else estimated_carts * 10
            else:
                # "Шум"
                estimated_carts = max(0, int((v3_carts - final_orders_count) / days)) if days > 0 else 0
                estimated_visitors = max(0, int((v3_visitors - (final_orders_count * 10)) / days)) if days > 0 else 0

            day_stats["cart"] = estimated_carts
            day_stats["visitors"] = estimated_visitors
            final_chart.append(day_stats)

        return {
            "period": f"{days} дн.",
            "limit_used": days,
            "max_limit": limit_days,
            "totals": {
                "visitors": v3_visitors,
                "cart": v3_carts,
                "orders": final_orders_count,
                "buyouts": final_buyouts_count,
                "revenue": final_orders_sum,
                "buyouts_revenue": final_buyouts_sum # Added explicit revenue for buyouts
            },
            "conversions": {
                "view_to_cart": round(cr_view_cart * 100, 1),
                "cart_to_order": round(cr_cart_order * 100, 1),
                "order_to_buyout": round((final_buyouts_count / final_orders_count * 100), 1) if final_orders_count else 0
            },
            "chart": final_chart,
            "is_estimated": use_fallback
        }

    except Exception as e:
        print(f"Funnel Error: {e}")
        return {
            "period": f"{days} дн.",
            "limit_used": days, 
            "max_limit": limit_days,
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