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
from bot_service import bot_service # <-- Новый сервис
from auth_service import AuthService
from database import init_db, get_db, User, MonitoredItem, PriceHistory, SearchHistory
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

# ... (get_current_user и startup оставляем без изменений) ...
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

# --- WB TOKEN ---
class TokenRequest(BaseModel):
    token: str

@app.post("/api/user/token")
async def save_wb_token(req: TokenRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    is_valid = await wb_api_service.check_token(req.token)
    if not is_valid: raise HTTPException(status_code=400, detail="Неверный токен")
    user.wb_api_token = req.token
    db.add(user)
    await db.commit()
    return {"status": "saved"}

@app.delete("/api/user/token")
async def delete_wb_token(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user.wb_api_token = None
    db.add(user)
    await db.commit()
    return {"status": "deleted"}

@app.get("/api/internal/stats")
async def get_internal_stats(user: User = Depends(get_current_user)):
    if not user.wb_api_token: raise HTTPException(status_code=400, detail="Токен API не подключен")
    return await wb_api_service.get_dashboard_stats(user.wb_api_token)

# --- MONITORING & UNIT ECONOMICS ---
@app.post("/api/monitor/add/{sku}")
async def add_to_monitor(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    limits = {"free": 3, "pro": 50, "business": 500}
    limit = limits.get(user.subscription_plan, 3)
    
    count_stmt = select(func.count()).select_from(MonitoredItem).where(MonitoredItem.user_id == user.id)
    current = (await db.execute(count_stmt)).scalar() or 0
    if current >= limit: raise HTTPException(403, f"Лимит тарифа исчерпан ({limit} шт)")

    stmt = select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku)
    if (await db.execute(stmt)).scalars().first(): return {"status": "exists", "message": "Товар уже в списке"}

    new_item = MonitoredItem(user_id=user.id, sku=sku, name="Загрузка...", brand="...")
    db.add(new_item)
    await db.commit()
    task = parse_and_save_sku.delay(sku, user.id)
    return {"status": "accepted", "task_id": task.id}

class CostUpdateRequest(BaseModel):
    cost_price: int

@app.put("/api/monitor/cost/{sku}")
async def update_cost_price(sku: int, req: CostUpdateRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Обновление себестоимости для расчета P&L"""
    stmt = select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku)
    item = (await db.execute(stmt)).scalars().first()
    if not item: raise HTTPException(404, "Товар не найден")
    
    item.cost_price = req.cost_price
    db.add(item)
    await db.commit()
    return {"status": "updated", "cost_price": req.cost_price}

@app.get("/api/monitor/list")
async def get_my_items(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(MonitoredItem).where(MonitoredItem.user_id == user.id).order_by(MonitoredItem.id.desc())
    items = (await db.execute(stmt)).scalars().all()
    
    data = []
    for i in items:
        last_price_stmt = select(PriceHistory).where(PriceHistory.item_id == i.id).order_by(PriceHistory.recorded_at.desc()).limit(1)
        lp = (await db.execute(last_price_stmt)).scalars().first()
        
        # Расчет базовой P&L (MVP)
        wallet = lp.wallet_price if lp else 0
        cost = i.cost_price or 0
        # Примерная логистика + комиссия (упрощенно для MVP, точнее - в отчетах)
        commission = wallet * 0.23 # ~23% WB
        logistics = 50 # ~50 руб
        profit = wallet - commission - logistics - cost
        roi = round((profit / cost * 100), 1) if cost > 0 else 0

        data.append({
            "id": i.id, "sku": i.sku, "name": i.name, "brand": i.brand,
            "cost_price": cost,
            "prices": [{"wallet_price": wallet, "standard_price": lp.standard_price}] if lp else [],
            "unit_economy": {
                "profit": int(profit),
                "roi": roi
            }
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
    if not item: raise HTTPException(404, "Item not found")
    history = (await db.execute(select(PriceHistory).where(PriceHistory.item_id == item.id).order_by(PriceHistory.recorded_at.asc()))).scalars().all()
    return {
        "sku": sku, "name": item.name, "cost_price": item.cost_price,
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

# --- AI & SEO (Standard endpoints) ---
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
    if res.get("status") == "error": raise HTTPException(400, res.get("message"))
    return res

class SeoGenRequest(BaseModel):
    sku: int; keywords: List[str]; tone: str

@app.post("/api/seo/generate")
async def generate_seo_content(req: SeoGenRequest, user: User = Depends(get_current_user)):
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
# В реальном продакшене этот URL нужно добавить в настройки бота (setWebhook)
@app.post("/api/webhook/telegram")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    
    if "pre_checkout_query" in data:
        # Автоматическое подтверждение перед оплатой
        pc_id = data["pre_checkout_query"]["id"]
        # Тут можно вызвать bot answerPreCheckoutQuery(ok=True)
        # Пока пропускаем, так как aiogram/bot logic сложнее
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

@app.get("/api/user/tariffs")
async def get_tariffs(user: User = Depends(get_current_user)):
    return [
        {"id": "free", "name": "Start", "price": "0 ₽", "stars": 0, "features": ["3 товара", "История 24ч", "P&L (7 дней)", "Ding! (1 раз/день)"], "current": user.subscription_plan == "free", "color": "slate"},
        {"id": "pro", "name": "Pro", "price": "2990 ₽", "stars": 2500, "features": ["50 товаров", "Полный P&L (API)", "Unit-экономика", "Ding! (Безлимит)", "PDF"], "current": user.subscription_plan == "pro", "color": "indigo", "is_best": True},
        {"id": "business", "name": "Business", "price": "6990 ₽", "stars": 6000, "features": ["Автобиддер", "Конкуренты (Парсинг)", "Прогноз поставок", "API"], "current": user.subscription_plan == "business", "color": "emerald"}
    ]

# --- PDF REPORT ---
@app.get("/api/report/pdf/{sku}")
async def generate_pdf(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.subscription_plan == "free": raise HTTPException(403, "Upgrade to PRO")
    item = (await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku))).scalars().first()
    if not item: raise HTTPException(404, "Item not found")
    history = (await db.execute(select(PriceHistory).where(PriceHistory.item_id == item.id).order_by(PriceHistory.recorded_at.desc()).limit(100))).scalars().all()
    
    pdf = FPDF()
    pdf.add_page()
    try:
        pdf.add_font('DejaVu', '', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', uni=True)
        pdf.set_font('DejaVu', '', 14)
    except:
        pdf.set_font("Arial", size=12)
        
    pdf.cell(0, 10, txt=f"Report: {item.name[:40]} ({sku})", ln=1, align='C')
    pdf.ln(5)
    pdf.set_font_size(10)
    pdf.cell(40, 10, "Date", 1); pdf.cell(30, 10, "Wallet", 1); pdf.cell(30, 10, "Profit", 1); pdf.ln()
    
    # Расчет в PDF
    for h in history:
        cost = item.cost_price or 0
        profit = h.wallet_price - (h.wallet_price * 0.23) - 50 - cost
        pdf.cell(40, 10, h.recorded_at.strftime("%Y-%m-%d"), 1)
        pdf.cell(30, 10, f"{h.wallet_price}", 1)
        pdf.cell(30, 10, f"{int(profit)}", 1)
        pdf.ln()

    pdf_content = pdf.output(dest='S')
    pdf_bytes = pdf_content.encode('latin-1') if isinstance(pdf_content, str) else pdf_content
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="wb_report_{sku}.pdf"'})

# --- ADMIN ---
@app.get("/api/admin/stats")
async def get_admin_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.is_admin: raise HTTPException(403, "Forbidden")
    users = (await db.execute(select(func.count(User.id)))).scalar()
    items = (await db.execute(select(func.count(MonitoredItem.id)))).scalar()
    return {"total_users": users, "total_items_monitored": items, "server_status": "Online (v1.4 - Phase 2)"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)