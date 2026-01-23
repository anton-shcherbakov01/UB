import logging
import json
import io
import asyncio
from datetime import datetime
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func # <--- ВАЖНО: добавлен func

from dependencies import get_current_user, get_redis_client, get_db
from database import User, SlotMonitor
from services.slots_service import SlotsService

logger = logging.getLogger("SlotsRouter")
router = APIRouter(prefix="/api/slots", tags=["Slots"])

executor = ThreadPoolExecutor(max_workers=2)

# =======================
# 1. MODELS
# =======================

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

# Модель для создания задачи (V1 - Legacy)
class MonitorCreate(BaseModel):
    warehouse_id: int
    warehouse_name: str
    target_coefficient: int = 0
    box_type: str = "all"

# Модель для создания умной задачи (V2 - Sniper)
class MonitorCreateV2(BaseModel):
    warehouse_id: int
    warehouse_name: str
    box_type_id: int = 1 # 1=Короба, 2=Паллеты
    date_from: datetime
    date_to: datetime
    target_coefficient: int
    auto_book: bool = False
    preorder_id: Optional[int] = None

# Модель ответа (обновленная структура БД)
class MonitorResponse(BaseModel):
    id: int
    warehouse_id: int
    warehouse_name: str
    box_type_id: int = 1
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    target_coefficient: int = 0
    auto_book: bool = False
    is_active: bool
    
    class Config:
        orm_mode = True

# =======================
# 2. ENDPOINTS
# =======================

@router.get("/coefficients", response_model=List[SlotItem])
async def get_slots(user: User = Depends(get_current_user), refresh: bool = False):
    """Получение коэффициентов (логика с кешем)"""
    if not user.wb_api_token:
        # Возвращаем пустой список, чтобы не ломать фронтенд ошибкой
        return []

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

# --- Monitoring Endpoints ---

@router.get("/monitors", response_model=List[MonitorResponse])
async def get_monitors(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Список активных задач на отслеживание"""
    result = await db.execute(select(SlotMonitor).where(SlotMonitor.user_id == user.id))
    monitors = result.scalars().all()
    
    # Небольшая обработка для старых записей, где новые поля могут быть NULL
    cleaned_monitors = []
    for m in monitors:
        if m.box_type_id is None: m.box_type_id = 1
        if m.target_coefficient is None: m.target_coefficient = 0
        cleaned_monitors.append(m)
        
    return cleaned_monitors

@router.post("/monitors", response_model=MonitorResponse)
async def add_monitor_legacy(
    data: MonitorCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Добавить склад в отслеживание (Legacy V1)"""
    # Проверка дублей (упрощенная)
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
        # Заполняем новые поля дефолтами для старого API
        box_type_id=1, 
        date_from=datetime.now(),
        date_to=datetime.now(),
        is_active=True
    )
    db.add(monitor)
    await db.commit()
    await db.refresh(monitor)
    return monitor

@router.post("/monitors/v2")
async def create_monitor_v2(
    data: MonitorCreateV2,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Проверка прав на авто-бронь
    if data.auto_book:
        if user.subscription_plan == 'start':
            raise HTTPException(403, "Авто-бронирование доступно только на PRO тарифе и выше")
        if not data.preorder_id:
            raise HTTPException(400, "Для авто-бронирования необходим ID поставки (preorder_id)")

    # Проверка лимитов
    current_count = (await db.execute(select(func.count()).select_from(SlotMonitor).where(SlotMonitor.user_id == user.id))).scalar()
    limit = 50 if user.subscription_plan != 'start' else 3
    
    if current_count >= limit:
        raise HTTPException(403, f"Лимит мониторов исчерпан ({limit})")

    # --- FIX: Убираем временную зону из дат для совместимости с PostgreSQL ---
    clean_date_from = data.date_from.replace(tzinfo=None)
    clean_date_to = data.date_to.replace(tzinfo=None)

    monitor = SlotMonitor(
        user_id=user.id,
        warehouse_id=data.warehouse_id,
        warehouse_name=data.warehouse_name,
        box_type_id=data.box_type_id,
        date_from=clean_date_from, # Используем очищенную дату
        date_to=clean_date_to,     # Используем очищенную дату
        target_coefficient=data.target_coefficient,
        auto_book=data.auto_book,
        preorder_id=data.preorder_id,
        is_active=True
    )
    db.add(monitor)
    await db.commit()
    return {"status": "ok", "message": "Снайпер запущен"}

@router.delete("/monitors/{id}")
async def delete_monitor(
    id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Удалить задачу по ID"""
    await db.execute(delete(SlotMonitor).where(
        SlotMonitor.user_id == user.id, 
        SlotMonitor.id == id
    ))
    await db.commit()
    return {"status": "deleted"}

@router.get("/report/slots-pdf")
async def generate_slots_pdf(user: User = Depends(get_current_user)):
    """Generate Slots analysis PDF report"""
    if not user.wb_api_token:
        raise HTTPException(status_code=400, detail="WB API Token required")
    
    # Get slots data
    r_client = get_redis_client()
    cache_key = f"slots:coeff:{user.id}"
    
    slots_data = []
    if r_client:
        cached = r_client.get(cache_key)
        if cached:
            try:
                slots_data = json.loads(cached)
            except:
                pass
    
    if not slots_data:
        # Fetch fresh data
        service = SlotsService(user.wb_api_token)
        slots_data = await service.get_coefficients()
    
    # Generate PDF in executor
    from services.pdf_generator import pdf_generator
    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(
        executor,
        pdf_generator.create_slots_pdf,
        slots_data
    )
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type='application/pdf',
        headers={'Content-Disposition': 'attachment; filename="slots_analysis.pdf"'}
    )