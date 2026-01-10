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
from datetime import datetime

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

# ID Супер-админа (Anton)
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

    # Fallback для отладки
    if not user_data_dict and os.getenv("DEBUG_MODE", "False") == "True":
         user_data_dict = {"id": 901378787, "username": "debug_user", "first_name": "Debug"}

    if not user_data_dict:
        raise HTTPException(status_code=401, detail="Unauthorized")

    tg_id = user_data_dict.get('id')
    stmt = select(User).where(User.telegram_id == tg_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    # FORCE ADMIN RIGHTS
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
        # Если юзер уже есть, обновляем права (для суперадмина)
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
    
    # Маскируем токен для безопасности
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

# --- WB API TOKEN MANAGEMENT ---

class TokenRequest(BaseModel):
    token: str

@app.post("/api/user/token")
async def save_wb_token(
    req: TokenRequest, 
    user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    """Сохранение токена API Статистики WB"""
    is_valid = await wb_api_service.check_token(req.token)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Неверный токен или ошибка API WB")

    user.wb_api_token = req.token
    db.add(user)
    await db.commit()
    return {"status": "saved", "message": "Токен успешно сохранен"}

@app.delete("/api/user/token")
async def delete_wb_token(
    user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    user.wb_api_token = None
    db.add(user)
    await db.commit()
    return {"status": "deleted"}

@app.get("/api/internal/stats")
async def get_internal_stats(user: User = Depends(get_current_user)):
    """Получение статистики (Заказы, Остатки) через официальный API"""
    if not user.wb_api_token:
        raise HTTPException(status_code=400, detail="Токен API не подключен")
    
    stats = await wb_api_service.get_dashboard_stats(user.wb_api_token)
    return stats

# --- INTERNAL FINANCE & UNIT ECONOMICS (NEW) ---

class CostUpdateRequest(BaseModel):
    cost_price: int

@app.get("/api/internal/products")
async def get_my_products_finance(
    user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    """
    Получение списка СВОИХ товаров для Unit-экономики (внутренняя аналитика).
    Данные берутся из API WB (остатки) + БД (себестоимость).
    """
    if not user.wb_api_token: 
        return []
    
    # 1. Получаем список товаров из API Остатков
    stocks = await wb_api_service.get_my_stocks(user.wb_api_token)
    if not stocks: 
        return []
    
    # Группируем по SKU (nmId), суммируем остатки
    sku_map = {}
    for s in stocks:
        sku = s.get('nmId')
        if sku not in sku_map:
            sku_map[sku] = {
                "sku": sku, 
                "quantity": 0, 
                "price": s.get('Price', 0), # Базовая цена
                "discount": s.get('Discount', 0)
            }
        sku_map[sku]['quantity'] += s.get('quantity', 0)
    
    skus = list(sku_map.keys())
    
    # 2. Получаем сохраненную себестоимость из БД
    costs_res = await db.execute(select(ProductCost).where(ProductCost.user_id == user.id, ProductCost.sku.in_(skus)))
    costs_map = {c.sku: c.cost_price for c in costs_res.scalars().all()}
    
    result = []
    # 3. Собираем итоговый отчет
    for sku, data in sku_map.items():
        cost = costs_map.get(sku, 0)
        # Примерная цена продажи
        selling_price = data['price'] * (1 - data['discount']/100)
        
        # Расчет P&L (Unit-экономика)
        # Хардкод комиссий для MVP (позже будем брать из API тарифов)
        commission = selling_price * 0.23 # ~23%
        logistics = 50 # ~50 руб
        profit = selling_price - commission - logistics - cost
        roi = round((profit / cost * 100), 1) if cost > 0 else 0
        margin = int(profit / selling_price * 100) if selling_price > 0 else 0
        
        result.append({
            "sku": sku,
            "quantity": data['quantity'],
            "price": int(selling_price),
            "cost_price": cost,
            "unit_economy": {
                "profit": int(profit),
                "roi": roi,
                "margin": margin
            }
        })
        
    return result

@app.post("/api/internal/cost/{sku}")
async def set_product_cost(
    sku: int, 
    req: CostUpdateRequest, 
    user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
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

# --- COMPETITOR MONITORING ---

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
    """
    Получение списка ОТСЛЕЖИВАЕМЫХ КОНКУРЕНТОВ.
    Здесь нет Unit-экономики, только цена.
    """
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
        "sku": sku, 
        "name": item.name, 
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

# --- AI & SEO ---
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
    """Извлекаем ключевые слова (название + характеристики)"""
    res = await parser_service.get_seo_data(sku) 
    if res.get("status") == "error":
        raise HTTPException(400, res.get("message"))
    return res

class SeoGenRequest(BaseModel):
    sku: int
    keywords: List[str]
    tone: str

@app.post("/api/seo/generate")
async def generate_seo_content(req: SeoGenRequest, user: User = Depends(get_current_user)):
    """Запуск задачи генерации текста"""
    task = generate_seo_task.delay(req.keywords, req.tone, req.sku, user.id)
    return {"status": "accepted", "task_id": task.id}

# --- HISTORY ---
@app.get("/api/user/history")
async def get_user_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SearchHistory).where(SearchHistory.user_id == user.id).order_by(SearchHistory.created_at.desc()).limit(50))
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

# --- PAYMENT & STARS (NEW) ---

class StarsPaymentRequest(BaseModel):
    plan_id: str
    amount: int # Stars

@app.post("/api/payment/stars_link")
async def create_stars_link(req: StarsPaymentRequest, user: User = Depends(get_current_user)):
    """Генерация инвойса для Telegram Stars"""
    title = f"Подписка {req.plan_id.upper()}"
    desc = f"Активация тарифа {req.plan_id} на 1 месяц"
    payload = json.dumps({"user_id": user.id, "plan": req.plan_id})
    
    link = await bot_service.create_invoice_link(title, desc, payload, req.amount)
    if not link:
        raise HTTPException(500, "Ошибка создания ссылки")
        
    return {"invoice_link": link}

# Webhook для обработки успешных платежей от Telegram
@app.post("/api/webhook/telegram")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    
    if "pre_checkout_query" in data:
        # Автоматическое подтверждение
        pass

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

@app.post("/api/payment/create")
async def create_payment(req: PaymentRequest, user: User = Depends(get_current_user)):
    return {"status": "created", "message": f"Оплата тарифа {req.plan_id.upper()}.", "manager_link": "https://t.me/AAntonShch"}

@app.get("/api/user/tariffs")
async def get_tariffs(user: User = Depends(get_current_user)):
    return [
        {"id": "free", "name": "Start", "price": "0 ₽", "stars": 0, "features": ["3 товара", "История 24ч", "P&L (7 дней)", "Ding! (1 раз/день)"], "current": user.subscription_plan == "free", "color": "slate"},
        {"id": "pro", "name": "Pro", "price": "2990 ₽", "stars": 2500, "features": ["50 товаров", "Полный P&L (API)", "Unit-экономика", "Ding! (Безлимит)", "PDF"], "current": user.subscription_plan == "pro", "color": "indigo", "is_best": True},
        {"id": "business", "name": "Business", "price": "6990 ₽", "stars": 6000, "features": ["Автобиддер", "Конкуренты (Парсинг)", "Прогноз поставок", "API"], "current": user.subscription_plan == "business", "color": "emerald"}
    ]

# --- ADMIN ---
@app.get("/api/admin/stats")
async def get_admin_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.is_admin: raise HTTPException(403, "Forbidden")
    users = (await db.execute(select(func.count(User.id)))).scalar()
    items = (await db.execute(select(func.count(MonitoredItem.id)))).scalar()
    return {"total_users": users, "total_items_monitored": items, "server_status": "Online (v1.5)"}

# --- PDF REPORT ---
@app.get("/api/report/pdf/{sku}")
async def generate_pdf(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.subscription_plan == "free":
        raise HTTPException(403, "Upgrade to PRO")

    item = (await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku))).scalars().first()
    if not item: raise HTTPException(404, "Item not found")

    history = (await db.execute(select(PriceHistory).where(PriceHistory.item_id == item.id).order_by(PriceHistory.recorded_at.desc()).limit(100))).scalars().all()

    pdf = FPDF()
    pdf.add_page()
    try:
        # Используем шрифт, который точно есть в контейнере
        pdf.add_font('DejaVu', '', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', uni=True)
        pdf.set_font('DejaVu', '', 14)
    except:
        pdf.set_font("Arial", size=12)

    pdf.cell(0, 10, txt=f"Report: {item.name[:40]} ({sku})", ln=1, align='C')
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

    # FIX: FPDF2 output() returns bytes/bytearray in newer versions, no encode needed
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