from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, timedelta

from database import get_db, User, BidderLog
from dependencies import get_current_user
from wb_api_service import wb_api_service

router = APIRouter(prefix="/api/bidder", tags=["Bidder"])

@router.get("/campaigns")
async def get_my_campaigns(user: User = Depends(get_current_user)):
    """
    Получение списка реальных кампаний пользователя.
    """
    if not user.wb_api_token:
        raise HTTPException(400, "WB API token not connected")
        
    campaigns = await wb_api_service.get_advert_campaigns(user.wb_api_token)
    
    # Обогащаем данными из БД (если есть настройки биддера для этих кампаний)
    # В рамках этой задачи просто возвращаем список
    return campaigns

@router.get("/stats/{campaign_id}")
async def get_campaign_stats(campaign_id: int, user: User = Depends(get_current_user)):
    if not user.wb_api_token:
        raise HTTPException(400, "No Token")
        
    stats = await wb_api_service.get_advert_stats(user.wb_api_token, campaign_id)
    info = await wb_api_service.get_current_bid_info(user.wb_api_token, campaign_id)
    
    return {
        "stats": stats,
        "current": info
    }

@router.get("/logs")
async def get_bidder_logs(
    campaign_id: int = None, 
    limit: int = 20, 
    user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    """
    Получение реальных логов работы биддера из БД.
    """
    stmt = select(BidderLog).where(BidderLog.user_id == user.id)
    
    if campaign_id:
        stmt = stmt.where(BidderLog.campaign_id == campaign_id)
        
    stmt = stmt.order_by(desc(BidderLog.timestamp)).limit(limit)
    
    logs = (await db.execute(stmt)).scalars().all()
    
    return [
        {
            "time": l.timestamp.strftime("%H:%M"),
            "full_date": l.timestamp.isoformat(),
            "campaign_id": l.campaign_id,
            "action": l.action,
            "bid": l.calculated_bid,
            "pos": l.current_pos,
            "saved": l.saved_amount,
            "msg": f"Pos {l.current_pos} -> Target {l.target_pos}. Bid {l.previous_bid} -> {l.calculated_bid}"
        }
        for l in logs
    ]

@router.get("/dashboard")
async def get_bidder_dashboard(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Сводная статистика биддера (реальная).
    """
    # 1. Считаем сэкономленный бюджет за 24 часа
    yesterday = datetime.utcnow() - timedelta(days=1)
    stmt = select(BidderLog).where(
        BidderLog.user_id == user.id,
        BidderLog.timestamp >= yesterday
    )
    logs = (await db.execute(stmt)).scalars().all()
    
    total_saved = sum([l.saved_amount for l in logs if l.saved_amount > 0])
    
    # 2. Количество активных кампаний
    active_count = 0
    if user.wb_api_token:
        camps = await wb_api_service.get_advert_campaigns(user.wb_api_token)
        # Статус 9 - активна
        active_count = len([c for c in camps if c.get('status') == 9])

    return {
        "total_budget_saved": total_saved,
        "campaigns_active": active_count,
        "logs_count_24h": len(logs)
    }