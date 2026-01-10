import os
import json
import io
import logging
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException, Header, Depends, Query, Body, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, update
from fpdf import FPDF
from pydantic import BaseModel
from typing import List, Optional

from parser_service import parser_service
from analysis_service import analysis_service
from wb_api_service import wb_api_service
from bot_service import bot_service
from auth_service import AuthService
from database import init_db, get_db, User, MonitoredItem, PriceHistory, SearchHistory, ProductCost
from celery_app import celery_app
from tasks import parse_and_save_sku, analyze_reviews_task, generate_seo_task
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

async def get_current_user(x_tg_data: str = Header(None, alias="X-TG-Data"), x_tg_data_query: str = Query(None, alias="x_tg_data"), db: AsyncSession = Depends(get_db)):
    token = x_tg_data if x_tg_data else x_tg_data_query
    user_data_dict = None
    if token and auth_manager.validate_init_data(token):
        try: user_data_dict = json.loads(dict(parse_qsl(token)).get('user', '{}'))
        except: pass
    if not user_data_dict and os.getenv("DEBUG_MODE") == "True":
         user_data_dict = {"id": 901378787, "username": "debug_user", "first_name": "Debug"}
    if not user_data_dict: raise HTTPException(401, "Unauthorized")

    tg_id = user_data_dict.get('id')
    user = (await db.execute(select(User).where(User.telegram_id == tg_id))).scalars().first()
    is_super = tg_id in SUPER_ADMIN_IDS
    
    if not user:
        user = User(telegram_id=tg_id, username=user_data_dict.get('username'), first_name=user_data_dict.get('first_name'), is_admin=is_super, subscription_plan="business" if is_super else "free")
        db.add(user); await db.commit(); await db.refresh(user)
    elif is_super and (not user.is_admin or user.subscription_plan != "business"):
        user.is_admin = True; user.subscription_plan = "business"; db.add(user); await db.commit(); await db.refresh(user)
    return user

@app.on_event("startup")
async def on_startup(): await init_db()

@app.get("/api/user/me")
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    count = (await db.execute(select(func.count()).select_from(MonitoredItem).where(MonitoredItem.user_id == user.id))).scalar() or 0
    masked_token = (user.wb_api_token[:5] + "*" * 10 + user.wb_api_token[-5:]) if user.wb_api_token else None
    return {"id": user.telegram_id, "username": user.username, "name": user.first_name, "plan": user.subscription_plan, "is_admin": user.is_admin, "items_count": count, "has_wb_token": bool(user.wb_api_token), "wb_token_preview": masked_token}

