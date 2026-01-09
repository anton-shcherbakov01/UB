import os
import json
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
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
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
auth_manager = AuthService(os.getenv("BOT_TOKEN"))
ADMIN_USERNAME = "AAntonShch" 

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
async def get_profile(user: User = Depends(get_current_user)):
    return {"id": user.telegram_id, "username": user.username, "plan": user.subscription_plan, "is_admin": user.is_admin, "items_count": len(user.items) if user.items else 0}

@app.get("/api/user/history")
async def get_user_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SearchHistory).where(SearchHistory.user_id == user.id).order_by(SearchHistory.created_at.desc()).limit(50))
    return res.scalars().all()

@app.delete("/api/user/history")
async def clear_user_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(SearchHistory).where(SearchHistory.user_id == user.id))
    await db.commit()
    return {"status": "cleared"}

@app.get("/api/user/tariffs")
async def get_tariffs(user: User = Depends(get_current_user)):
    return [
        {"id": "free", "name": "Старт", "price": "0 ₽", "features": ["3 товара", "AI (30 отзывов)"], "current": user.subscription_plan == "free"},
        {"id": "pro", "name": "PRO", "price": "990 ₽", "features": ["50 товаров", "AI (100 отзывов)"], "current": user.subscription_plan == "pro", "is_best": True}
    ]

@app.post("/api/monitor/add/{sku}")
async def add_to_monitor(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    limit = 3 if user.subscription_plan == "free" else 50
    if len(user.items) >= limit: raise HTTPException(403, f"Лимит тарифа исчерпан")
    stmt = select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku)
    if (await db.execute(stmt)).scalars().first(): return {"status": "exists"}
    db.add(MonitoredItem(user_id=user.id, sku=sku, name="Загрузка..."))
    await db.commit()
    task = parse_and_save_sku.delay(sku, user.id)
    return {"status": "accepted", "task_id": task.id}

@app.get("/api/monitor/list")
async def get_my_items(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id).order_by(MonitoredItem.id.desc()))
    return result.scalars().all()

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
    return {"sku": sku, "name": item.name, "history": [{"date": h.recorded_at.strftime("%d.%m %H:%M"), "wallet": h.wallet_price} for h in history]}

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
async def get_status(task_id: str):
    return await get_ai_result(task_id)

@app.get("/api/admin/stats")
async def admin_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.is_admin: raise HTTPException(403, "Forbidden")
    users = (await db.execute(select(User))).scalars().all()
    items = (await db.execute(select(MonitoredItem))).scalars().all()
    return {"total_users": len(users), "total_items_monitored": len(items), "server_status": "OK"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)