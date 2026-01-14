import json
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from database import get_db, User
from dependencies import get_current_user, get_redis_client
from wb_api.statistics import WBStatisticsAPI
from services.supply import supply_service
from tasks.supply import sync_supply_data_task

logger = logging.getLogger("SupplyRouter")
router = APIRouter(prefix="/api/supply", tags=["Supply"])

@router.get("/analysis", response_model=List[dict])
async def get_supply_analysis(
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    refresh: bool = False
):
    """
    Get full supply analysis: Stocks, Velocity, ABC, ROP.
    Data is cached in Redis for 1 hour.
    """
    if not user.wb_api_token:
        raise HTTPException(status_code=400, detail="WB API Token required")

    r_client = get_redis_client()
    cache_key = f"supply:analysis:{user.id}"

    # 1. Try Cache
    if not refresh and r_client:
        cached = r_client.get(cache_key)
        if cached:
            return json.loads(cached)

    # 2. Fetch Real Data
    try:
        wb_api = WBStatisticsAPI(user.wb_api_token)
        # Fetch stocks and orders (demand)
        stocks = await wb_api.get_stocks()
        orders = await wb_api.get_orders(days=30) # 30 days horizon for velocity

        # 3. Analyze
        analysis = supply_service.analyze_supply(stocks, orders)

        # 4. Cache Result (Ex: 3600 seconds)
        if r_client:
            r_client.setex(cache_key, 3600, json.dumps(analysis))
        
        # 5. Background Sync to ClickHouse (for historical retention)
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
    # Simply invalidate cache
    r_client = get_redis_client()
    if r_client:
        r_client.delete(f"supply:analysis:{user.id}")
    return {"status": "ok", "message": "Cache cleared. Reload page."}