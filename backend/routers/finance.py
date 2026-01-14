import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from database import get_db, get_redis_client
from dependencies import get_current_user
from models import User, ProductCost
from wb_api_service import wb_api_service
from analysis_service import analysis_service
from tasks.finance import sync_product_metadata 

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
        
    if user.subscription_plan == "free":
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
    if not user.wb_api_token: 
        return []
    
    # 1. Получаем остатки из WB API
    # Нам нужны поля 'Price' (базовая) и 'Discount' (скидка)
    try:
        stocks = await wb_api_service.get_my_stocks(user.wb_api_token)
        if not stocks: 
            return []
    except Exception:
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
    
    # 3. Загружаем настройки расходов из БД
    costs_res = await db.execute(select(ProductCost).where(ProductCost.user_id == user.id, ProductCost.sku.in_(skus)))
    costs_map = {c.sku: c for c in costs_res.scalars().all()}
    
    # 4. Redis кеш
    r_client = get_redis_client()
    
    commissions_global = {}
    logistics_tariffs = {}
    products_meta_cache = {}

    if r_client:
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

    result = []

    for sku, data in sku_map.items():
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
        
    return result

@router.post("/internal/cost/{sku}")
async def set_product_cost(
    sku: int, 
    req: CostUpdateRequest, 
    user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
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