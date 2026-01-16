import os
import io
import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from fpdf import FPDF
from concurrent.futures import ThreadPoolExecutor

from database import get_db, User, MonitoredItem, PriceHistory
from dependencies import get_current_user
from tasks import parse_and_save_sku, get_status
from services.selenium_search import selenium_service

logger = logging.getLogger("Monitoring")
router = APIRouter(prefix="/api", tags=["Monitoring"])

# Экзекьютор нужен ТОЛЬКО для синхронной генерации PDF
executor = ThreadPoolExecutor(max_workers=2)

@router.get("/monitoring/scan/{sku}")
async def scan_product(sku: int):
    """
    Мгновенный скан товара.
    """
    try:
        # Прямой вызов async метода (без executor)
        result = await selenium_service.get_product_details(sku)
        
        if not result.get('valid'):
            raise HTTPException(404, "Товар не найден или ошибка парсинга WB")
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Scan error: {e}")
        raise HTTPException(500, f"Scan failed: {str(e)}")

@router.post("/monitor/add/{sku}")
async def add_to_monitor(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    limits = {"free": 3, "pro": 50, "business": 500}
    limit = limits.get(user.subscription_plan, 3)
    
    count_stmt = select(func.count()).select_from(MonitoredItem).where(MonitoredItem.user_id == user.id)
    current = (await db.execute(count_stmt)).scalar() or 0
    
    if current >= limit:
        raise HTTPException(403, f"Лимит тарифа исчерпан ({limit} шт)")

    stmt = select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku)
    if (await db.execute(stmt)).scalars().first(): 
        return {"status": "exists", "message": "Товар уже в списке"}

    # Исправлено: убран run_in_executor, так как метод асинхронный
    name = "Загрузка..."
    brand = "..."
    try:
        details = await selenium_service.get_product_details(sku)
        if details.get('valid'):
            name = details.get('name', 'Товар WB')
            brand = details.get('brand', '')
    except Exception as e:
        logger.warning(f"Name fetch failed: {e}")

    new_item = MonitoredItem(user_id=user.id, sku=sku, name=name, brand=brand)
    db.add(new_item)
    await db.commit()
    
    task = parse_and_save_sku.delay(sku, user.id)
    return {"status": "accepted", "task_id": task.id, "name": name}

@router.get("/monitor/list")
async def get_my_items(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(MonitoredItem).where(MonitoredItem.user_id == user.id).order_by(MonitoredItem.id.desc())
    items = (await db.execute(stmt)).scalars().all()
    
    data = []
    for i in items:
        last_price_stmt = select(PriceHistory).where(PriceHistory.item_id == i.id).order_by(PriceHistory.recorded_at.desc()).limit(1)
        lp = (await db.execute(last_price_stmt)).scalars().first()
        
        data.append({
            "id": i.id, "sku": i.sku, "name": i.name, "brand": i.brand,
            "prices": [{"wallet_price": lp.wallet_price, "standard_price": lp.standard_price}] if lp else []
        })
    return data

@router.delete("/monitor/delete/{sku}")
async def delete_item(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = delete(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku)
    await db.execute(stmt)
    await db.commit()
    return {"status": "deleted"}

@router.get("/monitor/history/{sku}")
async def get_history(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = (await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku))).scalars().first()
    if not item: raise HTTPException(404, "Item not found in your list")
    
    history = (await db.execute(select(PriceHistory).where(PriceHistory.item_id == item.id).order_by(PriceHistory.recorded_at.asc()))).scalars().all()
    
    return {
        "sku": sku, 
        "name": item.name, 
        "history": [{"date": h.recorded_at.strftime("%d.%m %H:%M"), "wallet": h.wallet_price, "standard": h.standard_price, "base": h.base_price} for h in history]
    }

@router.get("/monitor/status/{task_id}")
def get_status_endpoint(task_id: str): 
    return get_status(task_id)

@router.get("/report/pdf/{sku}")
async def generate_pdf(sku: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.subscription_plan == "free":
        raise HTTPException(403, "Upgrade to PRO")

    item = (await db.execute(select(MonitoredItem).where(MonitoredItem.user_id == user.id, MonitoredItem.sku == sku))).scalars().first()
    if not item: raise HTTPException(404, "Item not found")

    history = (await db.execute(select(PriceHistory).where(PriceHistory.item_id == item.id).order_by(PriceHistory.recorded_at.desc()).limit(100))).scalars().all()

    # Генерацию PDF оставляем в executor, так как FPDF синхронная и тяжелая
    loop = asyncio.get_event_loop()
    pdf_bytes = await loop.run_in_executor(executor, _create_pdf_sync, sku, history)

    return StreamingResponse(
        io.BytesIO(pdf_bytes), 
        media_type='application/pdf', 
        headers={'Content-Disposition': f'attachment; filename="wb_report_{sku}.pdf"'}
    )

def _create_pdf_sync(sku, history):
    """Синхронная функция создания PDF для запуска в executor"""
    pdf = FPDF()
    pdf.add_page()
    
    font_paths = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        './fonts/DejaVuSans.ttf',
        '/usr/share/fonts/TTF/DejaVuSans.ttf'
    ]
    font_loaded = False
    for path in font_paths:
        if os.path.exists(path):
            try:
                pdf.add_font('DejaVu', '', path, uni=True)
                pdf.set_font('DejaVu', '', 14)
                font_loaded = True
                break
            except: continue
            
    if not font_loaded: pdf.set_font("Arial", size=12)

    pdf.cell(0, 10, txt=f"Price Report: SKU {sku}", ln=1, align='C')
    pdf.ln(5)
    
    pdf.set_font_size(10)
    pdf.cell(60, 10, "Date", 1)
    pdf.cell(40, 10, "Wallet", 1)
    pdf.cell(40, 10, "Regular", 1)
    pdf.ln()

    for h in history:
        pdf.cell(60, 10, h.recorded_at.strftime("%Y-%m-%d %H:%M"), 1)
        pdf.cell(40, 10, f"{h.wallet_price}", 1)
        pdf.cell(40, 10, f"{h.standard_price}", 1)
        pdf.ln()

    return pdf.output(dest='S').encode('latin-1')