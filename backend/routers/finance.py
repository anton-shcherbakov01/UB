import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
import io
import asyncio
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from database import get_db, User, ProductCost
from dependencies import get_current_user, get_redis_client, check_telegram_auth
from dependencies.quota import QuotaCheck
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

# --- Helper: Force Generate WB Image URL ---
def get_wb_image_url(nm_id: int) -> str:
    """
    Генерирует ссылку на фото WB, используя актуальную карту корзин (vol).
    Поддерживает новые сервера вплоть до basket-32.
    """
    try:
        nm_id = int(nm_id)
        vol = nm_id // 100000
        part = nm_id // 1000
        basket = "01"

        if 0 <= vol <= 143: basket = "01"
        elif 144 <= vol <= 287: basket = "02"
        elif 288 <= vol <= 431: basket = "03"
        elif 432 <= vol <= 719: basket = "04"
        elif 720 <= vol <= 1007: basket = "05"
        elif 1008 <= vol <= 1061: basket = "06"
        elif 1062 <= vol <= 1115: basket = "07"
        elif 1116 <= vol <= 1169: basket = "08"
        elif 1170 <= vol <= 1313: basket = "09"
        elif 1314 <= vol <= 1601: basket = "10"
        elif 1602 <= vol <= 1655: basket = "11"
        elif 1656 <= vol <= 1919: basket = "12"
        elif 1920 <= vol <= 2045: basket = "13"
        elif 2046 <= vol <= 2189: basket = "14"
        elif 2190 <= vol <= 2405: basket = "15"
        elif 2406 <= vol <= 2621: basket = "16"
        elif 2622 <= vol <= 2837: basket = "17"
        elif 2838 <= vol <= 3053: basket = "18"
        elif 3054 <= vol <= 3269: basket = "19"
        elif 3270 <= vol <= 3485: basket = "20"
        elif 3486 <= vol <= 3701: basket = "21"
        elif 3702 <= vol <= 3917: basket = "22"
        elif 3918 <= vol <= 4133: basket = "23"
        elif 4134 <= vol <= 4349: basket = "24"
        elif 4350 <= vol <= 4565: basket = "25"
        elif 4566 <= vol <= 4781: basket = "26"
        elif 4782 <= vol <= 4997: basket = "27"
        elif 4998 <= vol <= 5213: basket = "28"
        elif 5214 <= vol <= 5429: basket = "29"
        elif 5430 <= vol <= 5645: basket = "30"
        elif 5646 <= vol <= 5861: basket = "31"
        else: basket = "32"

        return f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/images/c246x328/1.webp"
    except:
        return ""

# --- Helper for PDF Auth ---
async def get_user_via_query(request: Request, db: AsyncSession = Depends(get_db)):
    x_tg_data = request.query_params.get("x_tg_data")
    if not x_tg_data:
        raise HTTPException(status_code=401, detail="Missing auth data")
    
    user = await check_telegram_auth(x_tg_data, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid auth data")
    return user

def calculate_auto_logistics(volume_l: float, tariffs_map: dict) -> float:
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
                "discount": s.get('Discount', 0),    # Скидка продавца
                "brand": s.get('brand', s.get('Brand', '')), # Пробуем достать бренд из остатков
                "subject": s.get('subject', s.get('Subject', ''))
            }
        sku_map[sku]['quantity'] += s.get('quantity', 0)
    
    skus = list(sku_map.keys())
    
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

            # Фоновое обновление если кэш пуст
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
            
            # --- ГАРАНТИЯ META ДАННЫХ (Fix) ---
            # Принудительно генерируем фото, если нет в кэше
            if not meta.get('photo'):
                meta['photo'] = get_wb_image_url(sku)
            
            # Принудительно заполняем название и бренд, если пусто
            if not meta.get('name'):
                meta['name'] = data.get('subject') or f"Товар {sku}"
            
            if not meta.get('brand'):
                meta['brand'] = data.get('brand') or "Wildberries"

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
                "supply": supply_data,
                "meta": meta 
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

@router.post("/finance/sync/pnl")
async def sync_pnl_data(
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not user.wb_api_token:
        raise HTTPException(status_code=400, detail="No WB Token")
    
    from tasks.report_loader import load_realization_reports_task
    background_tasks.add_task(load_realization_reports_task, user.id, user.wb_api_token, days=90)
    return {"status": "started", "message": "P&L data sync started (last 90 days)"}

@router.get("/finance/pnl")
async def get_pnl_data(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    from config.plans import has_feature
    now = datetime.utcnow()
    
    if user.subscription_plan == "start":
        if not has_feature(user.subscription_plan, "pnl_demo"):
            raise HTTPException(status_code=403, detail="P&L feature requires upgrade")
        yesterday = now - timedelta(days=1)
        date_from_dt = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        date_to_dt = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    else:
        if not has_feature(user.subscription_plan, "pnl_full"):
            raise HTTPException(status_code=403, detail="P&L feature requires upgrade")
        
        if date_from:
            try:
                if 'T' in date_from:
                     date_from_dt = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                else:
                     date_from_dt = datetime.strptime(date_from, "%Y-%m-%d")
            except:
                date_from_dt = now - timedelta(days=30)
        else:
            date_from_dt = now - timedelta(days=30)
        
        if date_to:
            try:
                if 'T' in date_to:
                    date_to_dt = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                else:
                    date_to_dt = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59)
            except:
                date_to_dt = now
        else:
            date_to_dt = now
    
    try:
        pnl_data = await analysis_service.get_pnl_data(user.id, date_from_dt, date_to_dt, db)
    except Exception as e:
        logger.error(f"Error fetching P&L data from service: {e}")
        pnl_data = []

    return {
        "plan": user.subscription_plan,
        "date_from": date_from_dt.isoformat(),
        "date_to": date_to_dt.isoformat(),
        "data": pnl_data 
    }

executor = ThreadPoolExecutor(max_workers=2)

@router.get("/finance/report/pnl-pdf")
async def generate_pnl_pdf(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user: User = Depends(get_user_via_query),
    db: AsyncSession = Depends(get_db)
):
    from config.plans import has_feature
    now = datetime.utcnow()
    date_from_dt = now - timedelta(days=30) 
    date_to_dt = now
    if date_from:
        try: date_from_dt = datetime.fromisoformat(date_from.replace('Z', ''))
        except: pass
    if date_to:
        try: date_to_dt = datetime.fromisoformat(date_to.replace('Z', ''))
        except: pass

    pnl_data = await analysis_service.get_pnl_data(user.id, date_from_dt, date_to_dt, db)
    
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
        headers={'Content-Disposition': f'attachment; filename="pnl_report.pdf"'}
    )

@router.get("/finance/report/unit-economy-pdf")
async def generate_unit_economy_pdf(
    user: User = Depends(get_user_via_query),
    db: AsyncSession = Depends(get_db)
):
    from config.plans import has_feature
    if not has_feature(user.subscription_plan, "unit_economy"):
         raise HTTPException(status_code=403, detail="Unit Economy requires upgrade")

    background_tasks = BackgroundTasks()
    unit_data = await get_my_products_finance(background_tasks, user, db)
    
    from services.pdf_generator import pdf_generator
    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(
        executor,
        pdf_generator.create_unit_economy_pdf,
        unit_data
    )
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type='application/pdf',
        headers={
            'Content-Disposition': f'attachment; filename="unit_economy.pdf"',
            'Content-Length': str(len(pdf_bytes)),
            'Cache-Control': 'no-cache'
        }
    )