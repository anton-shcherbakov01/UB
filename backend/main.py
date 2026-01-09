import os
import json
import io
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, update
from sqlalchemy.orm import selectinload
from fpdf import FPDF
from pydantic import BaseModel

from parser_service import parser_service
from analysis_service import analysis_service
from auth_service import AuthService
from database import init_db, get_db, User, MonitoredItem, PriceHistory, SearchHistory
from tasks import parse_and_save_sku, analyze_reviews_task
from dotenv import load_dotenv
from celery.result import AsyncResult
from celery_app import celery_app

load_dotenv()

app = FastAPI(title="WB Analytics Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

auth_manager = AuthService(os.getenv("BOT_TOKEN"))
ADMIN_USERNAME = "AAntonShch" 

# --- AUTH & USER ---

async def get_current_user(
    x_tg_data: str = Header(None, alias="X-TG-Data"),
    x_tg_data_query: str = Query(None, alias="x_tg_data"),
    db: AsyncSession = Depends(get_db)
):
    """
    Универсальный определитель пользователя.
    Принимает токен в заголовке (AJAX) или в URL (PDF скачивание).
    """
    token = x_tg_data if x_tg_data else x_tg_data_query
    
    user_data_dict = None

    if token:
        if auth_manager.validate_init_data(token):
            try:
                parsed = dict(parse_qsl(token))
                if 'user' in parsed: user_data_dict = json.loads(parsed['user'])
            except: pass

    if not user_data_dict and os.getenv("DEBUG_MODE", "False") == "True":
         user_data_dict = {"id": 111111, "username": "test_user", "first_name": "Tester"}

    if not user_data_dict:
        # Для PDF запросов из браузера 401 может выглядеть как ошибка загрузки
        raise HTTPException(status_code=401, detail="Unauthorized")

    tg_id = user_data_dict.get('id')
    
    stmt = select(User).where(User.telegram_id == tg_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        is_admin = (user_data_dict.get('username') == ADMIN_USERNAME)
        user = User(
            telegram_id=tg_id, 
            username=user_data_dict.get('username'), 
            first_name=user_data_dict.get('first_name'), 
            is_admin=is_admin
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    
    return user

@app.on_event("startup")
async def on_startup(): await init_db()

@app.get("/api/user/me")
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    count_stmt = select(func.count()).select_from(MonitoredItem).where(MonitoredItem.user_id == user.id)
    count = (await db.execute(count_stmt)).scalar() or 0
    return {
        "id": user.telegram_id,
        "username": user.username,
        "name": user.first_name,
        "plan": user.subscription_plan,
        "is_admin": user.is_admin,
        "items_count": count
    }

# --- TARIFFS & PAYMENT ---
class PaymentRequest(BaseModel):
    plan_id: str

@app.post("/api/payment/create")
async def create_payment(req: PaymentRequest, user: User = Depends(get_current_user)):
    prices = {"pro": 990, "business": 2990}
    if req.plan_id not in prices:
        raise HTTPException(400, "Invalid plan")
    return {
        "status": "created",
        "amount": prices[req.plan_id],
        "message": f"Оплата тарифа {req.plan_id.upper()}: {prices[req.plan_id]}₽. Свяжитесь с менеджером.",
        "manager_link": "https://t.me/AAntonShch"
    }

@app.get("/api/user/tariffs")
async def get_tariffs(user: User = Depends(get_current_user)):
    return [
        {"id": "free", "name": "Старт", "price": "0 ₽", "features": ["3 товара", "История 24ч", "AI (30 отзывов)"], "current": user.subscription_plan == "free", "color": "slate"},
        {"id": "pro", "name": "PRO", "price": "990 ₽", "features": ["50 товаров", "История 30 дней", "AI (100 отзывов)", "PDF Отчеты"], "current": user.subscription_plan == "pro", "color": "indigo", "is_best": True},
        {"id": "business", "name": "Business", "price": "2990 ₽", "features": ["500 товаров", "Безлимит AI", "Приоритет", "API"], "current": user.subscription_plan == "business", "color": "emerald"}
    ]

# --- MONITORING ---
@app.post("/api/monitor/add/{sku}")
async def add_to_monitor(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    limits = {"free": 3, "pro": 50, "business": 500}
    limit = limits.get(user.subscription_plan, 3)
    
    count_stmt = select(func.count()).select_from(MonitoredItem).where(MonitoredItem.user_id == user.id)
    current = (await db.execute(count_stmt)).scalar() or 0
    
    if current >= limit:
        raise HTTPException(403, f"Лимит тарифа исчерпан ({limit} шт)")

    stmt = select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku)
    if (await db.execute(stmt)).scalars().first(): return {"status": "exists", "message": "Товар уже в списке"}

    # Создаем с временным именем
    db.add(MonitoredItem(user_id=user.id, sku=sku, name="Загрузка...", brand="..."))
    await db.commit()
    
    task = parse_and_save_sku.delay(sku, user.id)
    return {"status": "accepted", "task_id": task.id}

@app.get("/api/monitor/list")
async def get_my_items(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Загружаем товары вместе с последней ценой (оптимизация)
    stmt = select(MonitoredItem).where(MonitoredItem.user_id == user.id).order_by(MonitoredItem.id.desc())
    result = await db.execute(stmt)
    items = result.scalars().all()
    
    # Для списка нам нужна последняя цена
    data = []
    for i in items:
        # Для каждого товара ищем последнюю запись в истории
        last_price_stmt = select(PriceHistory).where(PriceHistory.item_id == i.id).order_by(PriceHistory.recorded_at.desc()).limit(1)
        lp = (await db.execute(last_price_stmt)).scalars().first()
        
        data.append({
            "id": i.id, "sku": i.sku, "name": i.name, "brand": i.brand,
            "prices": [{"wallet_price": lp.wallet_price, "standard_price": lp.standard_price, "base_price": lp.base_price}] if lp else []
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
    if not item: raise HTTPException(404, "Not found")
    history = (await db.execute(select(PriceHistory).where(PriceHistory.item_id == item.id).order_by(PriceHistory.recorded_at.asc()))).scalars().all()
    return {"sku": sku, "name": item.name, "history": [{"date": h.recorded_at.strftime("%d.%m %H:%M"), "wallet": h.wallet_price, "standard": h.standard_price, "base": h.base_price} for h in history]}

# --- AI ---
@app.post("/api/ai/analyze/{sku}")
async def start_ai_analysis(sku: int, user: User = Depends(get_current_user)):
    limit = 30 if user.subscription_plan == "free" else 100
    task = analyze_reviews_task.delay(sku, limit, user.id)
    return {"status": "accepted", "task_id": task.id}

@app.get("/api/ai/result/{task_id}")
async def get_ai_result(task_id: str):
    res = AsyncResult(task_id, app=celery_app)
    resp = {"task_id": task_id, "status": res.status}
    if res.status == 'SUCCESS': resp["data"] = res.result
    elif res.status == 'FAILURE': resp["error"] = str(res.result)
    elif res.status == 'PROGRESS': resp["info"] = res.info.get('status')
    return resp

@app.get("/api/monitor/status/{task_id}")
async def get_status(task_id: str): return await get_ai_result(task_id)

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

# --- PDF REPORT ---
@app.get("/api/report/pdf/{sku}")
async def generate_pdf(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.subscription_plan == "free":
        raise HTTPException(403, "PDF доступен только в PRO версии")

    item = (await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku))).scalars().first()
    if not item: raise HTTPException(404, "Item not found")

    history = (await db.execute(select(PriceHistory).where(PriceHistory.item_id == item.id).order_by(PriceHistory.recorded_at.desc()).limit(100))).scalars().all()

    pdf = FPDF()
    pdf.add_page()
    
    # Шрифт
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    if os.path.exists(font_path):
        pdf.add_font('DejaVu', '', font_path, uni=True)
        pdf.set_font('DejaVu', '', 14)
    else:
        pdf.set_font("Arial", size=12)

    pdf.cell(0, 10, txt=f"Otchet: {item.name} ({sku})", ln=1, align='C')
    pdf.ln(5)
    
    pdf.set_font_size(10)
    # Заголовки таблицы
    pdf.cell(50, 10, "Data", 1)
    pdf.cell(40, 10, "Koshelek", 1)
    pdf.cell(40, 10, "Standard", 1)
    pdf.cell(40, 10, "Base", 1)
    pdf.ln()

    for h in history:
        pdf.cell(50, 10, h.recorded_at.strftime("%Y-%m-%d %H:%M"), 1)
        pdf.cell(40, 10, f"{h.wallet_price} rub", 1)
        pdf.cell(40, 10, f"{h.standard_price} rub", 1)
        pdf.cell(40, 10, f"{h.base_price} rub", 1)
        pdf.ln()

    return StreamingResponse(io.BytesIO(pdf.output(dest='S').encode('latin-1')), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="report_{sku}.pdf"'})

# --- ADMIN ---
class SetPlanRequest(BaseModel):
    user_id: int
    plan: str

@app.get("/api/admin/users")
async def get_all_users(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.is_admin: raise HTTPException(403, "Forbidden")
    users = (await db.execute(select(User).order_by(User.id.desc()))).scalars().all()
    return users

@app.post("/api/admin/set_plan")
async def set_user_plan(req: SetPlanRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.is_admin: raise HTTPException(403, "Forbidden")
    stmt = update(User).where(User.telegram_id == req.user_id).values(subscription_plan=req.plan)
    await db.execute(stmt)
    await db.commit()
    return {"status": "updated"}

@app.get("/api/admin/stats")
async def admin_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.is_admin: raise HTTPException(403, "Forbidden")
    uc = (await db.execute(select(func.count(User.id)))).scalar()
    ic = (await db.execute(select(func.count(MonitoredItem.id)))).scalar()
    return {"total_users": uc, "total_items_monitored": ic, "server_status": "OK"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)