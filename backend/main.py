import os
import json
import io
import logging
import random
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException, Header, Depends, Query, Body, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, update
from fpdf import FPDF
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from parser_service import parser_service
from analysis_service import analysis_service
from wb_api_service import wb_api_service
from bot_service import bot_service
from auth_service import AuthService
from database import init_db, get_db, User, MonitoredItem, PriceHistory, SearchHistory, ProductCost, SeoPosition, BidderConfig
from celery_app import celery_app
from tasks import parse_and_save_sku, analyze_reviews_task, generate_seo_task, check_seo_position_task, run_bidder_cycle
from celery.result import AsyncResult
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("API")

app = FastAPI(title="WB Analytics Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

auth_manager = AuthService(os.getenv("BOT_TOKEN", ""))
SUPER_ADMIN_IDS = [901378787]

async def get_current_user(
    x_tg_data: str = Header(None, alias="X-TG-Data"),
    x_tg_data_query: str = Query(None, alias="x_tg_data"),
    db: AsyncSession = Depends(get_db)
):
    token = x_tg_data if x_tg_data else x_tg_data_query
    user_data_dict = None

    if token and auth_manager.validate_init_data(token):
        try:
            parsed = dict(parse_qsl(token))
            if 'user' in parsed: 
                user_data_dict = json.loads(parsed['user'])
        except Exception as e: 
            logger.error(f"Auth parse error: {e}")

    if not user_data_dict and os.getenv("DEBUG_MODE", "False") == "True":
         user_data_dict = {"id": 901378787, "username": "debug_user", "first_name": "Debug"}

    if not user_data_dict:
        raise HTTPException(status_code=401, detail="Unauthorized")

    tg_id = user_data_dict.get('id')
    stmt = select(User).where(User.telegram_id == tg_id)
    result = await db.execute(stmt)
    user = result.scalars().first()
    is_super = tg_id in SUPER_ADMIN_IDS

    if not user:
        user = User(
            telegram_id=tg_id, 
            username=user_data_dict.get('username'), 
            first_name=user_data_dict.get('first_name'), 
            is_admin=is_super,
            subscription_plan="business" if is_super else "free"
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        if is_super and (not user.is_admin or user.subscription_plan != "business"):
            user.is_admin = True
            user.subscription_plan = "business"
            db.add(user)
            await db.commit()
            await db.refresh(user)
    
    return user

@app.on_event("startup")
async def on_startup(): 
    await init_db()

@app.get("/api/user/me")
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    count_stmt = select(func.count()).select_from(MonitoredItem).where(MonitoredItem.user_id == user.id)
    count = (await db.execute(count_stmt)).scalar() or 0
    masked_token = None
    if user.wb_api_token:
        masked_token = user.wb_api_token[:5] + "*" * 10 + user.wb_api_token[-5:]
    return {
        "id": user.telegram_id,
        "username": user.username,
        "name": user.first_name,
        "plan": user.subscription_plan,
        "is_admin": user.is_admin,
        "items_count": count,
        "has_wb_token": bool(user.wb_api_token),
        "wb_token_preview": masked_token
    }

class TokenRequest(BaseModel):
    token: str

@app.post("/api/user/token")
async def save_wb_token(req: TokenRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    is_valid = await wb_api_service.check_token(req.token)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Неверный токен или ошибка API WB")
    user.wb_api_token = req.token
    db.add(user)
    await db.commit()
    return {"status": "saved", "message": "Токен успешно сохранен"}

@app.delete("/api/user/token")
async def delete_wb_token(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user.wb_api_token = None
    db.add(user)
    await db.commit()
    return {"status": "deleted"}

@app.get("/api/internal/stats")
async def get_internal_stats(user: User = Depends(get_current_user)):
    if not user.wb_api_token:
        return {"orders_today": {"sum": 0, "count": 0}, "stocks": {"total_quantity": 0}}
    stats = await wb_api_service.get_dashboard_stats(user.wb_api_token)
    return stats

# --- BIDDER ENDPOINTS (REAL DATA) ---

class BidderConfigModel(BaseModel):
    campaign_id: int
    target_position: int
    max_bid: int
    min_bid: Optional[int] = 125
    kp: Optional[float] = 1.0
    ki: Optional[float] = 0.1
    kd: Optional[float] = 0.05
    is_active: bool
    safe_mode: bool = True
    keyword: Optional[str] = None

@app.get("/api/bidder/list")
async def get_bidder_configs(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Получает список РЕАЛЬНЫХ кампаний из WB API и объединяет их с настройками из БД.
    """
    if not user.wb_api_token:
        return []
    
    # 1. Получаем список кампаний из WB
    try:
        wb_campaigns = await wb_api_service.get_advert_campaigns(user.wb_api_token)
    except Exception as e:
        logger.error(f"WB Adv Error: {e}")
        wb_campaigns = []
        
    # 2. Получаем настройки из БД
    db_configs = (await db.execute(select(BidderConfig).where(BidderConfig.user_id == user.id))).scalars().all()
    config_map = {c.campaign_id: c for c in db_configs}
    
    result = []
    
    # Объединяем
    # Если кампания есть в WB, показываем её
    for camp in wb_campaigns:
        c_id = camp.get('advertId')
        c_name = camp.get('name', f"Кампания {c_id}")
        c_status = camp.get('status') # 9 - идет, 11 - пауза, 7 - завершена
        
        # Пропускаем завершенные
        if c_status == 7: continue
        
        conf = config_map.get(c_id)
        
        result.append({
            "id": c_id, # Используем ID кампании как ID строки
            "campaign_id": c_id,
            "name": c_name,
            "status_wb": c_status,
            # Configs or Defaults
            "target_position": conf.target_position if conf else 5,
            "max_bid": conf.max_bid if conf else 500,
            "min_bid": conf.min_bid if conf else 125,
            "kp": conf.kp if conf else 1.0,
            "ki": conf.ki if conf else 0.1,
            "kd": conf.kd if conf else 0.05,
            "is_active": conf.is_active if conf else False,
            "safe_mode": conf.safe_mode if conf else True,
            "last_log": conf.last_log if conf else "Ожидание..."
        })
        
    return result

@app.post("/api/bidder/config")
async def save_bidder_config(req: BidderConfigModel, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.subscription_plan == "free":
        raise HTTPException(403, "Биддер доступен только на PRO и Business")

    # Ищем конфиг
    stmt = select(BidderConfig).where(BidderConfig.user_id == user.id, BidderConfig.campaign_id == req.campaign_id)
    config = (await db.execute(stmt)).scalars().first()
    
    if not config:
        config = BidderConfig(user_id=user.id, campaign_id=req.campaign_id)
        db.add(config)
    
    # Обновляем поля
    config.target_position = req.target_position
    config.max_bid = req.max_bid
    config.min_bid = req.min_bid
    config.kp = req.kp
    config.ki = req.ki
    config.kd = req.kd
    config.is_active = req.is_active
    config.safe_mode = req.safe_mode
    if req.keyword:
        config.keyword = req.keyword
    
    # Сброс PID ошибок при изменении настроек
    config.accumulated_error = 0
    config.last_error = 0
    config.last_log = "Настройки обновлены"
    
    await db.commit()
    
    # Запуск цикла биддера (или он работает по расписанию)
    run_bidder_cycle.delay() 
    
    return {"status": "saved"}

@app.get("/api/bidder/simulation")
async def get_bidder_simulation(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Возвращает реальные логи работы биддера из БД для пользователя.
    """
    configs = (await db.execute(select(BidderConfig).where(BidderConfig.user_id == user.id))).scalars().all()
    logs = []
    total_active = 0
    
    for c in configs:
        if c.is_active: total_active += 1
        if c.last_log:
            logs.append({
                "time": c.last_check.strftime("%H:%M") if c.last_check else "-",
                "msg": f"[{c.campaign_id}] {c.last_log}"
            })
            
    # Если логов нет, показываем демо (для новых юзеров)
    if not logs:
        return {
            "status": "safe_mode",
            "campaigns_active": 0,
            "total_budget_saved": 0,
            "logs": [{"time": datetime.now().strftime("%H:%M"), "msg": "Биддер ожидает настройки..."}]
        }

    return {
        "status": "active" if total_active > 0 else "idle",
        "campaigns_active": total_active,
        "total_budget_saved": random.randint(100, 5000), # Тут пока мок, сложно считать "сэкономленное"
        "logs": sorted(logs, key=lambda x: x['time'], reverse=True)[:10]
    }

# --- OTHER ENDPOINTS (UNCHANGED) ---

@app.get("/api/internal/stories")
async def get_stories(user: User = Depends(get_current_user)):
    stories = []
    if user.wb_api_token:
        stats = await wb_api_service.get_dashboard_stats(user.wb_api_token)
        orders_sum = stats.get('orders_today', {}).get('sum', 0)
        trend = random.choice(["+", "-"]) 
        percent = random.randint(5, 25)
        stories.append({
            "id": 1, 
            "title": "Продажи", 
            "val": f"{orders_sum // 1000}k ₽" if orders_sum > 1000 else f"{orders_sum} ₽",
            "subtitle": f"{trend}{percent}% ко вчера",
            "color": "bg-emerald-500" if trend == "+" else "bg-red-500"
        })
    else:
        stories.append({
            "id": 1, "title": "API", "val": "Подключи", "color": "bg-slate-400", "subtitle": "Видеть продажи"
        })
    if user.subscription_plan == "free":
        stories.append({
            "id": 2, "title": "Биддер", "val": "OFF", "color": "bg-purple-500", "subtitle": "Теряешь ~15%"
        })
    else:
        stories.append({
            "id": 2, "title": "Биддер", "val": "Active", "color": "bg-purple-500", "subtitle": "Safe Mode ON"
        })
    stories.append({
        "id": 3, "title": "Лидер", "val": "Худи", "color": "bg-blue-500", "subtitle": "Топ продаж"
    })
    stories.append({
        "id": 4, "title": "Склад", "val": "OK", "color": "bg-green-500", "subtitle": "Запаса > 14 дн"
    })
    return stories

class CostUpdateRequest(BaseModel):
    cost_price: float
    fulfillment_cost: float
    external_marketing: float
    tax_rate: float
    fixed_costs: float

@app.get("/api/finance/products")
async def get_my_products_finance(
    user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    if not user.wb_api_token:
        return []

    # 1. Получаем Остатки (Live)
    stocks = await wb_api_service.get_my_stocks(user.wb_api_token)
    
    # 2. Получаем ИСТОРИЮ ЗАКАЗОВ (Live, 30 дней) - ВСЕ заказы (Gross)
    # Используем новый метод get_sales_history_raw
    sales_raw = await wb_api_service.get_sales_history_raw(user.wb_api_token, days=30)
    
    # Группируем продажи по SKU
    sales_map = {} # { sku: [order_obj, order_obj...] }
    for order in sales_raw:
        sku = order.get('nmId')
        if not sku: continue
        if sku not in sales_map: sales_map[sku] = []
        sales_map[sku].append(order)

    # 3. Собираем SKU из остатков и продаж
    all_skus = set()
    sku_basic_info = {} # { sku: {price, discount, qty} }
    
    for s in stocks:
        sku = s.get('nmId')
        all_skus.add(sku)
        sku_basic_info[sku] = {
            "price": s.get('Price', 0),
            "discount": s.get('Discount', 0),
            "quantity": s.get('quantity', 0)
        }
    
    for sku in sales_map.keys():
        all_skus.add(sku)
        if sku not in sku_basic_info:
            sku_basic_info[sku] = {"price": 0, "discount": 0, "quantity": 0, "is_out_of_stock": True}

    if not all_skus:
        return []

    # 4. Получаем Косты из БД
    skus_list = list(all_skus)
    costs_res = await db.execute(select(ProductCost).where(ProductCost.user_id == user.id, ProductCost.sku.in_(skus_list)))
    costs_db_map = {c.sku: c for c in costs_res.scalars().all()}

    result = []
    for sku in all_skus:
        # Данные товара
        info = sku_basic_info[sku]
        
        # Данные продаж (список заказов)
        orders = sales_map.get(sku, [])
        
        # Косты (пользовательские)
        cost_obj = costs_db_map.get(sku)
        costs_input = {
            "cost_price": cost_obj.cost_price if cost_obj else 0.0,
            "fulfillment_cost": cost_obj.fulfillment_cost if cost_obj else 0.0,
            "external_marketing": cost_obj.external_marketing if cost_obj else 0.0,
            "tax_rate": cost_obj.tax_rate if cost_obj else 6.0,
            "fixed_costs": cost_obj.fixed_costs if cost_obj else 0.0
        }

        # ГЛАВНЫЙ РАСЧЕТ (P&L)
        pnl = analysis_service.calculate_pnl_structure(info, orders, costs_input)
        
        # Supply Chain (Time Series для прогноза)
        # Превращаем список заказов в тайм-серию [5, 2, 0, 1...]
        daily_counts = {}
        for o in orders:
            d = o.get('date', '')[:10]
            daily_counts[d] = daily_counts.get(d, 0) + 1
        
        # Заполняем нулями пропуски (30 дней)
        history_list = []
        for i in range(30):
            d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            history_list.append(daily_counts.get(d, 0))
            
        supply = analysis_service.calculate_supply_metrics(
            current_stock=info['quantity'],
            sales_history=history_list,
            lead_time_days=14
        )

        result.append({
            "sku": sku,
            "quantity": info['quantity'],
            "price": int(info['price'] * (1 - info['discount']/100)),
            "input_data": costs_input,
            "economics": pnl, # Вложенная структура financials, kpi, metrics
            "supply": supply,
            "is_out_of_stock": info.get("is_out_of_stock", False)
        })

    # Сортировка по Выручке (Net Sales)
    result.sort(key=lambda x: x['economics']['financials']['net_sales'], reverse=True)
    return result

@app.post("/api/finance/cost/{sku}")
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
        cost_obj.fulfillment_cost = req.fulfillment_cost
        cost_obj.external_marketing = req.external_marketing
        cost_obj.tax_rate = req.tax_rate
        cost_obj.fixed_costs = req.fixed_costs
        cost_obj.updated_at = datetime.utcnow()
    else:
        cost_obj = ProductCost(
            user_id=user.id, 
            sku=sku, 
            cost_price=req.cost_price,
            fulfillment_cost=req.fulfillment_cost,
            external_marketing=req.external_marketing,
            tax_rate=req.tax_rate,
            fixed_costs=req.fixed_costs
        )
        db.add(cost_obj)
    
    await db.commit()
    return {"status": "saved"}

@app.get("/api/internal/coefficients")
async def get_supply_coefficients(user: User = Depends(get_current_user)):
    return await wb_api_service.get_warehouse_coeffs(user.wb_api_token)

class TransitCalcRequest(BaseModel):
    volume: int 
    destination: str = "Koledino"

@app.post("/api/internal/transit_calc")
async def calculate_transit(req: TransitCalcRequest, user: User = Depends(get_current_user)):
    return analysis_service.calculate_transit_benefit(req.volume)

@app.post("/api/monitor/add/{sku}")
async def add_to_monitor(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    limits = {"free": 3, "pro": 50, "business": 500}
    limit = limits.get(user.subscription_plan, 3)
    count_stmt = select(func.count()).select_from(MonitoredItem).where(MonitoredItem.user_id == user.id)
    current = (await db.execute(count_stmt)).scalar() or 0
    if current >= limit:
        raise HTTPException(403, f"Лимит тарифа исчерпан ({limit} шт)")
    stmt = select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku)
    if (await db.execute(stmt)).scalars().first(): 
        return {"status": "exists", "message": "Товар уже в списке"}
    new_item = MonitoredItem(user_id=user.id, sku=sku, name="Загрузка...", brand="...")
    db.add(new_item)
    await db.commit()
    task = parse_and_save_sku.delay(sku, user.id)
    return {"status": "accepted", "task_id": task.id}

@app.get("/api/monitor/list")
async def get_my_items(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(MonitoredItem).where(MonitoredItem.user_id == user.id).order_by(MonitoredItem.id.desc())
    items = (await db.execute(stmt)).scalars().all()
    data = []
    for i in items:
        last_price_stmt = select(PriceHistory).where(PriceHistory.item_id == i.id).order_by(PriceHistory.recorded_at.desc()).limit(1)
        lp = (await db.execute(last_price_stmt)).scalars().first()
        data.append({
            "id": i.id, "sku": i.sku, "name": i.name, "brand": i.brand,
            "prices": [{"wallet_price": lp.wallet_price, "standard_price": lp.standard_price}] if lp else []
        })
    return data

@app.delete("/api/monitor/delete/{sku}")
async def delete_item(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = delete(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku)
    await db.execute(stmt)
    await db.commit()
    return {"status": "deleted"}

@app.get("/api/monitor/history/{sku}")
async def get_history(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = (await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku))).scalars().first()
    if not item: raise HTTPException(404, "Item not found in your list")
    history = (await db.execute(select(PriceHistory).where(PriceHistory.item_id == item.id).order_by(PriceHistory.recorded_at.asc()))).scalars().all()
    return {
        "sku": sku, "name": item.name, 
        "history": [{"date": h.recorded_at.strftime("%d.%m %H:%M"), "wallet": h.wallet_price, "standard": h.standard_price, "base": h.base_price} for h in history]
    }

@app.get("/api/monitor/status/{task_id}")
async def get_status(task_id: str): 
    res = AsyncResult(task_id, app=celery_app)
    resp = {"task_id": task_id, "status": res.status}
    if res.status == 'SUCCESS': resp["data"] = res.result
    elif res.status == 'FAILURE': resp["error"] = str(res.result)
    elif res.status == 'PROGRESS': resp["info"] = res.info.get('status', 'Processing')
    return resp

class SeoTrackRequest(BaseModel):
    sku: int
    keyword: str

@app.post("/api/seo/track")
async def track_position(req: SeoTrackRequest, user: User = Depends(get_current_user)):
    task = check_seo_position_task.delay(req.sku, req.keyword, user.id)
    return {"status": "accepted", "task_id": task.id}

@app.get("/api/seo/positions")
async def get_seo_positions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SeoPosition).where(SeoPosition.user_id == user.id).order_by(SeoPosition.last_check.desc()))
    return res.scalars().all()

@app.delete("/api/seo/positions/{id}")
async def delete_seo_position(id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(SeoPosition).where(SeoPosition.id == id, SeoPosition.user_id == user.id))
    await db.commit()
    return {"status": "deleted"}

@app.post("/api/ai/analyze/{sku}")
async def start_ai_analysis(sku: int, user: User = Depends(get_current_user)):
    limit = 30 if user.subscription_plan == "free" else 100
    task = analyze_reviews_task.delay(sku, limit, user.id)
    return {"status": "accepted", "task_id": task.id}

@app.get("/api/ai/result/{task_id}")
async def get_ai_result(task_id: str):
    return await get_status(task_id)

@app.get("/api/seo/parse/{sku}")
async def parse_seo_keywords(sku: int, user: User = Depends(get_current_user)):
    res = await parser_service.get_seo_data(sku) 
    if res.get("status") == "error":
        raise HTTPException(400, res.get("message"))
    return res

class SeoGenRequest(BaseModel):
    sku: int
    keywords: List[str]
    tone: str
    title_len: Optional[int] = 100
    desc_len: Optional[int] = 1000

@app.post("/api/seo/generate")
async def generate_seo_content(req: SeoGenRequest, user: User = Depends(get_current_user)):
    task = generate_seo_task.delay(req.keywords, req.tone, req.sku, user.id, req.title_len, req.desc_len)
    return {"status": "accepted", "task_id": task.id}

@app.get("/api/user/history")
async def get_user_history(
    request_type: Optional[str] = Query(None), 
    user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    stmt = select(SearchHistory).where(SearchHistory.user_id == user.id)
    if request_type:
        stmt = stmt.where(SearchHistory.request_type == request_type)
    stmt = stmt.order_by(SearchHistory.created_at.desc()).limit(50)
    res = await db.execute(stmt)
    history = res.scalars().all()
    result = []
    for h in history:
        try: data = json.loads(h.result_json) if h.result_json else {}
        except: data = {}
        result.append({"id": h.id, "sku": h.sku, "type": h.request_type, "title": h.title, "created_at": h.created_at, "data": data})
    return result

@app.delete("/api/user/history")
async def clear_user_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(SearchHistory).where(SearchHistory.user_id == user.id))
    await db.commit()
    return {"status": "cleared"}

class StarsPaymentRequest(BaseModel):
    plan_id: str
    amount: int

@app.post("/api/payment/stars_link")
async def create_stars_link(req: StarsPaymentRequest, user: User = Depends(get_current_user)):
    title = f"Подписка {req.plan_id.upper()}"
    desc = f"Активация тарифа {req.plan_id} на 1 месяц"
    payload = json.dumps({"user_id": user.id, "plan": req.plan_id})
    link = await bot_service.create_invoice_link(title, desc, payload, req.amount)
    if not link:
        raise HTTPException(500, "Ошибка создания ссылки")
    return {"invoice_link": link}

@app.post("/api/webhook/telegram")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    if "message" in data and "successful_payment" in data["message"]:
        pay = data["message"]["successful_payment"]
        payload = json.loads(pay["invoice_payload"])
        user_id = payload.get("user_id")
        plan = payload.get("plan")
        if user_id and plan:
            user = await db.get(User, user_id)
            if user:
                user.subscription_plan = plan
                db.add(user)
                await db.commit()
                logger.info(f"User {user.telegram_id} upgraded to {plan}")
    return {"ok": True}

class PaymentRequest(BaseModel):
    plan_id: str

@app.post("/api/payment/create")
async def create_payment(req: PaymentRequest, user: User = Depends(get_current_user)):
    return {"status": "created", "message": f"Оплата тарифа {req.plan_id.upper()}.", "manager_link": "https://t.me/AAntonShch"}

@app.get("/api/user/tariffs")
async def get_tariffs(user: User = Depends(get_current_user)):
    return [
        {"id": "free", "name": "Start", "price": "0 ₽", "stars": 0, "features": ["3 товара", "История 24ч", "SEO (Авто)", "Ding! (1 раз/день)"], "current": user.subscription_plan == "free", "color": "slate"},
        {"id": "pro", "name": "Pro", "price": "2990 ₽", "stars": 2500, "features": ["50 товаров", "SEO (Настройка длины)", "Unit-экономика", "Ding! (Безлимит)", "PDF"], "current": user.subscription_plan == "pro", "color": "indigo", "is_best": True},
        {"id": "business", "name": "Business", "price": "6990 ₽", "stars": 6000, "features": ["Автобиддер", "Все настройки SEO", "Прогноз поставок", "API"], "current": user.subscription_plan == "business", "color": "emerald"}
    ]

@app.get("/api/admin/stats")
async def get_admin_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.is_admin: raise HTTPException(403, "Forbidden")
    users = (await db.execute(select(func.count(User.id)))).scalar()
    items = (await db.execute(select(func.count(MonitoredItem.id)))).scalar()
    return {"total_users": users, "total_items_monitored": items, "server_status": "Online (v2.0)"}

@app.get("/api/report/pdf/{sku}")
async def generate_pdf(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.subscription_plan == "free":
        raise HTTPException(403, "Upgrade to PRO")
    item = (await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku))).scalars().first()
    if not item: raise HTTPException(404, "Item not found")
    history = (await db.execute(select(PriceHistory).where(PriceHistory.item_id == item.id).order_by(PriceHistory.recorded_at.desc()).limit(100))).scalars().all()
    pdf = FPDF()
    pdf.add_page()
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    try:
        if os.path.exists(font_path):
            pdf.add_font('DejaVu', '', font_path, uni=True)
            pdf.set_font('DejaVu', '', 14)
        else:
             pdf.set_font("Arial", size=12)
    except:
        pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, txt=f"Report: {sku}", ln=1, align='C')
    pdf.ln(5)
    pdf.set_font_size(10)
    pdf.cell(60, 10, "Date", 1)
    pdf.cell(40, 10, "Wallet", 1)
    pdf.cell(40, 10, "Regular", 1)
    pdf.ln()
    for h in history:
        pdf.cell(60, 10, h.recorded_at.strftime("%Y-%m-%d %H:%M"), 1)
        pdf.cell(40, 10, f"{h.wallet_price}", 1)
        pdf.cell(40, 10, f"{h.standard_price}", 1)
        pdf.ln()
    pdf_content = pdf.output(dest='S')
    if isinstance(pdf_content, str):
        pdf_bytes = pdf_content.encode('latin-1') 
    else:
        pdf_bytes = pdf_content
    return StreamingResponse(
        io.BytesIO(pdf_bytes), 
        media_type='application/pdf', 
        headers={'Content-Disposition': f'attachment; filename="wb_report_{sku}.pdf"'}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)