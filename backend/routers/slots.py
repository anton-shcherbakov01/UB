import logging
import json
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from pydantic import BaseModel, validator

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
    boxTypeName: str = "Короба" 
    boxTypeID: int
    isSortingCenter: bool = False  # <--- Добавили флаг транзита/СЦ

    @validator("boxTypeName", pre=True, always=True)
    def set_name_from_id(cls, v, values):
        # Если имя есть и оно не пустое/не None
        if v and isinstance(v, str):
            return v
        
        # Логика восстановления имени по ID
        box_id = values.get("boxTypeID")
        if box_id == 2:
            return "Монопаллеты"
        if box_id in [0, 1, 5, 6]:
            return "Короба"
        return "Прочее"

@router.get("/coefficients", response_model=List[SlotItem])
async def get_slots(
    user: User = Depends(get_current_user),
    refresh: bool = False
):
    """
    Получение коэффициентов приемки.
    """
    if not user.wb_api_token:
        raise HTTPException(status_code=400, detail="WB API Token required")

    r_client = get_redis_client()
    cache_key = f"slots:coeff:{user.id}"

    if not refresh and r_client:
        cached = r_client.get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

    service = SlotsService(user.wb_api_token)
    data = await service.get_coefficients()

    # Сортировка: Сначала бесплатные, потом дешевые, потом по имени
    data.sort(key=lambda x: (
        0 if x.get('coefficient') == 0 else 1, # Приоритет бесплатным
        x.get('coefficient') if x.get('coefficient') != -1 else 999, # Закрытые (-1) в конец
        x.get('warehouseName', '')
    ))

    if r_client and data:
        r_client.setex(cache_key, 600, json.dumps(data))

    return data