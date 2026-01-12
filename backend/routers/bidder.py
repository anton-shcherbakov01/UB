from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from datetime import datetime, timedelta
from pydantic import BaseModel

from database import get_db, User, BidderLog, BidderSettings
from dependencies import get_current_user
from wb_api_service import wb_api_service

router = APIRouter(prefix="/api/bidder", tags=["Bidder"])

class CampaignSettingsUpdate(BaseModel):
    campaign_id: int
    is_active: bool
    target_pos: int
    max_bid: int
    min_bid: int
    target_cpa: int
    strategy: str = "pid"

@router.get("/campaigns")
async def get_my_campaigns(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not user.wb_api_token:
        raise HTTPException(400, "WB API token not connected")
    try:
        # 1. Fetch live campaigns from WB
        campaigns = await wb_api_service.get_advert_campaigns(user.wb_api_token)
        
        # 2. Fetch our local settings
        camp_ids = [c['id'] for c in campaigns]
        settings_res = await db.execute(select(BidderSettings).where(BidderSettings.campaign_id.in_(camp_ids)))
        settings_map = {s.campaign_id: s for s in settings_res.scalars().all()}
        
        # 3. Merge data
        result = []
        for c in campaigns:
            s = settings_map.get(c['id'])
            c['bidder_enabled'] = s.is_active if s else False
            c['target_pos'] = s.target_pos if s else 1
            c['strategy'] = s.strategy if s else 'pid'
            result.append(c)
            
        return result
    except Exception as e:
        # Return empty list on error to prevent UI crash
        return []

@router.get("/settings/{campaign_id}")
async def get_campaign_settings(campaign_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(BidderSettings).where(BidderSettings.campaign_id == campaign_id, BidderSettings.user_id == user.id)
    settings = (await db.execute(stmt)).scalars().first()
    
    if not settings:
        return {
            "campaign_id": campaign_id, "is_active": False,
            "target_pos": 1, "max_bid": 500, "min_bid": 125,
            "target_cpa": 0, "strategy": "pid"
        }
    return settings

@router.post("/settings")
async def save_campaign_settings(req: CampaignSettingsUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(BidderSettings).where(BidderSettings.campaign_id == req.campaign_id, BidderSettings.user_id == user.id)
    settings = (await db.execute(stmt)).scalars().first()
    
    if settings:
        settings.is_active = req.is_active
        settings.target_pos = req.target_pos
        settings.max_bid = req.max_bid
        settings.min_bid = req.min_bid
        settings.target_cpa = req.target_cpa
        settings.strategy = req.strategy
        settings.updated_at = datetime.utcnow()
    else:
        settings = BidderSettings(
            user_id=user.id,
            campaign_id=req.campaign_id,
            is_active=req.is_active,
            target_pos=req.target_pos,
            max_bid=req.max_bid,
            min_bid=req.min_bid,
            target_cpa=req.target_cpa,
            strategy=req.strategy
        )
        db.add(settings)
    
    await db.commit()
    return {"status": "saved", "is_active": req.is_active}

@router.get("/stats/{campaign_id}")
async def get_campaign_stats(campaign_id: int, user: User = Depends(get_current_user)):
    if not user.wb_api_token: raise HTTPException(400, "No Token")
    try:
        stats = await wb_api_service.get_advert_stats(user.wb_api_token, campaign_id)
        info = await wb_api_service.get_current_bid_info(user.wb_api_token, campaign_id)
        return {"stats": stats, "current": info}
    except:
        raise HTTPException(503, "WB Advert API Unavailable")

@router.get("/logs")
async def get_bidder_logs(campaign_id: int = None, limit: int = 20, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(BidderLog).where(BidderLog.user_id == user.id)
    if campaign_id: stmt = stmt.where(BidderLog.campaign_id == campaign_id)
    stmt = stmt.order_by(desc(BidderLog.timestamp)).limit(limit)
    logs = (await db.execute(stmt)).scalars().all()
    
    return [{
        "time": l.timestamp.strftime("%H:%M"),
        "full_date": l.timestamp.isoformat(),
        "campaign_id": l.campaign_id,
        "action": l.action,
        "bid": l.calculated_bid,
        "pos": l.current_pos,
        "saved": l.saved_amount,
        "msg": f"Pos {l.current_pos} -> {l.target_pos} | Bid {l.calculated_bid} ({l.action})"
    } for l in logs]

@router.get("/dashboard")
async def get_bidder_dashboard(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    yesterday = datetime.utcnow() - timedelta(days=1)
    stmt = select(BidderLog).where(BidderLog.user_id == user.id, BidderLog.timestamp >= yesterday)
    logs = (await db.execute(stmt)).scalars().all()
    total_saved = sum([l.saved_amount for l in logs if l.saved_amount > 0])
    
    active_stmt = select(BidderSettings).where(BidderSettings.user_id == user.id, BidderSettings.is_active == True)
    active_count = len((await db.execute(active_stmt)).scalars().all())

    return {
        "total_budget_saved": total_saved,
        "campaigns_active": active_count,
        "logs_count_24h": len(logs)
    }