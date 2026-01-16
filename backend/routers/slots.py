import logging
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional, Any
from pydantic import BaseModel, validator
from datetime import datetime

from dependencies import get_current_user, get_redis_client
from database import User
from services.slots_service import SlotsService

logger = logging.getLogger("SlotsRouter")
router = APIRouter(prefix="/api/slots", tags=["Slots"])

class SlotItem(BaseModel):
    date: str
    coefficient: int
    warehouseID: int
    warehouseName: str
    boxTypeName: str = "Короба" # Дефолтное значение
    boxTypeID: int

    # Валидатор для заполнения пропущенных имен на основе ID
    @validator("boxTypeName", pre=True, always=True)
    def set_name_from_id(cls, v, values):
        if v is not None:
            return v
        
        # Если имя не пришло, пробуем определить по ID
        box_id = values.get("boxTypeID")
        
        # ID 2 - это обычно Монопаллеты
        if box_id == 2:
            return "Монопаллеты"
        
        # Остальные (0, 1, 5, 6) чаще всего относятся к Коробам или смешанным типам
        return "Короба"

@router.get("/coefficients", response_model=List[SlotItem])
async def get_slots(
    user: User = Depends(get_current_user),
    refresh: bool = False
):
    """
    Get warehouse acceptance coefficients.
    Uses Redis caching (10 minutes) to avoid hitting WB API limits.
    """
    if not user.wb_api_token:
        raise HTTPException(status_code=400, detail="WB API Token required")

    r_client = get_redis_client()
    cache_key = f"slots:coeff:{user.id}"

    # 1. Try Cache
    if not refresh and r_client:
        cached = r_client.get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

    # 2. Fetch Live
    service = SlotsService(user.wb_api_token)
    data = await service.get_coefficients()

    # 3. Sort by 'Free' (0) then 'Base' (1), then by Warehouse Name
    # Priority: Free slots first!
    # Используем .get() для безопасности, если структура API изменится
    data.sort(key=lambda x: (x.get('coefficient', 99), x.get('warehouseName', '')))

    # 4. Cache
    if r_client and data:
        r_client.setex(cache_key, 600, json.dumps(data))  # 10 min TTL

    return data