import os
import json
import logging
import redis
from urllib.parse import parse_qsl
from fastapi import Header, Query, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
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
        if auth_manager.validate_init_data(token):
            try:
                parsed = dict(parse_qsl(token))
                if 'user' in parsed: 
                    user_data_dict = json.loads(parsed['user'])
            except Exception as e: 
                logger.error(f"Auth parse error: {e}")
        else:
             # Fallback для локальной разработки
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

    # 1. Сначала пробуем найти
    stmt = select(User).where(User.telegram_id == tg_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    is_super = tg_id in SUPER_ADMIN_IDS

    if not user:
        # 2. Если нет - пробуем создать через RAW SQL с ON CONFLICT DO NOTHING
        # Это предотвращает ошибку "duplicate key value violates unique constraint" в логах Postgres
        # и устраняет состояние гонки.
        try:
            username = user_data_dict.get('username')
            first_name = user_data_dict.get('first_name')
            plan = "strategist" if is_super else "start"  # Админы получают самый полный тариф
            is_adm = is_super
            
            # Используем text() для raw query (надежнее всего для upsert в данной конфигурации)
            insert_query = text("""
                INSERT INTO users (telegram_id, username, first_name, is_admin, subscription_plan, created_at)
                VALUES (:tg_id, :username, :first_name, :is_admin, :plan, NOW())
                ON CONFLICT (telegram_id) DO NOTHING
            """)
            
            await db.execute(insert_query, {
                "tg_id": tg_id,
                "username": username,
                "first_name": first_name,
                "is_admin": is_adm,
                "plan": plan
            })
            await db.commit()
            
            # 3. Достаем юзера заново (он точно есть теперь)
            result = await db.execute(stmt)
            user = result.scalars().first()
            
        except Exception as e:
            await db.rollback()
            logger.error(f"User creation error: {e}")
            raise HTTPException(status_code=500, detail="Database error")
            
    # Если юзер уже был, обновляем только админские права (не трогаем тариф - админ может менять его сам)
    if user and is_super and not user.is_admin:
        user.is_admin = True
        # Не меняем subscription_plan - админ может сам выбрать тариф через админ-панель
        db.add(user)
        await db.commit()
    
    return user