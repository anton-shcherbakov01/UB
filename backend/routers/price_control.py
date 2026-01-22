import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional

from database import get_db, User, PriceAlert, ProductCost
from dependencies import get_current_user
from wb_api_service import wb_api_service

logger = logging.getLogger("PriceControl")
router = APIRouter(prefix="/api/control", tags=["Price Control"])

class AlertUpdateRequest(BaseModel):
    sku: int
    min_price: int
    is_active: bool = True

@router.get("/list")
async def get_controlled_items(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Получает список товаров напрямую из API Цен и Скидок.
    Матчит с настройками алертов из БД.
    """
    if not user.wb_api_token:
        raise HTTPException(400, "Token required")

    # 1. Загружаем актуальные цены из WB API (Быстро)
    try:
        wb_goods = await wb_api_service.get_all_goods_prices(user.wb_api_token)
    except Exception as e:
        logger.error(f"Failed to fetch prices: {e}")
        return []

    if not wb_goods:
        return []

    # Собираем SKU для запроса к БД
    skus = [g['nmID'] for g in wb_goods]

    # 2. Получаем настройки алертов из БД
    alerts_stmt = select(PriceAlert).where(PriceAlert.user_id == user.id)
    alerts_res = await db.execute(alerts_stmt)
    alerts_map = {a.sku: a for a in alerts_res.scalars().all()}

    # 3. Получаем себестоимость (для расчета маржи)
    costs_stmt = select(ProductCost).where(ProductCost.user_id == user.id)
    costs_res = await db.execute(costs_stmt)
    costs_map = {c.sku: c.cost_price for c in costs_res.scalars().all()}

    result = []
    
    for item in wb_goods:
        sku = item['nmID']
        
        # Основная математика WB API
        # price - это базовая цена (до скидки, зачеркнутая)
        # discount - процент скидки
        base_price = int(item.get('price', 0))
        discount = int(item.get('discount', 0))
        
        # Эту цену установил селлер. Ниже нее он не получит (за вычетом комиссии).
        # СПП применяется уже к ней, но за счет WB.
        seller_price = int(base_price * (1 - discount / 100))
        
        alert = alerts_map.get(sku)
        cost_price = costs_map.get(sku, 0)
        
        min_price = alert.min_price if alert else 0
        is_active = alert.is_active if alert else False
        
        # Статус
        status = "ok"
        diff_percent = 0
        
        if min_price > 0:
            if seller_price < min_price:
                status = "danger" # Пробили дно
                diff_percent = round((1 - seller_price/min_price) * 100, 1)
            elif seller_price < (min_price * 1.05):
                status = "warning" # Близко к дну (5%)
        
        # Используем фото из API Контента или заглушку
        # API Цен не отдает фото и названия, но мы можем взять их из кеша, если есть, 
        # или просто сгенерировать ссылку на корзину
        vol = sku // 100000
        part = sku // 1000
        photo_url = f"https://basket-01.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"

        result.append({
            "sku": sku,
            "photo": photo_url,
            "current_price": seller_price, # Цена селлера
            "base_price": base_price,
            "discount": discount,
            "min_price": min_price,
            "cost_price": cost_price,
            "is_active": is_active,
            "status": status,
            "diff_percent": diff_percent
        })

    # Сортировка: сначала Danger, потом Warning, потом активные
    result.sort(key=lambda x: (
        0 if x['status'] == 'danger' else 
        1 if x['status'] == 'warning' else 
        2 if x['min_price'] > 0 else 3
    ))
    
    return result

@router.post("/update")
async def update_alert(
    req: AlertUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(PriceAlert).where(PriceAlert.user_id == user.id, PriceAlert.sku == req.sku)
    alert = (await db.execute(stmt)).scalars().first()
    
    if alert:
        alert.min_price = req.min_price
        alert.is_active = req.is_active
        # Сразу обновляем last_check, чтобы не спамить
        alert.last_check = datetime.utcnow() # Fix import needed
    else:
        alert = PriceAlert(
            user_id=user.id,
            sku=req.sku,
            min_price=req.min_price,
            is_active=req.is_active
        )
        db.add(alert)
        
    await db.commit()
    return {"status": "updated"}

# Для фикса импорта datetime
from datetime import datetime