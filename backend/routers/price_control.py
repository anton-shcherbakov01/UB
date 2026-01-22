import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database import get_db, User, PriceAlert, ProductCost
from dependencies import get_current_user
from wb_api_service import wb_api_service

logger = logging.getLogger("PriceControl")
router = APIRouter(prefix="/api/control", tags=["Price Control"])

class AlertUpdateRequest(BaseModel):
    sku: int
    min_price: int
    is_active: bool = True

# --- ХЕЛПЕР: Определение сервера для фото (Алгоритм WB 2025) ---
def get_basket_number(sku: int) -> str:
    vol = sku // 100000
    if 0 <= vol <= 143: return '01'
    if 144 <= vol <= 287: return '02'
    if 288 <= vol <= 431: return '03'
    if 432 <= vol <= 719: return '04'
    if 720 <= vol <= 1007: return '05'
    if 1008 <= vol <= 1061: return '06'
    if 1062 <= vol <= 1115: return '07'
    if 1116 <= vol <= 1169: return '08'
    if 1170 <= vol <= 1313: return '09'
    if 1314 <= vol <= 1601: return '10'
    if 1602 <= vol <= 1655: return '11'
    if 1656 <= vol <= 1919: return '12'
    if 1920 <= vol <= 2045: return '13'
    if 2046 <= vol <= 2189: return '14'
    if 2190 <= vol <= 2405: return '15'
    if 2406 <= vol <= 2621: return '16'
    if 2622 <= vol <= 2837: return '17'
    if 2838 <= vol <= 3053: return '18'
    if 3054 <= vol <= 3269: return '19'
    if 3270 <= vol <= 3485: return '20'
    return '21' # Fallback на новые сервера

@router.get("/list")
async def get_controlled_items(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Получает список товаров напрямую из API Цен и Скидок.
    Исправлен алгоритм получения цены (из sizes) и фото.
    """
    if not user.wb_api_token:
        raise HTTPException(400, "Token required")

    # 1. Загружаем актуальные цены из WB API
    try:
        wb_goods = await wb_api_service.get_all_goods_prices(user.wb_api_token)
    except Exception as e:
        logger.error(f"Failed to fetch prices: {e}")
        raise HTTPException(502, f"WB API Error: {str(e)}")

    if not wb_goods:
        logger.warning(f"User {user.id}: WB returned 0 goods. Check 'Prices & Discounts' token scope.")
        return []

    # Собираем SKU для запроса к БД
    skus = [g['nmID'] for g in wb_goods]

    # 2. Получаем настройки алертов из БД
    alerts_stmt = select(PriceAlert).where(PriceAlert.user_id == user.id)
    alerts_res = await db.execute(alerts_stmt)
    alerts_map = {a.sku: a for a in alerts_res.scalars().all()}

    # 3. Получаем себестоимость
    costs_stmt = select(ProductCost).where(ProductCost.user_id == user.id)
    costs_res = await db.execute(costs_stmt)
    costs_map = {c.sku: c.cost_price for c in costs_res.scalars().all()}

    result = []
    
    for item in wb_goods:
        sku = item.get('nmID')
        if not sku: continue
        
        # --- ЛОГИКА ЦЕН (ИСПРАВЛЕНО) ---
        # Сначала ищем в корне, если нет (0) - ищем в размерах
        base_price = int(item.get('price', 0))
        discount = int(item.get('discount', 0))

        # Если в корне пусто, лезем в размеры
        if base_price == 0 and 'sizes' in item and len(item['sizes']) > 0:
            first_size = item['sizes'][0]
            base_price = int(first_size.get('price', 0))
            # Скидка обычно общая, но иногда может быть внутри
            if discount == 0: 
                discount = int(first_size.get('discount', 0))

        # Эту цену установил селлер (до СПП)
        seller_price = int(base_price * (1 - discount / 100))
        
        # --- ФОТО (ИСПРАВЛЕНО) ---
        host = get_basket_number(sku)
        vol = sku // 100000
        part = sku // 1000
        photo_url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"

        # --- БД ---
        alert = alerts_map.get(sku)
        cost_price = costs_map.get(sku, 0)
        
        min_price = alert.min_price if alert else 0
        is_active = alert.is_active if alert else False
        
        # Статус
        status = "ok"
        diff_percent = 0
        
        if min_price > 0:
            if seller_price < min_price:
                status = "danger"
                diff_percent = round((1 - seller_price/min_price) * 100, 1)
            elif seller_price < (min_price * 1.05):
                status = "warning"
        
        result.append({
            "sku": sku,
            "photo": photo_url,
            "current_price": seller_price,
            "base_price": base_price,
            "discount": discount,
            "min_price": min_price,
            "cost_price": cost_price,
            "is_active": is_active,
            "status": status,
            "diff_percent": diff_percent,
            "name": item.get('vendorCode', f"Товар {sku}"), # Используем артикул продавца как название
            "brand": "WB"
        })

    # Сортировка: Danger -> Warning -> Active -> Others
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
        alert.last_check = datetime.utcnow()
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

@router.post("/refresh/{sku}")
async def force_refresh_price(
    sku: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Принудительное обновление для одного товара не всегда возможно через этот API 
    # (он отдает списки). Для UI просто вернем "ок", так как основной список обновляется при загрузке.
    return {"status": "ok"}