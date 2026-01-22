import os
import json
import logging
import redis
from urllib.parse import parse_qsl
from fastapi import Header, Query, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, update

from database import get_db, User, Lead
from auth_service import AuthService
from celery_app import REDIS_URL

logger = logging.getLogger("Dependencies")

auth_manager = AuthService(os.getenv("BOT_TOKEN", ""))
SUPER_ADMIN_IDS = [901378787] # Замените на ваш ID

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
    start_param = None

    if token:
        if auth_manager.validate_init_data(token):
            try:
                parsed = dict(parse_qsl(token))
                if 'user' in parsed: 
                    user_data_dict = json.loads(parsed['user'])
                if 'start_param' in parsed:
                    start_param = parsed['start_param']
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

    # 1. Поиск пользователя
    stmt = select(User).where(User.telegram_id == tg_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    is_super = tg_id in SUPER_ADMIN_IDS

    # 2. Создание пользователя (если новый)
    if not user:
        try:
            username = user_data_dict.get('username')
            first_name = user_data_dict.get('first_name')
            plan = "strategist" if is_super else "start"
            is_adm = is_super
            
            # --- ПАРТНЕРСКАЯ ЛОГИКА ---
            referrer_id = None
            
            # А. Если перешли по рефке (agent_123)
            if start_param and start_param.startswith('agent_'):
                try:
                    referrer_id = int(start_param.split('_')[1])
                except:
                    pass
            
            # Б. Если не было рефки, проверяем таблицу лидов (Lead Reservation)
            if not referrer_id and username:
                clean_username = username.lower()
                lead_stmt = select(Lead).where(
                    Lead.username == clean_username,
                    Lead.status == 'reserved',
                    Lead.expires_at > text("NOW()")
                )
                lead_res = await db.execute(lead_stmt)
                lead = lead_res.scalars().first()
                if lead:
                    referrer_id = lead.reserved_by_partner_id
                    # Обновляем статус лида на конвертирован
                    lead.status = 'converted'
                    db.add(lead)

            # Создаем юзера
            new_user = User(
                telegram_id=tg_id,
                username=username,
                first_name=first_name,
                is_admin=is_adm,
                subscription_plan=plan,
                referrer_id=referrer_id
            )
            db.add(new_user)
            await db.commit()
            
            # Получаем созданного
            result = await db.execute(stmt)
            user = result.scalars().first()
            
        except Exception as e:
            await db.rollback()
            logger.error(f"User creation error: {e}")
            raise HTTPException(status_code=500, detail="Database error")
            
    # Обновление админских прав при входе
    if user and is_super and not user.is_admin:
        user.is_admin = True
        db.add(user)
        await db.commit()
    
    return user