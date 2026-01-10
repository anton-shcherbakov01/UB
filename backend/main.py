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
from typing import List, Optional
from datetime import datetime, timedelta  # [FIX] Добавлен timedelta

from parser_service import parser_service
from analysis_service import analysis_service
from wb_api_service import wb_api_service
from bot_service import bot_service
from auth_service import AuthService
from database import init_db, get_db, User, MonitoredItem, PriceHistory, SearchHistory, ProductCost, SeoPosition
from celery_app import celery_app
from tasks import parse_and_save_sku, analyze_reviews_task, generate_seo_task, check_seo_position_task
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
        # Возвращаем нули, чтобы фронт не падал
        return {"orders_today": {"sum": 0, "count": 0}, "stocks": {"total_quantity": 0}}
    
    stats = await wb_api_service.get_dashboard_stats(user.wb_api_token)
    return stats

# --- NEW: STORIES ENDPOINT ---
@app.get("/api/internal/stories")
async def get_stories(user: User = Depends(get_current_user)):
    """
    Генерация умных сторис на основе реальных данных.
    """
    stories = []
    
    # 1. Стори "Продажи"
    if user.wb_api_token:
        stats = await wb_api_service.get_dashboard_stats(user.wb_api_token)
        orders_sum = stats.get('orders_today', {}).get('sum', 0)
        
        # Симуляция тренда (в реальности сравниваем с БД)
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

    # 2. Стори "Биддер"
    if user.subscription_plan == "free":
        stories.append({
            "id": 2, "title": "Биддер", "val": "OFF", "color": "bg-purple-500", "subtitle": "Теряешь ~15%"
        })
    else:
        stories.append({
            "id": 2, "title": "Биддер", "val": "Active", "color": "bg-purple-500", "subtitle": "Safe Mode ON"
        })

    # 3. Стори "Лидер" (Заглушка)
    stories.append({
        "id": 3, "title": "Лидер", "val": "Худи", "color": "bg-blue-500", "subtitle": "Топ продаж"
    })

    # 4. Стори "Склад"
    stories.append({
        "id": 4, "title": "Склад", "val": "OK", "color": "bg-green-500", "subtitle": "Запаса > 14 дн"
    })

    return stories

# --- INTERNAL FINANCE & SUPPLY CHAIN ---

class CostUpdateRequest(BaseModel):
    cost_price: int

@app.get("/api/internal/products")
async def get_my_products_finance(
    user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    """
    Получение списка СВОИХ товаров для Unit-экономики.
    """
    if not user.wb_api_token: 
        return []
    
    # 1. Получаем список товаров из API Остатков
    stocks = await wb_api_service.get_my_stocks(user.wb_api_token)
    if not stocks: 
        return []
    
    # Группируем по SKU (nmId)
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
    
    # 2. Получаем себестоимость из БД
    costs_res = await db.execute(select(ProductCost).where(ProductCost.user_id == user.id, ProductCost.sku.in_(skus)))
    costs_map = {c.sku: c.cost_price for c in costs_res.scalars().all()}
    
    result = []
    # 3. Собираем отчет
    for sku, data in sku_map.items():
        cost = costs_map.get(sku, 0)
        selling_price = data['price'] * (1 - data['discount']/100)
        
        # P&L (Unit)
        commission = selling_price * 0.23
        logistics = 50 
        profit = selling_price - commission - logistics - cost
        roi = round((profit / cost * 100), 1) if cost > 0 else 0
        margin = int(profit / selling_price * 100) if selling_price > 0 else 0
        
        # Supply Chain Prediction
        sales_velocity = random.uniform(0.5, 5.0) # Mock для MVP
        supply = analysis_service.calculate_supply_prediction(data['quantity'], sales_velocity)

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
            "supply": supply
        })
        
    return result

@app.post("/api/internal/cost/{sku}")
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

