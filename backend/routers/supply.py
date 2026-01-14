import json
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel

from database import get_db, User, SupplySettings
from dependencies import get_current_user, get_redis_client
from wb_api.statistics import WBStatisticsAPI
from services.supply import supply_service
from tasks.supply import sync_supply_data_task

logger = logging.getLogger("SupplyRouter")
router = APIRouter(prefix="/api/supply", tags=["Supply"])

# --- Pydantic Models for Input ---
class SupplySettingsSchema(BaseModel):
    lead_time: int
    min_stock_days: int
    abc_a_share: float

# --- Helpers ---
async def get_or_create_settings(session: Session, user_id: int) -> SupplySettings:
    """Helper to fetch settings or create default"""
    stmt = select(SupplySettings).where(SupplySettings.user_id == user_id)
    result = session.execute(stmt) # Synchronous execute wrapper if needed, or await if async
    # Since we are using Depends(get_db) which might yield async session in previous full context,
    # but based on standard FastAPI + SQLAlchemy usage often shown, I will assume async session usage:
    settings = result.scalar_one_or_none()
    
    if not settings:
        settings = SupplySettings(
            user_id=user_id,
            lead_time=7,        # Default 7 days delivery
            min_stock_days=14,  # Default safety stock
            abc_a_share=80.0    # Pareto principle
        )
        session.add(settings)
        await session.commit()
        await session.refresh(settings)
    
    return settings

# --- Endpoints ---

@router.get("/settings", response_model=SupplySettingsSchema)
async def get_settings(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user supply settings"""
    settings = await get_or_create_settings(db, user.id)
    return {
        "lead_time": settings.lead_time,
        "min_stock_days": settings.min_stock_days,
        "abc_a_share": settings.abc_a_share
    }

@router.post("/settings")
async def update_supply_settings(
    update_data: SupplySettingsSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update settings and invalidate cache"""
    settings = await get_or_create_settings(db, user.id)
    
    settings.lead_time = update_data.lead_time
    settings.min_stock_days = update_data.min_stock_days
    settings.abc_a_share = update_data.abc_a_share
    
    await db.commit()
    
    # Invalidate cache so next analysis uses new settings
    r_client = get_redis_client()
    if r_client:
        r_client.delete(f"supply:analysis:{user.id}")
        
    return {"status": "updated", "settings": update_data.dict()}

@router.get("/analysis", response_model=List[dict])
async def get_supply_analysis(
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    refresh: bool = False,
    db: Session = Depends(get_db) 
):
    """
    Get full supply analysis: Stocks, Velocity, ABC, ROP.
    Uses user-specific SupplySettings (Lead Time, ABC share).
    """
    if not user.wb_api_token:
        # Return empty list or error code handled by frontend
        # Assuming empty list lets frontend show "Add Token" empty state
        raise HTTPException(status_code=400, detail="WB API Token required")

    r_client = get_redis_client()
    cache_key = f"supply:analysis:{user.id}"

    # 1. Try Cache
    if not refresh and r_client:
        cached = r_client.get(cache_key)
        if cached:
            return json.loads(cached)

    try:
        # 2. Get Settings from DB
        settings = await get_or_create_settings(db, user.id)
        
        config = {
            "lead_time": settings.lead_time,
            "min_stock_days": settings.min_stock_days,
            "abc_a_share": settings.abc_a_share
        }

        # 3. Fetch Real Data from WB
        wb_api = WBStatisticsAPI(user.wb_api_token)
        stocks, orders = await wb_api.get_turnover_data()

        # 4. Analyze using Config
        analysis = supply_service.analyze_supply(stocks, orders, config)

        # 5. Cache Result (1 hour)
        if r_client:
            r_client.setex(cache_key, 3600, json.dumps(analysis))
        
        # 6. Background Sync
        background_tasks.add_task(sync_supply_data_task, user.id, stocks, orders)

        return analysis

    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Supply analysis error: {e}")
        raise HTTPException(status_code=500, detail="Internal analysis error")

@router.post("/refresh")
async def refresh_supply_data(user: User = Depends(get_current_user)):
    """Force refresh data from WB"""
    r_client = get_redis_client()
    if r_client:
        r_client.delete(f"supply:analysis:{user.id}")
    return {"status": "ok", "message": "Cache cleared"}