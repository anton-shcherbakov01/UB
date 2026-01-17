import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
import io
import asyncio
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from database import get_db, User, ProductCost
from dependencies import get_current_user, get_redis_client
from dependencies.quota import QuotaCheck
from fastapi import HTTPException
from wb_api_service import wb_api_service
from analysis_service import analysis_service
from tasks.finance import sync_product_metadata

# Настройка логгера
logger = logging.getLogger("FinanceRouter")

router = APIRouter(prefix="/api", tags=["Finance"])

class CostUpdateRequest(BaseModel):
    cost_price: int
    logistics: Optional[int] = 50
    commission_percent: Optional[float] = 25.0

class TransitCalcRequest(BaseModel):
    volume: int 
    destination: str = "Koledino"

def calculate_auto_logistics(volume_l: float, tariffs_map: dict) -> float:
    """
    Считает логистику на основе тарифов склада.
    """
    if not tariffs_map:
        return 50.0 
    
    wh_tariff = tariffs_map.get('Коледино') 
    if not wh_tariff and tariffs_map:
        wh_tariff = list(tariffs_map.values())[0]
    
    if not wh_tariff:
        return 50.0

    base = wh_tariff.get('base', 35.0)
    liter_rate = wh_tariff.get('liter', 5.0)

    if volume_l <= 5:
        return base
    
    extra = volume_l - 5
    return round(base + (extra * liter_rate), 2)


@router.get("/internal/stats")
async def get_internal_stats(user: User = Depends(get_current_user)):
    if not user.wb_api_token:
        return {"orders_today": {"sum": 0, "count": 0}, "stocks": {"total_quantity": 0}}
    try:
        return await wb_api_service.get_dashboard_stats(user.wb_api_token)
    except:
        return {"orders_today": {"sum": 0, "count": 0}, "stocks": {"total_quantity": 0}}

@router.get("/internal/stories")
async def get_stories(user: User = Depends(get_current_user)):
    stories = []
    orders_sum = 0
    stocks_qty = 0
    
    if user.wb_api_token:
        try:
            stats = await wb_api_service.get_dashboard_stats(user.wb_api_token)
            orders_sum = stats.get('orders_today', {}).get('sum', 0)
            stocks_qty = stats.get('stocks', {}).get('total_quantity', 0)
            stories.append({
                "id": 1, 
                "title": "Продажи", 
                "val": f"{orders_sum // 1000}k ₽" if orders_sum > 1000 else f"{orders_sum} ₽",
                "subtitle": "Сегодня",
                "color": "bg-emerald-500"
            })
        except:
             stories.append({
                "id": 1, "title": "API Error", "val": "Fail", "color": "bg-red-500", "subtitle": "Connection"
            })
    else:
        stories.append({
            "id": 1, "title": "API", "val": "Подключи", "color": "bg-slate-400", "subtitle": "Нет данных"
        })
        
    if user.subscription_plan == "start":
        stories.append({
            "id": 2, "title": "Биддер", "val": "OFF", "color": "bg-purple-500", "subtitle": "Upgrade"
        })
    else:
        stories.append({
            "id": 2, "title": "Биддер", "val": "Active", "color": "bg-purple-500", "subtitle": "Safe Mode"
        })
        
    if user.wb_api_token:
        stories.append({
            "id": 3, "title": "Склад", "val": f"{stocks_qty}", "color": "bg-blue-500", "subtitle": "Всего шт."
        })
        
    return stories

