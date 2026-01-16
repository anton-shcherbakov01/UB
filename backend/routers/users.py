import json
from datetime import datetime, timedelta
from typing import Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from pydantic import BaseModel

from database import get_db, User, MonitoredItem, SearchHistory
from dependencies import get_current_user
from wb_api_service import wb_api_service
from tasks import sync_financial_reports
from config.plans import TIERS, ADDONS, get_limit

router = APIRouter(prefix="/api/user", tags=["User"])

class TokenRequest(BaseModel):
    token: str

@router.get("/me")
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Считаем товары
    count_stmt = select(func.count()).select_from(MonitoredItem).where(MonitoredItem.user_id == user.id)
    count = (await db.execute(count_stmt)).scalar() or 0
    
    # Маскируем токен для безопасности
    masked_token = None
    if user.wb_api_token:
        # Показываем первые 5 и последние 4 символа
        if len(user.wb_api_token) > 10:
            masked_token = user.wb_api_token[:5] + "••••••••••" + user.wb_api_token[-4:]
        else:
            masked_token = "••••••••"
    
    # Считаем дни подписки
    days_left = 0
    if user.subscription_expires_at:
        delta = user.subscription_expires_at - datetime.utcnow()
        days_left = max(0, delta.days)

    # Get quota usage info
    from config.plans import get_limit
    ai_limit = get_limit(user.subscription_plan, "ai_requests")
    
    return {
        "id": user.telegram_id,
        "username": user.username,
        "name": user.first_name,
        "plan": user.subscription_plan,
        "is_admin": user.is_admin,
        "items_count": count,
        "has_wb_token": bool(user.wb_api_token),
        "wb_token_preview": masked_token,
        "days_left": days_left,
        "subscription_expires_at": user.subscription_expires_at,
        "ai_requests_used": user.ai_requests_used or 0,
        "ai_requests_limit": ai_limit,
        "extra_ai_balance": user.extra_ai_balance or 0
    }

@router.post("/token")
async def save_wb_token(
    req: TokenRequest, 
    user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    """Сохранение токена API WB и сразу проверка прав"""
    # 1. Проверяем валидность
    is_valid = await wb_api_service.check_token(req.token)
    if not is_valid:
        raise HTTPException(status_code=400, detail="Токен невалиден или API Wildberries недоступно")

    # 2. Сохраняем
    user.wb_api_token = req.token
    db.add(user)
    await db.commit()
    
    # 3. Запускаем первичную синхронизацию в фоне
    sync_financial_reports.delay(user.id)

    # 4. Сразу получаем права, чтобы обновить UI
    scopes = await wb_api_service.get_token_scopes(req.token)

    return {
        "status": "saved", 
        "message": "Токен сохранен", 
        "scopes": scopes
    }

@router.get("/token/scopes")
async def get_token_scopes(user: User = Depends(get_current_user)):
    """
    Возвращает права доступа по полному списку WB.
    """
    # Полный список ключей, которые ожидает фронтенд
    default_scopes = {
        "content": False,       # Контент
        "marketplace": False,   # Маркетплейс
        "analytics": False,     # Аналитика
        "promotion": False,     # Продвижение
        "returns": False,       # Возвраты
        "documents": False,     # Документы
        "statistics": False,    # Статистика
        "finance": False,       # Финансы
        "supplies": False,      # Поставки
        "chat": False,          # Чат с покупателем
        "questions": False,     # Вопросы и отзывы
        "prices": False,        # Цены и скидки
        "users": False          # Пользователи
    }

    if not user.wb_api_token:
        return default_scopes
    
    # Получаем реальные права от сервиса WB API
    # Сервис должен вернуть словарь. Мы мержим его с дефолтным, 
    # чтобы гарантировать наличие всех ключей.
    try:
        real_scopes = await wb_api_service.get_token_scopes(user.wb_api_token)
        # Обновляем дефолтные значения теми, что пришли (если пришли)
        # Логика: если в real_scopes есть ключ - берем его значение, иначе False
        result = {key: real_scopes.get(key, False) for key in default_scopes}
        return result
    except Exception:
        # Если ошибка связи с WB, возвращаем все False
        return default_scopes

@router.delete("/token")
async def delete_wb_token(
    user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    user.wb_api_token = None
    db.add(user)
    await db.commit()
    return {"status": "deleted"}

@router.get("/tariffs")
async def get_tariffs(user: User = Depends(get_current_user)):
    """
    Возвращает список тарифов из config/plans.py с переведенными названиями и описаниями.
    """
    tariffs = []
    
    # Map plan IDs to display info
    plan_mapping = {
        "start": {
            "id": "start",
            "features_display": [
                "История: 7 дней",
                "5 AI-запросов / мес",
                "Слоты и уведомления",
                "P&L (демо: вчера)"
            ]
        },
        "analyst": {
            "id": "analyst",
            "features_display": [
                "История: 60 дней",
                "100 AI-запросов / мес",
                "Слоты и уведомления",
                "P&L (полный доступ)",
                "Форензика возвратов"
            ],
            "is_best": True
        },
        "strategist": {
            "id": "strategist",
            "features_display": [
                "История: 365 дней",
                "1000 AI-запросов / мес",
                "Слоты и уведомления",
                "P&L экспорт",
                "Форензика + Cash Gap",
                "Приоритетный опрос"
            ]
        }
    }
    
    for plan_key in ["start", "analyst", "strategist"]:
        plan_config = TIERS.get(plan_key, {})
        if not plan_config:
            continue
            
        plan_info = plan_mapping.get(plan_key, {})
        price = plan_config.get("price", 0)
        
        tariffs.append({
            "id": plan_key,
            "name": plan_config.get("name", plan_key).replace(" (Free)", "").replace(" (Pro)", "").replace(" (Business)", ""),
            "price": f"{price} ₽" if price > 0 else "0 ₽",
            "stars": 0,  # Stars payment can be added later if needed
            "features": plan_info.get("features_display", []),
            "current": user.subscription_plan == plan_key,
            "is_best": plan_info.get("is_best", False)
        })
    
    return tariffs
# --- History Routes (без изменений, кратко) ---
@router.get("/history")
async def get_user_history(
    request_type: Optional[str] = Query(None), 
    user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    stmt = select(SearchHistory).where(SearchHistory.user_id == user.id)
    if request_type: stmt = stmt.where(SearchHistory.request_type == request_type)
    stmt = stmt.order_by(SearchHistory.created_at.desc()).limit(50)
    res = await db.execute(stmt)
    history = res.scalars().all()
    result = []
    for h in history:
        try: data = json.loads(h.result_json) if h.result_json else {}
        except: data = {}
        result.append({"id": h.id, "sku": h.sku, "type": h.request_type, "title": h.title, "created_at": h.created_at, "data": data})
    return result

@router.delete("/history")
async def clear_user_history(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(delete(SearchHistory).where(SearchHistory.user_id == user.id))
    await db.commit()
    return {"status": "cleared"}