import logging
import json
from fastapi import APIRouter, Depends, HTTPException, Body
from typing import List, Optional
from pydantic import BaseModel, validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from dependencies import get_current_user, get_redis_client, get_db
from database import User, SlotMonitor
from services.slots_service import SlotsService

logger = logging.getLogger("SlotsRouter")
router = APIRouter(prefix="/api/slots", tags=["Slots"])

# =======================
# 1. MODELS (Обязательно в начале!)
# =======================

class MonitorCreate(BaseModel):
    warehouse_id: int
    warehouse_name: str
    target_coefficient: int = 0  # 0 (бесплатно) или 1
    box_type: str = "all"

# Эта модель вызывала ошибку, если стояла ниже
class MonitorResponse(MonitorCreate):
    id: int
    is_active: bool

    class Config:
        orm_mode = True

class SlotItem(BaseModel):
    date: str
    coefficient: int
    warehouseID: int
    warehouseName: str
    boxTypeName: str = "Короба"
    boxTypeID: int
    isSortingCenter: bool = False

    @validator("boxTypeName", pre=True, always=True)
    def set_name_from_id(cls, v, values):
        if v and isinstance(v, str): return v
        box_id = values.get("boxTypeID")
        return "Монопаллеты" if box_id == 2 else "Короба"

# =======================
# 2. ENDPOINTS
# =======================

@router.get("/coefficients", response_model=List[SlotItem])
async def get_slots(user: User = Depends(get_current_user), refresh: bool = False):
    """Получение коэффициентов (логика с кешем)"""
    if not user.wb_api_token:
        raise HTTPException(status_code=400, detail="WB API Token required")

    r_client = get_redis_client()
    cache_key = f"slots:coeff:{user.id}"

    if not refresh and r_client:
        cached = r_client.get(cache_key)
        if cached:
            try: return json.loads(cached)
            except: pass

    service = SlotsService(user.wb_api_token)
    data = await service.get_coefficients()
    
    # Сортировка
    data.sort(key=lambda x: (
        0 if x.get('coefficient') == 0 else 1,
        x.get('coefficient') if x.get('coefficient') != -1 else 999,
        x.get('warehouseName', '')
    ))

    if r_client and data:
        r_client.setex(cache_key, 600, json.dumps(data))

    return data

# --- Monitoring (Bot) Endpoints ---

@router.get("/monitors", response_model=List[MonitorResponse])
async def get_monitors(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Список складов на отслеживании"""
    result = await db.execute(select(SlotMonitor).where(SlotMonitor.user_id == user.id))
    monitors = result.scalars().all()
    return monitors

@router.post("/monitors", response_model=MonitorResponse)
async def add_monitor(
    data: MonitorCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Добавить склад в отслеживание"""
    # Проверка дублей
    existing = await db.execute(select(SlotMonitor).where(
        SlotMonitor.user_id == user.id,
        SlotMonitor.warehouse_id == data.warehouse_id
    ))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Этот склад уже отслеживается")

    monitor = SlotMonitor(
        user_id=user.id,
        warehouse_id=data.warehouse_id,
        warehouse_name=data.warehouse_name,
        target_coefficient=data.target_coefficient,
        box_type=data.box_type,
        is_active=True
    )
    db.add(monitor)
    await db.commit()
    await db.refresh(monitor)
    return monitor

@router.delete("/monitors/{warehouse_id}")
async def delete_monitor(
    warehouse_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Удалить склад из отслеживания"""
    await db.execute(delete(SlotMonitor).where(
        SlotMonitor.user_id == user.id, 
        SlotMonitor.warehouse_id == warehouse_id
    ))
    await db.commit()
    return {"status": "deleted"}