@router.get("/internal/products")
async def get_my_products_finance(
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    logger.info(f"💰 [UnitEconomy] Запрос от {user.id}")

    if not user.wb_api_token: 
        logger.warning(f"⚠️ [UnitEconomy] Нет токена у юзера {user.id}")
        return []
    
    # 1. Получаем остатки из WB API
    try:
        stocks = await wb_api_service.get_my_stocks(user.wb_api_token)
        logger.info(f"📦 [UnitEconomy] Получено {len(stocks) if stocks else 0} записей остатков")
        
        if not stocks: 
            logger.warning("⚠️ [UnitEconomy] WB вернул пустой список остатков")
            return []
    except Exception as e:
        logger.error(f"❌ [UnitEconomy] Ошибка получения остатков: {e}")
        return []
    
    # 2. Группируем остатки по SKU
    sku_map = {}
    for s in stocks:
        sku = s.get('nmId')
        if not sku: continue
        
        if sku not in sku_map:
            sku_map[sku] = {
                "sku": sku, 
                "quantity": 0, 
                "basic_price": s.get('Price', 0),    # Цена до скидки
                "discount": s.get('Discount', 0)     # Скидка продавца
            }
        sku_map[sku]['quantity'] += s.get('quantity', 0)
    
    skus = list(sku_map.keys())
    logger.info(f"📊 [UnitEconomy] Уникальных артикулов (SKU): {len(skus)}")
    
    # 3. Загружаем настройки расходов из БД
    try:
        costs_res = await db.execute(select(ProductCost).where(ProductCost.user_id == user.id, ProductCost.sku.in_(skus)))
        costs_map = {c.sku: c for c in costs_res.scalars().all()}
    except Exception as e:
        logger.error(f"❌ [UnitEconomy] Ошибка БД (Cost): {e}")
        costs_map = {}
    
    # 4. Redis кеш
    r_client = get_redis_client()
    
    commissions_global = {}
    logistics_tariffs = {}
    products_meta_cache = {}

    if r_client:
        try:
            comm_data = r_client.get(f"meta:commissions:{user.id}")
            tariffs_data = r_client.get("meta:logistics_tariffs")
            
            if comm_data: commissions_global = json.loads(comm_data)
            if tariffs_data: logistics_tariffs = json.loads(tariffs_data)

            # Фоновое обновление
            if not comm_data or not tariffs_data:
                background_tasks.add_task(sync_product_metadata, user.id)

            pipe = r_client.pipeline()
            for sku in skus:
                pipe.get(f"meta:product:{user.id}:{sku}")
                pipe.get(f"forecast:{user.id}:{sku}")
            
            redis_results = pipe.execute()
            
            for i, sku in enumerate(skus):
                meta_raw = redis_results[i * 2]
                forecast_raw = redis_results[i * 2 + 1]
                
                products_meta_cache[sku] = {
                    "meta": json.loads(meta_raw) if meta_raw else None,
                    "forecast": json.loads(forecast_raw) if forecast_raw else None
                }
        except Exception as e:
            logger.error(f"⚠️ [UnitEconomy] Ошибка Redis: {e}")

    result = []

    for sku, data in sku_map.items():
        try:
            cost_obj = costs_map.get(sku)
            
            cache_entry = products_meta_cache.get(sku, {})
            meta = cache_entry.get("meta") or {}
            forecast_json = cache_entry.get("forecast")
            
            # --- ЛОГИСТИКА ---
            if cost_obj and cost_obj.logistics is not None:
                logistics_val = cost_obj.logistics
            else:
                volume = meta.get('volume', 1.0) 
                logistics_val = calculate_auto_logistics(volume, logistics_tariffs)

            # --- КОМИССИЯ ---
            if cost_obj and cost_obj.commission_percent is not None:
                commission_pct = cost_obj.commission_percent
            else:
                subj_id = str(meta.get('subject_id', ''))
                commission_pct = commissions_global.get(subj_id, 25.0)

            cost_price = cost_obj.cost_price if cost_obj else 0
            
            # --- ЦЕНООБРАЗОВАНИЕ ---
            basic_price = data['basic_price']
            discount_percent = data['discount']
            
            # Реальная цена реализации = База - Скидка
            selling_price = basic_price * (1 - discount_percent/100)
            
            commission_rub = selling_price * (commission_pct / 100.0)
            
            profit = selling_price - commission_rub - logistics_val - cost_price
            
            roi = round((profit / cost_price * 100), 1) if cost_price > 0 else 0
            margin = int(profit / selling_price * 100) if selling_price > 0 else 0
            
            # --- SUPPLY ---
            supply_data = None
            if forecast_json:
                try:
                    supply_data = analysis_service.calculate_supply_metrics(
                        current_stock=data['quantity'],
                        sales_history=[],
                        forecast_data=forecast_json
                    )
                except: pass
            
            if not supply_data:
                supply_data = {
                    "status": "unknown",
                    "recommendation": "Анализ...",
                    "metrics": {
                        "safety_stock": 0, "rop": 0, "days_left": 0, 
                        "avg_daily_demand": 0, "current_stock": data['quantity']
                    }
                }

            result.append({
                "sku": sku,
                "quantity": data['quantity'],
                "price_structure": {
                    "basic": int(basic_price),
                    "discount": int(discount_percent),
                    "selling": int(selling_price)
                },
                "cost_price": cost_price,
                "logistics": logistics_val,
                "commission_percent": commission_pct,
                "unit_economy": {
                    "profit": int(profit),
                    "roi": roi,
                    "margin": margin
                },
                "supply": supply_data
            })
        except Exception as e:
            logger.error(f"❌ [UnitEconomy] Ошибка расчета SKU {sku}: {e}")
            continue
            
    logger.info(f"🏁 [UnitEconomy] Итог: {len(result)} товаров")
    return result

@router.post("/internal/cost/{sku}")
async def set_product_cost(
    sku: int, 
    req: CostUpdateRequest, 
    user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    logger.info(f"✏️ [UnitEconomy] Обновление костов SKU {sku} для юзера {user.id}")
    try:
        stmt = select(ProductCost).where(ProductCost.user_id == user.id, ProductCost.sku == sku)
        cost_obj = (await db.execute(stmt)).scalars().first()
        if cost_obj:
            cost_obj.cost_price = req.cost_price
            cost_obj.logistics = req.logistics
            cost_obj.commission_percent = req.commission_percent
            cost_obj.updated_at = datetime.utcnow()
        else:
            cost_obj = ProductCost(
                user_id=user.id, 
                sku=sku, 
                cost_price=req.cost_price,
                logistics=req.logistics,
                commission_percent=req.commission_percent
            )
            db.add(cost_obj)
        await db.commit()
        return {"status": "saved", "data": req.dict()}
    except Exception as e:
        logger.error(f"❌ [UnitEconomy] Ошибка сохранения костов: {e}")
        raise HTTPException(status_code=500, detail="Save error")

@router.get("/internal/coefficients")
async def get_supply_coefficients(user: User = Depends(get_current_user)):
    if not user.wb_api_token:
        return []
    try:
        data = await wb_api_service.get_warehouse_coeffs(user.wb_api_token)
        return data if data else []
    except:
        return []

@router.post("/internal/transit_calc")
async def calculate_transit(req: TransitCalcRequest, user: User = Depends(get_current_user)):
    return await wb_api_service.calculate_transit(req.volume, req.destination)

@router.get("/finance/pnl")
async def get_pnl_data(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get P&L (Profit & Loss) data for the user.
    
    For "start" plan: Only yesterday's data is available (pnl_demo feature).
    For "analyst" and higher: Full date range is available (pnl_full feature).
    """
    from datetime import timedelta
    from config.plans import has_feature
    
    now = datetime.utcnow()
    
    import logging
    logger = logging.getLogger("FinanceRouter")
    
    # Check feature access based on plan
    if user.subscription_plan == "start":
        # Start plan has pnl_demo feature - only yesterday
        if not has_feature(user.subscription_plan, "pnl_demo"):
            logger.warning(f"P&L 403: User {user.id} (plan={user.subscription_plan}) lacks pnl_demo feature")
            raise HTTPException(status_code=403, detail="P&L feature requires upgrade")
        yesterday = now - timedelta(days=1)
        date_from_dt = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        date_to_dt = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        # Analyst+ plans have pnl_full feature - full date range
        if not has_feature(user.subscription_plan, "pnl_full"):
            logger.warning(f"P&L 403: User {user.id} (plan={user.subscription_plan}) lacks pnl_full feature")
            raise HTTPException(status_code=403, detail="P&L feature requires upgrade")
        
        # For analyst+ plans, allow full date range
        if date_from:
            try:
                date_from_dt = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            except:
                # Fallback to 30 days ago if parsing fails
                date_from_dt = now - timedelta(days=30)
        else:
            date_from_dt = now - timedelta(days=30)
        
        if date_to:
            try:
                date_to_dt = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            except:
                date_to_dt = now
        else:
            date_to_dt = now
    
    # Проверяем лимит history_days для analyst+ планов
    if user.subscription_plan != "start":
        from config.plans import get_limit
        history_limit = get_limit(user.subscription_plan, "history_days")
        days_requested = (date_to_dt - date_from_dt).days
        if days_requested > history_limit:
            from config.plans import get_plan_config
            plan_config = get_plan_config(user.subscription_plan)
            logger.warning(f"P&L 403: User {user.id} (plan={user.subscription_plan}) requested {days_requested} days, limit={history_limit}")
            raise HTTPException(
                status_code=403,
                detail=f"Период {days_requested} дней недоступен на вашем тарифе. Доступно: {history_limit} дней. Текущий план: {plan_config.get('name', user.subscription_plan)}"
            )
    
    # Get P&L data from analysis service
    pnl_data = await analysis_service.get_pnl_data(user.id, date_from_dt, date_to_dt, db)
    
    return {
        "plan": user.subscription_plan,
        "date_from": date_from_dt.isoformat(),
        "date_to": date_to_dt.isoformat(),
        "data": pnl_data
    }

executor = ThreadPoolExecutor(max_workers=2)

@router.get("/report/pnl-pdf")
async def generate_pnl_pdf(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Generate P&L PDF report"""
    from config.plans import has_feature
    
    # Check access (same logic as get_pnl_data)
    now = datetime.utcnow()
    if user.subscription_plan == "start":
        if not has_feature(user.subscription_plan, "pnl_demo"):
            raise HTTPException(status_code=403, detail="P&L PDF requires upgrade")
        yesterday = now - timedelta(days=1)
        date_from_dt = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        date_to_dt = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        if not has_feature(user.subscription_plan, "pnl_full"):
            raise HTTPException(status_code=403, detail="P&L PDF requires upgrade")
        
        if date_from:
            try:
                date_from_dt = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            except:
                date_from_dt = now - timedelta(days=30)
        else:
            date_from_dt = now - timedelta(days=30)
        
        if date_to:
            try:
                date_to_dt = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            except:
                date_to_dt = now
        else:
            date_to_dt = now
    
    # Get P&L data
    pnl_data = await analysis_service.get_pnl_data(user.id, date_from_dt, date_to_dt, db)
    
    # Generate PDF in executor
    from services.pdf_generator import pdf_generator
    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(
        executor,
        pdf_generator.create_pnl_pdf,
        pnl_data,
        date_from_dt.isoformat(),
        date_to_dt.isoformat()
    )
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="pnl_report_{date_from_dt.strftime("%Y%m%d")}_{date_to_dt.strftime("%Y%m%d")}.pdf"'}
    )

@router.get("/report/unit-economy-pdf")
async def generate_unit_economy_pdf(
    user: User = Depends(QuotaCheck(feature_flag="unit_economy")),
    db: AsyncSession = Depends(get_db)
):
    """Generate Unit Economy PDF report. Requires Analyst+ plan."""
    if not user.wb_api_token:
        raise HTTPException(status_code=400, detail="WB API Token required")
    
    # Get unit economy data (reuse existing endpoint logic)
    from fastapi import BackgroundTasks
    background_tasks = BackgroundTasks()
    
    # Call the internal endpoint logic
    unit_data = await get_my_products_finance(background_tasks, user, db)
    
    if not unit_data:
        raise HTTPException(status_code=404, detail="Нет данных для Unit экономики")
    
    # Generate PDF in executor
    from services.pdf_generator import pdf_generator
    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(
        executor,
        pdf_generator.create_unit_economy_pdf,
        unit_data
    )
    
    filename = f"unit_economy_{datetime.now().strftime('%Y%m%d')}.pdf"
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(len(pdf_bytes)),
            'Cache-Control': 'no-cache'
        }
    )