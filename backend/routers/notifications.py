import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from dependencies import get_current_user, get_db
from database import User, NotificationSettings

logger = logging.getLogger("NotifyRouter")
router = APIRouter(prefix="/api/notifications", tags=["Notifications"])

class NotifyConfig(BaseModel):
    notify_new_orders: bool
    notify_buyouts: bool
    notify_hourly_stats: bool
    show_daily_revenue: bool
    show_funnel: bool

@router.get("/settings", response_model=NotifyConfig)
async def get_settings(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(NotificationSettings).where(NotificationSettings.user_id == user.id)
    res = await db.execute(stmt)
    settings = res.scalar_one_or_none()
    
    if not settings:
        # Создаем дефолтные
        settings = NotificationSettings(user_id=user.id)
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
    stmt = select(NotificationSettings).where(NotificationSettings.user_id == user.id)
    res = await db.execute(stmt)
    settings = res.scalar_one()
    
    settings.notify_new_orders = config.notify_new_orders
    settings.notify_buyouts = config.notify_buyouts
    settings.notify_hourly_stats = config.notify_hourly_stats
    settings.show_daily_revenue = config.show_daily_revenue
    settings.show_funnel = config.show_funnel
    
    await db.commit()
    return {"status": "ok"}