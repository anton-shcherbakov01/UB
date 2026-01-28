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
from mock_service import mock_service

# Import ProductParser
from parser_parts.product import ProductParser

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
    
    if user.wb_api_token == "DEMO":
        return mock_service.get_unit_economy()
    
    # 1. Получаем остатки из WB API
    try:
        stocks = await wb_api_service.get_my_stocks(user.wb_api_token)
        if not stocks: 
            return []
    except Exception as e:
        logger.error(f"❌ [UnitEconomy] Ошибка получения остатков: {e}")
        return []
    
    # 2. Группируем по SKU
    sku_map = {}
    for s in stocks:
        sku = s.get('nmId')
        if not sku: continue
        if sku not in sku_map:
            sku_map[sku] = {
                "sku": sku, 
                "quantity": 0, 
                "basic_price": s.get('Price', 0),
                "discount": s.get('Discount', 0),
                "brand": s.get('brand', s.get('Brand', '')),
                "subject": s.get('subject', s.get('Subject', ''))
            }
        sku_map[sku]['quantity'] += s.get('quantity', 0)
    
    skus = list(sku_map.keys())
    
    # 3. Загружаем расходы из БД и глобальные настройки из Redis
    costs_res = await db.execute(select(ProductCost).where(ProductCost.user_id == user.id, ProductCost.sku.in_(skus)))
    costs_map = {c.sku: c for c in costs_res.scalars().all()}
    
    r_client = get_redis_client()
    commissions_global, logistics_tariffs, products_meta_cache = {}, {}, {}

    if r_client:
        try:
            comm_data = r_client.get(f"meta:commissions:{user.id}")
            tariffs_data = r_client.get("meta:logistics_tariffs")
            
            # Если глобальных данных нет, запускаем синхронизацию в фоне
            if not comm_data or not tariffs_data:
                background_tasks.add_task(sync_product_metadata, user.id)

            commissions_global = json.loads(comm_data) if comm_data else {}
            logistics_tariffs = json.loads(tariffs_data) if tariffs_data else {}

            # Пакетное получение меты товаров и прогнозов
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
            logger.error(f"⚠️ [UnitEconomy] Ошибка кэша: {e}")

    # 4. ВОССТАНОВЛЕНИЕ МЕТАДАННЫХ (Лучшее из Варианта 1)
    parser = ProductParser()
    missing_meta_skus = []
    for sku in skus:
        meta = products_meta_cache.get(sku, {}).get("meta") or {}
        # Проверяем на отсутствие фото или старый формат ссылок
        if not meta.get('photo') or "basket" not in str(meta.get('photo', '')):
            missing_meta_skus.append(sku)

    if missing_meta_skus:
        logger.info(f"🕵️ [Parser] Догружаем данные для {len(missing_meta_skus)} SKU")
        parse_tasks = [parser._find_card_json(sku) for sku in missing_meta_skus]
        parsed_results = await asyncio.gather(*parse_tasks)
        
        if r_client:
            pipe = r_client.pipeline()
            for i, p_data in enumerate(parsed_results):
                sku = missing_meta_skus[i]
                if p_data:
                    current_cache = products_meta_cache.get(sku, {"meta": {}, "forecast": None})
                    meta = current_cache["meta"] or {}
                    # Обновляем поля из парсера
                    meta.update({
                        'photo': p_data.get('image_url') or get_wb_image_url(sku),
                        'name': p_data.get('imt_name') or meta.get('name'),
                        'brand': p_data.get('selling', {}).get('brand_name') or meta.get('brand')
                    })
                    current_cache['meta'] = meta
                    products_meta_cache[sku] = current_cache
                    pipe.setex(f"meta:product:{user.id}:{sku}", 86400, json.dumps(meta))
            pipe.execute()

    # 5. ФИНАНСОВЫЙ РАСЧЕТ (Лучшее из Варианта 2)
    result = []
    for sku, data in sku_map.items():
        try:
            cost_obj = costs_map.get(sku)
            cache_entry = products_meta_cache.get(sku, {})
            meta = cache_entry.get("meta") or {}
            forecast_json = cache_entry.get("forecast")

            # Гарантия наличия базовых полей для фронтенда
            if not meta.get('photo'): meta['photo'] = get_wb_image_url(sku)
            if not meta.get('name'): meta['name'] = data.get('subject') or f"Товар {sku}"
            if not meta.get('brand'): meta['brand'] = data.get('brand') or "Wildberries"

            # --- ЛОГИСТИКА ---
            if cost_obj and cost_obj.logistics is not None:
                log_val = cost_obj.logistics
            else:
                log_val = calculate_auto_logistics(meta.get('volume', 1.0), logistics_tariffs)

            # --- КОМИССИЯ ---
            if cost_obj and cost_obj.commission_percent is not None:
                comm_pct = cost_obj.commission_percent
            else:
                comm_pct = commissions_global.get(str(meta.get('subject_id', '')), 25.0)

            # --- ЮНИТ-ЭКОНОМИКА ---
            price_raw = data['basic_price']
            discount = data['discount']
            # Цена после скидки продавца (то, что платит покупатель без учета СПП)
            selling_price = price_raw * (1 - discount / 100)
            
            cost_price = cost_obj.cost_price if cost_obj else 0
            comm_rub = selling_price * (comm_pct / 100)
            
            profit = selling_price - comm_rub - log_val - cost_price
            roi = round((profit / cost_price * 100), 1) if cost_price > 0 else 0
            margin = int((profit / selling_price * 100)) if selling_price > 0 else 0

            # --- ПОСТАВКИ ---
            supply_data = {"status": "unknown", "metrics": {"current_stock": data['quantity']}}
            if forecast_json:
                try:
                    supply_data = analysis_service.calculate_supply_metrics(
                        current_stock=data['quantity'],
                        sales_history=[],
                        forecast_data=forecast_json
                    )
                except: pass

            result.append({
                "sku": sku,
                "quantity": data['quantity'],
                "price_structure": {
                    "basic": int(price_raw),
                    "discount": int(discount),
                    "selling": int(selling_price)
                },
                "cost_price": cost_price,
                "logistics": log_val,
                "commission_percent": comm_pct,
                "unit_economy": {
                    "profit": int(profit),
                    "roi": roi,
                    "margin": margin
                },
                "supply": supply_data,
                "meta": meta 
            })
        except Exception as e:
            logger.error(f"❌ [UnitEconomy] Ошибка SKU {sku}: {e}")

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
    if user.wb_api_token == "DEMO":
        # Генерируем 30 или 90 дней
        return {
            "plan": user.subscription_plan,
            "date_from": date_from_dt.isoformat(),
            "date_to": date_to_dt.isoformat(),
            "data": mock_service.get_pnl_data(30)
        }
    
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