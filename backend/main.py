import os
import json
from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
# Импортируем selectinload для жадной загрузки связей
from sqlalchemy.orm import selectinload
from typing import List, Optional

from parser_service import parser_service
from analysis_service import analysis_service
from auth_service import AuthService
from database import init_db, get_db, User, MonitoredItem, PriceHistory
from tasks import parse_and_save_sku
from dotenv import load_dotenv

# Инициализация окружения
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
ADMIN_USERNAME = "AntonShch" 

# --- ЗАВИСИМОСТИ ---

async def get_current_user(x_tg_data: str = Header(None), db: AsyncSession = Depends(get_db)):
    """Определяет пользователя по данным из Telegram"""
    
    user_data_dict = None

    if x_tg_data:
        is_valid = auth_manager.validate_init_data(x_tg_data)
        if is_valid:
            try:
                parsed = dict(parse_qsl(x_tg_data))
                if 'user' in parsed:
                    user_data_dict = json.loads(parsed['user'])
            except Exception as e:
                print(f"Auth parse error: {e}")

    if not user_data_dict and os.getenv("DEBUG_MODE", "False") == "True":
         user_data_dict = {"id": 111111, "username": "test_user", "first_name": "Tester"}

    if not user_data_dict:
        raise HTTPException(status_code=401, detail="Unauthorized")

    tg_id = user_data_dict.get('id')
    username = user_data_dict.get('username')
    first_name = user_data_dict.get('first_name')

    # Ищем пользователя в БД с ЖАДНОЙ загрузкой товаров (items)
    # Это предотвращает ошибку MissingGreenlet при обращении к user.items
    stmt = select(User).options(selectinload(User.items)).where(User.telegram_id == tg_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        is_admin = (username == ADMIN_USERNAME)
        user = User(
            telegram_id=tg_id,
            username=username,
            first_name=first_name,
            is_admin=is_admin,
            subscription_plan="free"
        )
        db.add(user)
        await db.commit()
        # При refresh тоже нужно подгрузить items, если планируем к ним обращаться, 
        # но для нового юзера список пуст, так что это безопасно.
        await db.refresh(user)
    
    return user

@app.on_event("startup")
async def on_startup():
    await init_db()

# --- ПОЛЬЗОВАТЕЛЬСКИЕ ЭНДПОИНТЫ ---

@app.get("/api/user/me")
async def get_profile(user: User = Depends(get_current_user)):
    """Получить профиль текущего пользователя"""
    # Теперь user.items уже загружен в память, и len() сработает без запроса к БД
    items_count = len(user.items) if user.items else 0
    
    return {
        "id": user.telegram_id,
        "username": user.username,
        "name": user.first_name,
        "plan": user.subscription_plan,
        "is_admin": user.is_admin,
        "items_count": items_count
    }

@app.post("/api/monitor/add/{sku}")
async def add_to_monitor(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Добавить товар в ЛИЧНЫЙ список мониторинга"""
    
    # user.items доступен благодаря selectinload в get_current_user
    current_items = len(user.items) if user.items else 0
    limit = 3 if user.subscription_plan == "free" else 50
    
    if current_items >= limit:
        raise HTTPException(status_code=403, detail=f"Лимит тарифа исчерпан ({limit} товаров).")

    stmt = select(MonitoredItem).where(
        MonitoredItem.user_id == user.id,
        MonitoredItem.sku == sku
    )
    existing = (await db.execute(stmt)).scalars().first()
    
    if existing:
        return {"status": "exists", "message": "Товар уже в списке"}

    new_item = MonitoredItem(user_id=user.id, sku=sku, name="Загрузка...", brand="...")
    db.add(new_item)
    await db.commit()

    task = parse_and_save_sku.delay(sku)
    return {"status": "accepted", "task_id": task.id, "message": "Добавлено в очередь"}

@app.get("/api/monitor/list")
async def get_my_items(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Получить список товаров текущего пользователя"""
    result = await db.execute(
        select(MonitoredItem)
        .where(MonitoredItem.user_id == user.id)
        .order_by(MonitoredItem.id.desc())
    )
    return result.scalars().all()

@app.delete("/api/monitor/delete/{sku}")
async def delete_item(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Удалить товар"""
    stmt = delete(MonitoredItem).where(
        MonitoredItem.user_id == user.id,
        MonitoredItem.sku == sku
    )
    await db.execute(stmt)
    await db.commit()
    return {"status": "deleted"}

@app.get("/api/monitor/history/{sku}")
async def get_history(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Получить историю цен"""
    item_res = await db.execute(
        select(MonitoredItem).where(
            MonitoredItem.user_id == user.id,
            MonitoredItem.sku == sku
        )
    )
    item = item_res.scalars().first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден в вашем списке")
        
    history_res = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.item_id == item.id)
        .order_by(PriceHistory.recorded_at.asc())
    )
    history = history_res.scalars().all()
    
    return {
        "sku": sku,
        "name": item.name,
        "history": [{"date": h.recorded_at.strftime("%d.%m %H:%M"), "wallet": h.wallet_price} for h in history]
    }

# --- SYSTEM & PROXY ---
from celery.result import AsyncResult
from celery_app import celery_app

@app.get("/api/monitor/status/{task_id}")
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    response = {"task_id": task_id, "status": task_result.status}
    if task_result.status == 'SUCCESS':
        response["result"] = task_result.result
    elif task_result.status == 'FAILURE':
        response["error"] = str(task_result.result)
    elif task_result.status == 'PROGRESS':
         response["info"] = task_result.info.get('status', 'В процессе...')
    return response

# --- ADMIN PANEL ---

@app.get("/api/admin/stats")
async def admin_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.is_admin:
        raise HTTPException(403, "Доступ запрещен")
    
    users_count = (await db.execute(select(User))).scalars().all()
    items_count = (await db.execute(select(MonitoredItem))).scalars().all()
    
    return {
        "total_users": len(users_count),
        "total_items_monitored": len(items_count),
        "server_status": "OK"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)