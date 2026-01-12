import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from database import get_db, User, ProductCost
from dependencies import get_current_user, get_redis_client
from wb_api_service import wb_api_service
from analysis_service import analysis_service

router = APIRouter(prefix="/api", tags=["Finance"])

class CostUpdateRequest(BaseModel):
    cost_price: int

class TransitCalcRequest(BaseModel):
    volume: int 
    destination: str = "Koledino"

@router.get("/internal/stats")
async def get_internal_stats(user: User = Depends(get_current_user)):
    """Получение статистики (Заказы, Остатки) через официальный API"""
    if not user.wb_api_token:
        return {"orders_today": {"sum": 0, "count": 0}, "stocks": {"total_quantity": 0}}
    
    stats = await wb_api_service.get_dashboard_stats(user.wb_api_token)
    return stats

@router.get("/internal/stories")
async def get_stories(user: User = Depends(get_current_user)):
    """Генерация сторис на основе реальных данных"""
    stories = []
    
    # 1. Продажи
    if user.wb_api_token:
        stats = await wb_api_service.get_dashboard_stats(user.wb_api_token)
        orders_sum = stats.get('orders_today', {}).get('sum', 0)
        
        stories.append({
            "id": 1, 
            "title": "Продажи", 
            "val": f"{orders_sum // 1000}k ₽" if orders_sum > 1000 else f"{orders_sum} ₽",
            "subtitle": "Сегодня",
            "color": "bg-emerald-500"
        })
    else:
        stories.append({
            "id": 1, "title": "API", "val": "Подключи", "color": "bg-slate-400", "subtitle": "Нет данных"
        })

    # 2. Биддер
    if user.subscription_plan == "free":
        stories.append({
            "id": 2, "title": "Биддер", "val": "OFF", "color": "bg-purple-500", "subtitle": "Upgrade"
        })
    else:
        stories.append({
            "id": 2, "title": "Биддер", "val": "Active", "color": "bg-purple-500", "subtitle": "Safe Mode"
        })

    # 3. Склад (Реальные данные)
    if user.wb_api_token:
        stocks = await wb_api_service.get_dashboard_stats(user.wb_api_token)
        qty = stocks.get('stocks', {}).get('total_quantity', 0)
        stories.append({
            "id": 3, "title": "Склад", "val": f"{qty}", "color": "bg-blue-500", "subtitle": "Всего шт."
        })

    return stories

@router.get("/internal/products")
async def get_my_products_finance(
    user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    """Получение списка СВОИХ товаров для Unit-экономики (Real Data)."""
    if not user.wb_api_token: 
        return []
    
    # Оборачиваем в try-except для защиты от сбоев API
    try:
        stocks = await wb_api_service.get_my_stocks(user.wb_api_token)
        if not stocks: 
            return []
    except Exception:
        return []
    
    sku_map = {}
    for s in stocks:
        sku = s.get('nmId')
        if sku not in sku_map:
            sku_map[sku] = {
                "sku": sku, 
                "quantity": 0, 
                "price": s.get('Price', 0), 
                "discount": s.get('Discount', 0)
            }
        sku_map[sku]['quantity'] += s.get('quantity', 0)
    
    skus = list(sku_map.keys())
    
    costs_res = await db.execute(select(ProductCost).where(ProductCost.user_id == user.id, ProductCost.sku.in_(skus)))
    costs_map = {c.sku: c.cost_price for c in costs_res.scalars().all()}
    
    result = []
    r_client = get_redis_client()

    for sku, data in sku_map.items():
        cost = costs_map.get(sku, 0)
        selling_price = data['price'] * (1 - data['discount']/100)
        
        commission_rate = 0.25 
        commission = selling_price * commission_rate
        logistics = 50 
        
        profit = selling_price - commission - logistics - cost
        roi = round((profit / cost * 100), 1) if cost > 0 else 0
        margin = int(profit / selling_price * 100) if selling_price > 0 else 0
        
        supply_data = None
        if r_client:
            cached_forecast = r_client.get(f"forecast:{user.id}:{sku}")
            if cached_forecast:
                forecast_json = json.loads(cached_forecast)
                supply_data = analysis_service.calculate_supply_metrics(
                    current_stock=data['quantity'],
                    sales_history=[],
                    forecast_data=forecast_json
                )
        
        if not supply_data:
            supply_data = {
                "status": "unknown",
                "recommendation": "Мало данных",
                "metrics": {
                    "safety_stock": 0, "rop": 0, "days_left": 0, 
                    "avg_daily_demand": 0, "current_stock": data['quantity']
                }
            }

        result.append({
            "sku": sku,
            "quantity": data['quantity'],
            "price": int(selling_price),
            "cost_price": cost,
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
        cost_obj.updated_at = datetime.utcnow()
    else:
        cost_obj = ProductCost(user_id=user.id, sku=sku, cost_price=req.cost_price)
        db.add(cost_obj)
    
    await db.commit()
    return {"status": "saved", "cost_price": req.cost_price}

@router.get("/internal/coefficients")
async def get_supply_coefficients(user: User = Depends(get_current_user)):
    if not user.wb_api_token:
        return []
    # Возвращаем пустой список если API недоступен, чтобы фронт не падал
    try:
        data = await wb_api_service.get_warehouse_coeffs(user.wb_api_token)
        return data if data else []
    except:
        return []

@router.post("/internal/transit_calc")
async def calculate_transit(req: TransitCalcRequest, user: User = Depends(get_current_user)):
    return await wb_api_service.calculate_transit(req.volume, req.destination)