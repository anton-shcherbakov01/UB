import os
import json
import io
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, update
from sqlalchemy.orm import selectinload
from fpdf import FPDF

from parser_service import parser_service
from analysis_service import analysis_service
from auth_service import AuthService
from database import init_db, get_db, User, MonitoredItem, PriceHistory, SearchHistory
from tasks import parse_and_save_sku, analyze_reviews_task
from dotenv import load_dotenv
from celery.result import AsyncResult
from celery_app import celery_app
from pydantic import BaseModel

load_dotenv()
app = FastAPI(title="WB Analytics Platform")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
auth_manager = AuthService(os.getenv("BOT_TOKEN"))
ADMIN_USERNAME = "AAntonShch"

# --- AUTH & USER ---
async def get_current_user(x_tg_data: str = Header(None), db: AsyncSession = Depends(get_db)):
    user_data_dict = None
    if x_tg_data and auth_manager.validate_init_data(x_tg_data):
        try:
            parsed = dict(parse_qsl(x_tg_data))
            if 'user' in parsed: user_data_dict = json.loads(parsed['user'])
        except: pass
    if not user_data_dict and os.getenv("DEBUG_MODE", "False") == "True": 
        user_data_dict = {"id": 111111, "username": "test", "first_name": "Tester"}
    
    if not user_data_dict: raise HTTPException(401, "Unauthorized")
    
    tg_id = user_data_dict.get('id')
    stmt = select(User).options(selectinload(User.items)).where(User.telegram_id == tg_id)
    user = (await db.execute(stmt)).scalars().first()
    
    if not user:
        is_admin = (user_data_dict.get('username') == ADMIN_USERNAME)
        user = User(telegram_id=tg_id, username=user_data_dict.get('username'), first_name=user_data_dict.get('first_name'), is_admin=is_admin)
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
    return {"id": user.telegram_id, "username": user.username, "plan": user.subscription_plan, "is_admin": user.is_admin, "items_count": count}

# --- TARIFFS & PAYMENT STUB ---
class PaymentRequest(BaseModel):
    plan_id: str

@app.post("/api/payment/create")
async def create_payment(req: PaymentRequest, user: User = Depends(get_current_user)):
    """
    Заглушка для оплаты. В будущем сюда подключить ЮKassa.
    Сейчас просто возвращает ссылку на бота менеджера или инструкции.
    """
    prices = {"pro": 990, "business": 2990}
    if req.plan_id not in prices:
        raise HTTPException(400, "Invalid plan")
    
    # Для ИП: Можно возвращать ссылку на оплату счета или контакт менеджера
    return {
        "status": "created",
        "amount": prices[req.plan_id],
        "message": f"Для оплаты тарифа {req.plan_id.upper()} переведите {prices[req.plan_id]}₽ по реквизитам ИП...",
        "manager_link": "https://t.me/AAntonShch" # Ссылка на вас для ручной активации
    }

@app.get("/api/user/tariffs")
async def get_tariffs(user: User = Depends(get_current_user)):
    # Лимиты жестко прописаны здесь, чтобы фронт знал о них
    return [
        {"id": "free", "name": "Старт", "price": "0 ₽", "features": ["3 товара в мониторинге", "История за 24 часа", "Базовый AI"], "limits": {"items": 3, "reviews": 30}, "current": user.subscription_plan == "free", "color": "slate"},
        {"id": "pro", "name": "PRO", "price": "990 ₽", "features": ["50 товаров", "История за месяц", "Расширенный AI", "PDF отчеты"], "limits": {"items": 50, "reviews": 100}, "current": user.subscription_plan == "pro", "color": "indigo", "is_best": True},
        {"id": "business", "name": "Business", "price": "2990 ₽", "features": ["500 товаров", "Безлимитный AI", "Приоритетная поддержка"], "limits": {"items": 500, "reviews": 1000}, "current": user.subscription_plan == "business", "color": "emerald"}
    ]

# --- MONITORING ---
@app.post("/api/monitor/add/{sku}")
async def add_to_monitor(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Проверка лимитов по тарифу
    limits = {"free": 3, "pro": 50, "business": 500}
    limit = limits.get(user.subscription_plan, 3)
    
    count_stmt = select(func.count()).select_from(MonitoredItem).where(MonitoredItem.user_id == user.id)
    current_items = (await db.execute(count_stmt)).scalar() or 0
    
    if current_items >= limit:
        raise HTTPException(403, f"Лимит тарифа {user.subscription_plan} исчерпан ({limit} шт)")

    stmt = select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku)
    if (await db.execute(stmt)).scalars().first(): return {"status": "exists", "message": "Товар уже в списке"}

    db.add(MonitoredItem(user_id=user.id, sku=sku, name="Загрузка...", brand="..."))
    await db.commit()
    task = parse_and_save_sku.delay(sku, user.id)
    return {"status": "accepted", "task_id": task.id}

