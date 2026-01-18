import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from dependencies import get_current_user, get_db
from database import User, NotificationSettings
from config.plans import get_limit, get_plan_config

logger = logging.getLogger("NotifyRouter")
router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

class NotifyConfig(BaseModel):
    notify_new_orders: bool
    notify_buyouts: bool
    notify_hourly_stats: bool
    summary_interval: int # 1, 3, 6, 12, 24
    show_funnel: bool
    # show_daily_revenue удален, так как это часть hourly_stats

    class Config:
        from_attributes = True

@router.get("/settings", response_model=NotifyConfig)
async def get_settings(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(NotificationSettings).where(NotificationSettings.user_id == user.id)
    res = await db.execute(stmt)
    settings = res.scalar_one_or_none()
    
    if not settings:
        settings = NotificationSettings(user_id=user.id)
        # Дефолтные настройки
        settings.notify_new_orders = True
        settings.notify_buyouts = True
        settings.notify_hourly_stats = True
        settings.summary_interval = 24
        settings.show_funnel = True
        
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
        
    return settings

@router.post("/settings")
async def update_settings(
    config: NotifyConfig,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Проверка лимитов тарифа
    min_interval = get_limit(user.subscription_plan, "min_summary_interval")
    # Если min_interval не задан (например 0), ставим дефолт 24
    if min_interval == 0: min_interval = 24

    if config.notify_hourly_stats and config.summary_interval < min_interval:
        plan_name = get_plan_config(user.subscription_plan).get("name", "Unknown")
        raise HTTPException(
            status_code=403, 
            detail=f"На тарифе '{plan_name}' минимальный интервал уведомлений — {min_interval} ч."
        )

    stmt = select(NotificationSettings).where(NotificationSettings.user_id == user.id)
    res = await db.execute(stmt)
    settings = res.scalar_one()
    
    settings.notify_new_orders = config.notify_new_orders
    settings.notify_buyouts = config.notify_buyouts
    settings.notify_hourly_stats = config.notify_hourly_stats
    settings.summary_interval = config.summary_interval
    settings.show_funnel = config.show_funnel
    # settings.show_daily_revenue - игнорируем или удаляем из БД если есть миграция
    
    await db.commit()
    return {"status": "ok", "message": "Настройки сохранены"}