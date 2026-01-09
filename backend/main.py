import os
import json
import io
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, update
from fpdf import FPDF
from pydantic import BaseModel
from celery.result import AsyncResult
from dotenv import load_dotenv

from auth_service import AuthService
from database import init_db, get_db, User, MonitoredItem, PriceHistory, SearchHistory
from tasks import parse_and_save_sku, analyze_reviews_task
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
            if 'user' in parsed: user_data_dict = json.loads(parsed['user'])
        except: pass

    if not user_data_dict and os.getenv("DEBUG_MODE") == "True":
         user_data_dict = {"id": 111111, "username": "test_user", "first_name": "Tester"}

    if not user_data_dict:
        raise HTTPException(status_code=401, detail="Unauthorized")

    tg_id = user_data_dict.get('id')
    stmt = select(User).where(User.telegram_id == tg_id)
    user = (await db.execute(stmt)).scalars().first()

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
    count = (await db.execute(select(func.count()).select_from(MonitoredItem).where(MonitoredItem.user_id == user.id))).scalar() or 0
    return {
        "id": user.telegram_id,
        "username": user.username,
        "name": user.first_name,
        "plan": user.subscription_plan,
        "is_admin": user.is_admin,
        "items_count": count
    }

class PaymentRequest(BaseModel):
    plan_id: str

@app.post("/api/payment/create")
async def create_payment(req: PaymentRequest, user: User = Depends(get_current_user)):
    prices = {"pro": 990, "business": 2990}
    if req.plan_id not in prices: raise HTTPException(400, "Invalid plan")
    return {"status": "created", "amount": prices[req.plan_id], "manager_link": "https://t.me/AAntonShch"}

@app.get("/api/user/tariffs")
async def get_tariffs(user: User = Depends(get_current_user)):
    return [
        {"id": "free", "name": "Старт", "price": "0 ₽", "features": ["3 товара", "История 24ч"], "current": user.subscription_plan == "free"},
        {"id": "pro", "name": "PRO", "price": "990 ₽", "features": ["50 товаров", "PDF Отчеты"], "current": user.subscription_plan == "pro", "is_best": True},
        {"id": "business", "name": "Business", "price": "2990 ₽", "features": ["500 товаров", "API"], "current": user.subscription_plan == "business"}
    ]

@app.post("/api/monitor/add/{sku}")
async def add_to_monitor(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    limit = {"free": 3, "pro": 50, "business": 500}.get(user.subscription_plan, 3)
    current = (await db.execute(select(func.count()).select_from(MonitoredItem).where(MonitoredItem.user_id == user.id))).scalar() or 0
    
    if current >= limit: raise HTTPException(403, f"Лимит: {limit}")

    exists = (await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku))).scalars().first()
    if exists: return {"status": "exists"}

    db.add(MonitoredItem(user_id=user.id, sku=sku, name="Загрузка...", brand="..."))
    await db.commit()
    
    task = parse_and_save_sku.delay(sku, user.id)
    return {"status": "accepted", "task_id": task.id}

@app.get("/api/monitor/list")
async def get_my_items(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items = (await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id).order_by(MonitoredItem.id.desc()))).scalars().all()
    data = []
    for i in items:
        lp = (await db.execute(select(PriceHistory).where(PriceHistory.item_id == i.id).order_by(PriceHistory.recorded_at.desc()).limit(1))).scalars().first()
        data.append({
            "id": i.id, "sku": i.sku, "name": i.name, "brand": i.brand,
            "prices": [{"wallet_price": lp.wallet_price}] if lp else []
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
    if not item: raise HTTPException(404)
    history = (await db.execute(select(PriceHistory).where(PriceHistory.item_id == item.id).order_by(PriceHistory.recorded_at.asc()))).scalars().all()
    return {"sku": sku, "name": item.name, "history": [{"date": h.recorded_at.strftime("%d.%m %H:%M"), "wallet": h.wallet_price, "standard": h.standard_price} for h in history]}

@app.post("/api/ai/analyze/{sku}")
async def start_ai_analysis(sku: int, user: User = Depends(get_current_user)):
    limit = 100 if user.subscription_plan in ["pro", "business"] else 30
    task = analyze_reviews_task.delay(sku, limit, user.id)
    return {"status": "accepted", "task_id": task.id}

@app.get("/api/monitor/status/{task_id}")
async def get_status(task_id: str):
    res = AsyncResult(task_id, app=celery_app)
    resp = {"task_id": task_id, "status": res.status}
    if res.status == 'SUCCESS': resp["data"] = res.result
    elif res.status == 'FAILURE': resp["error"] = str(res.result)
    elif res.status == 'PROGRESS': resp["info"] = res.info.get('status')
    return resp

@app.get("/api/ai/result/{task_id}")
async def get_ai_result(task_id: str): return await get_status(task_id)

@app.get("/api/user/history")
async def get_user_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SearchHistory).where(SearchHistory.user_id == user.id).order_by(SearchHistory.created_at.desc()).limit(50))
    return [{"id": h.id, "sku": h.sku, "type": h.request_type, "title": h.title, "created_at": h.created_at, "data": json.loads(h.result_json) if h.result_json else {}} for h in res.scalars().all()]

@app.delete("/api/user/history")
async def clear_user_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(SearchHistory).where(SearchHistory.user_id == user.id))
    await db.commit()
    return {"status": "cleared"}

@app.get("/api/report/pdf/{sku}")
async def generate_pdf(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.subscription_plan == "free": raise HTTPException(403, "Need PRO")
    
    item = (await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku))).scalars().first()
    if not item: raise HTTPException(404)
    history = (await db.execute(select(PriceHistory).where(PriceHistory.item_id == item.id).order_by(PriceHistory.recorded_at.desc()))).scalars().all()

    pdf = FPDF()
    pdf.add_page()
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    if os.path.exists(font_path): pdf.add_font('DejaVu', '', font_path, uni=True); pdf.set_font('DejaVu', '', 14)
    else: pdf.set_font("Arial", size=12)

    pdf.cell(0, 10, txt=f"Otchet: {item.name} ({sku})", ln=1, align='C')
    pdf.ln(5)
    pdf.set_font_size(10)
    pdf.cell(50, 10, "Date", 1); pdf.cell(40, 10, "Wallet", 1); pdf.ln()
    
    for h in history:
        pdf.cell(50, 10, h.recorded_at.strftime("%Y-%m-%d %H:%M"), 1)
        pdf.cell(40, 10, f"{h.wallet_price} rub", 1)
        pdf.ln()

    return StreamingResponse(io.BytesIO(pdf.output(dest='S').encode('latin-1')), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="report_{sku}.pdf"'})

@app.get("/api/admin/stats")
async def admin_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.is_admin: raise HTTPException(403)
    return {
        "total_users": (await db.execute(select(func.count(User.id)))).scalar(),
        "total_items_monitored": (await db.execute(select(func.count(MonitoredItem.id)))).scalar(),
        "server_status": "OK"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)