@app.get("/api/monitor/list")
async def get_my_items(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id).order_by(MonitoredItem.id.desc()))
    items = result.scalars().all()
    # Обогащаем данными о последней цене
    return items

@app.delete("/api/monitor/delete/{sku}")
async def delete_item(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku))
    await db.commit()
    return {"status": "deleted"}

@app.get("/api/monitor/history/{sku}")
async def get_history(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = (await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku))).scalars().first()
    if not item: raise HTTPException(404, "Not found")
    history = (await db.execute(select(PriceHistory).where(PriceHistory.item_id == item.id).order_by(PriceHistory.recorded_at.asc()))).scalars().all()
    return {
        "sku": sku, "name": item.name, 
        "history": [{"date": h.recorded_at.strftime("%d.%m %H:%M"), "wallet": h.wallet_price, "standard": h.standard_price, "base": h.base_price} for h in history]
    }

# --- AI ---
@app.post("/api/ai/analyze/{sku}")
async def start_ai_analysis(sku: int, user: User = Depends(get_current_user)):
    limits = {"free": 30, "pro": 100, "business": 200}
    limit = limits.get(user.subscription_plan, 30)
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

# --- HISTORY & REPORTS ---
@app.get("/api/user/history")
async def get_user_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SearchHistory).where(SearchHistory.user_id == user.id).order_by(SearchHistory.created_at.desc()).limit(50))
    history = res.scalars().all()
    # Возвращаем историю, распарсивая JSON результат
    result = []
    for h in history:
        try:
            data = json.loads(h.result_json) if h.result_json else None
        except: data = None
        result.append({
            "id": h.id, "sku": h.sku, "type": h.request_type, 
            "title": h.title, "created_at": h.created_at,
            "data": data
        })
    return result

@app.delete("/api/user/history")
async def clear_user_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(SearchHistory).where(SearchHistory.user_id == user.id))
    await db.commit()
    return {"status": "cleared"}

@app.get("/api/report/pdf/{sku}")
async def generate_pdf_report(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Генерация PDF отчета по товару"""
    if user.subscription_plan == "free":
        raise HTTPException(403, "PDF отчеты доступны только в PRO версии")

    # Получаем данные (историю или AI анализ можно добавить)
    item_res = await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku))
    item = item_res.scalars().first()
    if not item: raise HTTPException(404, "Товар не найден в мониторинге")

    history_res = await db.execute(select(PriceHistory).where(PriceHistory.item_id == item.id).order_by(PriceHistory.recorded_at.desc()).limit(30))
    history = history_res.scalars().all()

    # Генерация PDF
    pdf = FPDF()
    pdf.add_page()
    
    # Шрифт (используем DejaVu, который установили в Docker)
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    if os.path.exists(font_path):
        pdf.add_font('DejaVu', '', font_path, uni=True)
        pdf.set_font('DejaVu', '', 14)
    else:
        pdf.set_font("Arial", size=12) # Fallback

    pdf.cell(200, 10, txt=f"Otchet po tovaru WB: {sku}", ln=1, align='C')
    pdf.set_font('DejaVu', '', 10)
    pdf.cell(200, 10, txt=f"Nazvanie: {item.name}", ln=1)
    pdf.cell(200, 10, txt=f"Brend: {item.brand}", ln=1)
    pdf.ln(10)
    
    pdf.cell(200, 10, txt="Istoria cen (poslednie 30 zapisey):", ln=1)
    pdf.ln(5)
    
    # Таблица
    col_width = 45
    pdf.cell(col_width, 10, "Data", 1)
    pdf.cell(col_width, 10, "Koshelek", 1)
    pdf.cell(col_width, 10, "Obychnaya", 1)
    pdf.cell(col_width, 10, "Bazovaya", 1)
    pdf.ln()
    
    for h in history:
        pdf.cell(col_width, 10, h.recorded_at.strftime("%Y-%m-%d %H:%M"), 1)
        pdf.cell(col_width, 10, str(h.wallet_price), 1)
        pdf.cell(col_width, 10, str(h.standard_price), 1)
        pdf.cell(col_width, 10, str(h.base_price), 1)
        pdf.ln()

    # Output
    pdf_bytes = pdf.output(dest='S').encode('latin-1')
    
    headers = {'Content-Disposition': f'attachment; filename="report_{sku}.pdf"'}
    return StreamingResponse(io.BytesIO(pdf_bytes), headers=headers, media_type='application/pdf')

# --- ADMIN PANEL ---
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
    return {"status": "updated", "user_id": req.user_id, "new_plan": req.plan}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)