# --- WB TOKEN ---
class TokenRequest(BaseModel): token: str
@app.post("/api/user/token")
async def save_wb_token(req: TokenRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not await wb_api_service.check_token(req.token): raise HTTPException(400, "Неверный токен")
    user.wb_api_token = req.token; db.add(user); await db.commit()
    return {"status": "saved"}

@app.delete("/api/user/token")
async def delete_wb_token(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user.wb_api_token = None; db.add(user); await db.commit()
    return {"status": "deleted"}

@app.get("/api/internal/stats")
async def get_internal_stats(user: User = Depends(get_current_user)):
    if not user.wb_api_token: raise HTTPException(400, "Токен не подключен")
    return await wb_api_service.get_dashboard_stats(user.wb_api_token)

# --- FINANCE & INTERNAL PRODUCTS (NEW) ---

class CostUpdateRequest(BaseModel): cost_price: int

@app.get("/api/internal/products")
async def get_my_products_finance(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Получение списка СВОИХ товаров для Unit-экономики.
    1. Берем остатки из WB API (чтобы получить SKU).
    2. Берем сохраненные Cost Price из БД.
    3. Считаем P&L.
    """
    if not user.wb_api_token: return []
    
    # 1. Получаем сырые данные об остатках (там есть SKU и Цена продажи)
    stocks = await wb_api_service.get_my_stocks(user.wb_api_token)
    if not stocks: return []
    
    # Группируем по nmId (SKU), так как остатки разбиты по складам/размерам
    sku_map = {}
    for s in stocks:
        sku = s.get('nmId')
        if sku not in sku_map:
            sku_map[sku] = {
                "sku": sku, 
                "quantity": 0, 
                "price": s.get('Price', 0), # Цена до скидки
                "discount": s.get('Discount', 0)
            }
        sku_map[sku]['quantity'] += s.get('quantity', 0)
    
    skus = list(sku_map.keys())
    
    # 2. Получаем себестоимость из БД
    costs_res = await db.execute(select(ProductCost).where(ProductCost.user_id == user.id, ProductCost.sku.in_(skus)))
    costs_map = {c.sku: c.cost_price for c in costs_res.scalars().all()}
    
    result = []
    # 3. Собираем итоговый список
    for sku, data in sku_map.items():
        cost = costs_map.get(sku, 0)
        # Примерная цена продажи (Price * (1 - Discount/100))
        # API остатков отдает Price (базовая). Считаем примерную цену реализации
        selling_price = data['price'] * (1 - data['discount']/100)
        
        # P&L (Упрощенно для MVP)
        # Комиссия ~23%, Логистика ~50р (Хардкод для MVP, потом будем брать из тарифов)
        commission = selling_price * 0.23
        logistics = 50
        profit = selling_price - commission - logistics - cost
        roi = round((profit / cost * 100), 1) if cost > 0 else 0
        
        # Получаем имя/картинку. Если нет - клиент подгрузит асинхронно или покажем SKU
        # (В идеале здесь бы кэш имен, но для MVP вернем SKU)
        
        result.append({
            "sku": sku,
            "quantity": data['quantity'],
            "price": int(selling_price),
            "cost_price": cost,
            "unit_economy": {
                "profit": int(profit),
                "roi": roi,
                "margin": int(profit / selling_price * 100) if selling_price > 0 else 0
            }
        })
        
    return result

@app.post("/api/internal/cost/{sku}")
async def set_product_cost(sku: int, req: CostUpdateRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Установка себестоимости для своего товара"""
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

# --- COMPETITOR MONITORING (CLEANED) ---
@app.post("/api/monitor/add/{sku}")
async def add_to_monitor(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # ... (старый код проверок лимитов)
    limits = {"free": 3, "pro": 50, "business": 500}
    limit = limits.get(user.subscription_plan, 3)
    current = (await db.execute(select(func.count()).select_from(MonitoredItem).where(MonitoredItem.user_id == user.id))).scalar() or 0
    if current >= limit: raise HTTPException(403, "Лимит исчерпан")
    
    if (await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku))).scalars().first():
        return {"status": "exists"}

    new_item = MonitoredItem(user_id=user.id, sku=sku, name="Загрузка...", brand="...")
    db.add(new_item); await db.commit()
    task = parse_and_save_sku.delay(sku, user.id)
    return {"status": "accepted", "task_id": task.id}

@app.get("/api/monitor/list")
async def get_my_items(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Только внешние конкуренты. Без Unit-экономики."""
    items = (await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id).order_by(MonitoredItem.id.desc()))).scalars().all()
    data = []
    for i in items:
        lp = (await db.execute(select(PriceHistory).where(PriceHistory.item_id == i.id).order_by(PriceHistory.recorded_at.desc()).limit(1))).scalars().first()
        data.append({
            "id": i.id, "sku": i.sku, "name": i.name, "brand": i.brand,
            "prices": [{"wallet_price": lp.wallet_price, "standard_price": lp.standard_price}] if lp else []
        })
    return data

@app.delete("/api/monitor/delete/{sku}")
async def delete_item(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku))
    await db.commit()
    return {"status": "deleted"}

@app.get("/api/monitor/history/{sku}")
async def get_history(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = (await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku))).scalars().first()
    if not item: raise HTTPException(404, "Item not found")
    history = (await db.execute(select(PriceHistory).where(PriceHistory.item_id == item.id).order_by(PriceHistory.recorded_at.asc()))).scalars().all()
    return {"sku": sku, "name": item.name, "history": [{"date": h.recorded_at.strftime("%d.%m %H:%M"), "wallet": h.wallet_price} for h in history]}

@app.get("/api/monitor/status/{task_id}")
async def get_status(task_id: str): 
    res = AsyncResult(task_id, app=celery_app)
    resp = {"task_id": task_id, "status": res.status}
    if res.status == 'SUCCESS': resp["data"] = res.result
    elif res.status == 'FAILURE': resp["error"] = str(res.result)
    elif res.status == 'PROGRESS': resp["info"] = res.info.get('status', 'Processing')
    return resp

# --- AI & SEO (UNCHANGED) ---
@app.post("/api/ai/analyze/{sku}")
async def start_ai_analysis(sku: int, user: User = Depends(get_current_user)):
    task = analyze_reviews_task.delay(sku, 30, user.id)
    return {"status": "accepted", "task_id": task.id}

@app.get("/api/ai/result/{task_id}")
async def get_ai_result(task_id: str): return await get_status(task_id)

@app.get("/api/seo/parse/{sku}")
async def parse_seo_keywords(sku: int, user: User = Depends(get_current_user)):
    res = await parser_service.get_seo_data(sku) 
    if res.get("status") == "error": raise HTTPException(400, res.get("message"))
    return res

class SeoGenRequest(BaseModel): sku: int; keywords: List[str]; tone: str
@app.post("/api/seo/generate")
async def generate_seo_content(req: SeoGenRequest, user: User = Depends(get_current_user)):
    task = generate_seo_task.delay(req.keywords, req.tone, req.sku, user.id)
    return {"status": "accepted", "task_id": task.id}

# --- HISTORY (UNCHANGED) ---
@app.get("/api/user/history")
async def get_user_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = (await db.execute(select(SearchHistory).where(SearchHistory.user_id == user.id).order_by(SearchHistory.created_at.desc()).limit(50))).scalars().all()
    return [{"id": h.id, "sku": h.sku, "type": h.request_type, "title": h.title, "created_at": h.created_at, "data": json.loads(h.result_json) if h.result_json else {}} for h in res]

@app.delete("/api/user/history")
async def clear_user_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(SearchHistory).where(SearchHistory.user_id == user.id))
    await db.commit()
    return {"status": "cleared"}

# --- PAYMENT & STARS ---
class StarsPaymentRequest(BaseModel): plan_id: str; amount: int
@app.post("/api/payment/stars_link")
async def create_stars_link(req: StarsPaymentRequest, user: User = Depends(get_current_user)):
    link = await bot_service.create_invoice_link(f"Подписка {req.plan_id.upper()}", f"Тариф {req.plan_id}", json.dumps({"user_id": user.id, "plan": req.plan_id}), req.amount)
    if not link: raise HTTPException(500, "Error")
    return {"invoice_link": link}

@app.post("/api/payment/create")
async def create_payment(req: PaymentRequest, user: User = Depends(get_current_user)):
    return {"status": "created", "manager_link": "https://t.me/AAntonShch"}

@app.get("/api/user/tariffs")
async def get_tariffs(user: User = Depends(get_current_user)):
    return [
        {"id": "free", "name": "Start", "price": "0 ₽", "stars": 0, "features": ["3 товара", "История 24ч"], "current": user.subscription_plan == "free", "is_best": False},
        {"id": "pro", "name": "Pro", "price": "2990 ₽", "stars": 2500, "features": ["50 товаров", "P&L (Финансы)", "Unit-экономика", "PDF"], "current": user.subscription_plan == "pro", "is_best": True},
        {"id": "business", "name": "Business", "price": "6990 ₽", "stars": 6000, "features": ["Все включено", "API"], "current": user.subscription_plan == "business", "is_best": False}
    ]

# --- ADMIN ---
@app.get("/api/admin/stats")
async def get_admin_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.is_admin: raise HTTPException(403, "Forbidden")
    u = (await db.execute(select(func.count(User.id)))).scalar()
    i = (await db.execute(select(func.count(MonitoredItem.id)))).scalar()
    return {"total_users": u, "total_items_monitored": i, "server_status": "Online (v1.5)"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)