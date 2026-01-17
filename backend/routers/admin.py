import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from datetime import datetime, timedelta

from database import get_db, User, MonitoredItem
from dependencies import get_current_user
from config.plans import TIERS

logger = logging.getLogger("Admin")
router = APIRouter(prefix="/api/admin", tags=["Admin"])

class PlanChangeRequest(BaseModel):
    plan_id: str

@router.get("/stats")
async def get_admin_stats(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.is_admin: raise HTTPException(403, "Forbidden")
    users = (await db.execute(select(func.count(User.id)))).scalar()
    items = (await db.execute(select(func.count(MonitoredItem.id)))).scalar()
    return {"total_users": users, "total_items_monitored": items, "server_status": "Online (v2.0)"}

@router.post("/set-plan")
async def set_user_plan(
    request: PlanChangeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Изменение тарифа текущего пользователя (для админов для тестирования).
    """
    if not user.is_admin:
        raise HTTPException(403, "Forbidden")
    
    # Проверяем, что план существует
    if request.plan_id not in TIERS:
        raise HTTPException(400, detail=f"Неверный план. Доступные: {', '.join(TIERS.keys())}")
    
    # Обновляем план пользователя
    user.subscription_plan = request.plan_id
    
    # Если план не бесплатный, устанавливаем срок действия подписки на 30 дней
    plan_config = TIERS[request.plan_id]
    now = datetime.utcnow()
    if plan_config.get("price", 0) > 0:
        user.subscription_expires_at = now + timedelta(days=30)
    else:
        user.subscription_expires_at = None
    
    # Сбрасываем использование квот
    user.ai_requests_used = 0
    user.extra_ai_balance = 0
    user.usage_reset_date = now + timedelta(days=30)
    
    # Сохраняем изменения - используем merge для безопасности
    # Это гарантирует, что объект будет правильно обновлен в сессии
    merged_user = await db.merge(user)
    
    # Flush перед commit для гарантии записи изменений
    await db.flush()
    
    # Commit транзакции
    await db.commit()
    
    # Обновляем объект из БД, чтобы получить актуальные значения
    await db.refresh(merged_user, attribute_names=["subscription_plan", "subscription_expires_at", "ai_requests_used", "extra_ai_balance", "usage_reset_date"])
    
    # Обновляем оригинальный объект значениями из merged объекта
    user.subscription_plan = merged_user.subscription_plan
    user.subscription_expires_at = merged_user.subscription_expires_at
    user.ai_requests_used = merged_user.ai_requests_used
    user.extra_ai_balance = merged_user.extra_ai_balance
    user.usage_reset_date = merged_user.usage_reset_date
    
    # Логируем успешное изменение для отладки
    logger.info(f"User {user.id} (telegram_id={user.telegram_id}) plan changed to {request.plan_id}")
    
    return {
        "status": "success",
        "message": f"Тариф изменен на {plan_config.get('name', request.plan_id)}",
        "plan": user.subscription_plan,
        "plan_name": plan_config.get("name", request.plan_id),
        "expires_at": user.subscription_expires_at.isoformat() if user.subscription_expires_at else None
    }