@app.get("/api/internal/coefficients")
async def get_supply_coefficients(user: User = Depends(get_current_user)):
    """Получение коэффициентов приемки для Supply Chain"""
    return await wb_api_service.get_warehouse_coeffs(user.wb_api_token)

# --- TRANSIT CALCULATOR ---
class TransitCalcRequest(BaseModel):
    volume: int # Литы
    destination: str = "Koledino"

@app.post("/api/internal/transit_calc")
async def calculate_transit(req: TransitCalcRequest, user: User = Depends(get_current_user)):
    """Калькулятор транзита (Roadmap 3.2.2)"""
    return analysis_service.calculate_transit_benefit(req.volume)

# --- NEW: BIDDER SIMULATION ---
@app.get("/api/bidder/simulation")
async def get_bidder_simulation(user: User = Depends(get_current_user)):
    """
    Симуляция работы биддера.
    """
    # Генерируем "фейковые" данные для демо эффекта "Safe Mode"
    return {
        "status": "safe_mode",
        "campaigns_active": 3,
        "total_budget_saved": random.randint(5000, 25000),
        "logs": [
            {"time": (datetime.now() - timedelta(minutes=5)).strftime("%H:%M"), "msg": "Кампания 'Платья': Ставка конкурента 500₽ -> Оптимизировано до 155₽"},
            {"time": (datetime.now() - timedelta(minutes=15)).strftime("%H:%M"), "msg": "Кампания 'Блузки': Удержание 2 места (Target CPA)"},
            {"time": (datetime.now() - timedelta(minutes=45)).strftime("%H:%M"), "msg": "Аукцион перегрет. Реклама на паузе."}
        ]
    }

# --- COMPETITOR MONITORING & SEO TRACKER ---

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

# --- NEW: SEO TRACKER (SERP) ---

class SeoTrackRequest(BaseModel):
    sku: int
    keyword: str

@app.post("/api/seo/track")
async def track_position(req: SeoTrackRequest, user: User = Depends(get_current_user)):
    """Запуск задачи трекинга позиции"""
    task = check_seo_position_task.delay(req.sku, req.keyword, user.id)
    return {"status": "accepted", "task_id": task.id}

@app.get("/api/seo/positions")
async def get_seo_positions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Получение сохраненных позиций"""
    res = await db.execute(select(SeoPosition).where(SeoPosition.user_id == user.id).order_by(SeoPosition.last_check.desc()))
    return res.scalars().all()

@app.delete("/api/seo/positions/{id}")
async def delete_seo_position(id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(SeoPosition).where(SeoPosition.id == id, SeoPosition.user_id == user.id))
    await db.commit()
    return {"status": "deleted"}

# --- AI & SEO CONTENT ---
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

class PaymentRequest(BaseModel):
    plan_id: str

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
    return {"total_users": users, "total_items_monitored": items, "server_status": "Online (v2.0)"}

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
    
    # [FIX] Добавляем поддержку шрифтов для кириллицы
    # Пытаемся загрузить системный шрифт или fallback
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf' # Docker standard
    try:
        if os.path.exists(font_path):
            pdf.add_font('DejaVu', '', font_path, uni=True)
            pdf.set_font('DejaVu', '', 14)
        else:
             # Попытка найти локальный шрифт
             local_font = "fonts/DejaVuSans.ttf"
             if os.path.exists(local_font):
                 pdf.add_font('DejaVu', '', local_font, uni=True)
                 pdf.set_font('DejaVu', '', 14)
             else:
                 logger.warning("No unicode font found. Cyrillic may fail.")
                 pdf.set_font("Arial", size=12) # Fallback (Внимание: кириллица не будет работать!)
    except Exception as e:
        logger.error(f"Font loading error: {e}")
        pdf.set_font("Arial", size=12)

    pdf.cell(0, 10, txt=f"Report: {sku}", ln=1, align='C') # Убрали item.name из заголовка на случай проблем с кодировкой
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
    
    # Совместимость версий FPDF
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