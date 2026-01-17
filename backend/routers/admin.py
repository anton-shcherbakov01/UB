from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from datetime import datetime, timedelta

from database import get_db, User, MonitoredItem
from dependencies import get_current_user
from config.plans import TIERS

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
    if plan_config.get("price", 0) > 0:
        user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
    else:
        user.subscription_expires_at = None
    
    # Сбрасываем использование квот
    user.ai_requests_used = 0
    user.extra_ai_balance = 0
    user.usage_reset_date = datetime.utcnow() + timedelta(days=30)
    
    # Сохраняем изменения
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Убеждаемся, что изменения применены
    await db.refresh(user, ["subscription_plan", "subscription_expires_at", "ai_requests_used", "usage_reset_date"])
    
    return {
        "status": "success",
        "message": f"Тариф изменен на {plan_config.get('name', request.plan_id)}",
        "plan": user.subscription_plan,
        "plan_name": plan_config.get("name", request.plan_id),
        "expires_at": user.subscription_expires_at.isoformat() if user.subscription_expires_at else None
    }