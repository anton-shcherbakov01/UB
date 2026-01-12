import os
import json
import logging
import redis
from urllib.parse import parse_qsl
from fastapi import Header, Query, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database import get_db, User
from auth_service import AuthService
from celery_app import REDIS_URL

logger = logging.getLogger("Dependencies")

# Настройки
auth_manager = AuthService(os.getenv("BOT_TOKEN", ""))
SUPER_ADMIN_IDS = [901378787]

# Redis Client (Singleton for DI)
try:
    r_client = redis.from_url(REDIS_URL, decode_responses=True)
except Exception as e:
    logger.error(f"Redis connect error in dependencies: {e}")
    r_client = None

def get_redis_client():
    return r_client

async def get_current_user(
    x_tg_data: str = Header(None, alias="X-TG-Data"),
    x_tg_data_query: str = Query(None, alias="x_tg_data"),
    db: AsyncSession = Depends(get_db)
) -> User:
    token = x_tg_data if x_tg_data else x_tg_data_query
    user_data_dict = None

    if token:
        # Пробуем валидацию
        if auth_manager.validate_init_data(token):
            try:
                parsed = dict(parse_qsl(token))
                if 'user' in parsed: 
                    user_data_dict = json.loads(parsed['user'])
            except Exception as e: 
                logger.error(f"Auth parse error: {e}")
        else:
             # Попытка парсинга даже если валидация не прошла (для локальных тестов)
             try:
                parsed = dict(parse_qsl(token))
                if 'user' in parsed: 
                    user_data_dict = json.loads(parsed['user'])
             except:
                 pass

    # Fallback для отладки
    if not user_data_dict and os.getenv("DEBUG_MODE", "False") == "True":
         user_data_dict = {"id": 901378787, "username": "debug_user", "first_name": "Debug"}

    if not user_data_dict:
        raise HTTPException(status_code=401, detail="Unauthorized")

    tg_id = user_data_dict.get('id')
    if not tg_id:
        raise HTTPException(status_code=401, detail="Invalid user data")

    stmt = select(User).where(User.telegram_id == tg_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    # FORCE ADMIN RIGHTS
    is_super = tg_id in SUPER_ADMIN_IDS

    if not user:
        # Защита от Race Condition при создании пользователя
        try:
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
        except IntegrityError:
            await db.rollback()
            stmt = select(User).where(User.telegram_id == tg_id)
            result = await db.execute(stmt)
            user = result.scalars().first()
            
            if not user:
                raise HTTPException(status_code=500, detail="Database error during user creation")
    else:
        # Если юзер уже есть, обновляем права (для суперадмина)
        if is_super and (not user.is_admin or user.subscription_plan != "business"):
            user.is_admin = True
            user.subscription_plan = "business"
            db.add(user)
            await db.commit()
            await db.refresh(user)
    
    return user