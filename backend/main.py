import os
import json
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
         user_data_dict = {"id": 111111, "username": "test_user", "first_name": "Tester"}

    if not user_data_dict:
        raise HTTPException(status_code=401, detail="Unauthorized")

    tg_id = user_data_dict.get('id')
    
    # Убрали selectinload(User.items), чтобы не тянуть лишнее
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
    """Получить профиль + количество товаров (безопасно)"""
    # Считаем товары отдельным запросом, это не вызывает ошибок асинхронности
    count_stmt = select(func.count()).select_from(MonitoredItem).where(MonitoredItem.user_id == user.id)
    items_count = await db.execute(count_stmt)
    count = items_count.scalar() or 0

    return {
        "id": user.telegram_id,
        "username": user.username,
        "name": user.first_name,
        "plan": user.subscription_plan,
        "is_admin": user.is_admin,
        "items_count": count
    }

@app.get("/api/user/tariffs")
async def get_tariffs(user: User = Depends(get_current_user)):
    return [
        {"id": "free", "name": "Старт", "price": "0 ₽", "features": ["3 товара", "AI (30 отзывов)", "История цен"], "current": user.subscription_plan == "free", "color": "slate"},
        {"id": "pro", "name": "PRO", "price": "990 ₽", "features": ["50 товаров", "AI (100 отзывов)", "Приоритетная очередь"], "current": user.subscription_plan == "pro", "color": "indigo", "is_best": True}
    ]

@app.post("/api/monitor/add/{sku}")
async def add_to_monitor(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Проверка лимита через count
    count_stmt = select(func.count()).select_from(MonitoredItem).where(MonitoredItem.user_id == user.id)
    current_items = (await db.execute(count_stmt)).scalar() or 0
    
    limit = 3 if user.subscription_plan == "free" else 50
    if current_items >= limit:
        raise HTTPException(status_code=403, detail=f"Лимит ({limit} шт) исчерпан")

    # Проверка дубликатов
    stmt = select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku)
    if (await db.execute(stmt)).scalars().first():
        return {"status": "exists", "message": "Товар уже в списке"}

    db.add(MonitoredItem(user_id=user.id, sku=sku, name="Загрузка...", brand="..."))
    await db.commit()
    
    task = parse_and_save_sku.delay(sku, user.id)
    return {"status": "accepted", "task_id": task.id}

@app.get("/api/monitor/list")
async def get_my_items(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id).order_by(MonitoredItem.id.desc()))
    return result.scalars().all()

@app.delete("/api/monitor/delete/{sku}")
async def delete_item(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Каскадное удаление настроено в БД, достаточно удалить товар
    stmt = delete(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku)
    await db.execute(stmt)
    await db.commit()
    return {"status": "deleted"}

@app.get("/api/monitor/history/{sku}")
async def get_history(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item_res = await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku))
    item = item_res.scalars().first()
    
    if not item: raise HTTPException(404, "Товар не найден")
        
    history_res = await db.execute(select(PriceHistory).where(PriceHistory.item_id == item.id).order_by(PriceHistory.recorded_at.asc()))
    history = history_res.scalars().all()
    
    return {
        "sku": sku,
        "name": item.name,
        "history": [{"date": h.recorded_at.strftime("%d.%m %H:%M"), "wallet": h.wallet_price} for h in history]
    }

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

# --- ИСТОРИЯ ЗАПРОСОВ ---
@app.get("/api/user/history")
async def get_user_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(SearchHistory).where(SearchHistory.user_id == user.id).order_by(SearchHistory.created_at.desc()).limit(50))
    return res.scalars().all()

@app.delete("/api/user/history")
async def clear_user_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(SearchHistory).where(SearchHistory.user_id == user.id))
    await db.commit()
    return {"status": "cleared"}

# --- АДМИНКА ---
@app.get("/api/admin/stats")
async def admin_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.is_admin: raise HTTPException(403, "Forbidden")
    
    uc = (await db.execute(select(func.count(User.id)))).scalar()
    ic = (await db.execute(select(func.count(MonitoredItem.id)))).scalar()
    
    return {"total_users": uc, "total_items_monitored": ic, "server_status": "OK"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)