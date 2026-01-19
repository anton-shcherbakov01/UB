from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dependencies import get_current_user
from database import User

router = APIRouter(prefix="/api/bidder", tags=["Bidder"])

class CampaignSettingsUpdate(BaseModel):
    campaign_id: int
    is_active: bool
    target_pos: int
    max_bid: int
    min_bid: int
    target_cpa: int
    strategy: str = "pid"

# Maintenance stub response
MAINTENANCE_RESPONSE = {"status": "maintenance", "message": "Module is currently in development"}

@router.get("/auction")
async def check_auction(query: str = None, user: User = Depends(get_current_user)):
    """Stub: Module is currently in development"""
    return MAINTENANCE_RESPONSE

@router.get("/campaigns")
async def get_my_campaigns(user: User = Depends(get_current_user)):
    """Stub: Module is currently in development"""
    return MAINTENANCE_RESPONSE

@router.get("/settings/{campaign_id}")
async def get_campaign_settings(campaign_id: int, user: User = Depends(get_current_user)):
    """Stub: Module is currently in development"""
    return MAINTENANCE_RESPONSE

@router.post("/settings")
async def save_campaign_settings(req: CampaignSettingsUpdate, user: User = Depends(get_current_user)):
    """Stub: Module is currently in development"""
    return MAINTENANCE_RESPONSE

@router.get("/stats/{campaign_id}")
async def get_campaign_stats(campaign_id: int, user: User = Depends(get_current_user)):
    """Stub: Module is currently in development"""
    return MAINTENANCE_RESPONSE

@router.get("/logs")
async def get_bidder_logs(campaign_id: int = None, limit: int = 20, user: User = Depends(get_current_user)):
    """Stub: Module is currently in development"""
    return MAINTENANCE_RESPONSE

@router.get("/dashboard")
async def get_bidder_dashboard(user: User = Depends(get_current_user)):
    """Stub: Module is currently in development"""
    return MAINTENANCE_RESPONSE