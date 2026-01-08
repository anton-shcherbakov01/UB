import os
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from celery.result import AsyncResult
from typing import List

from database import init_db, get_db, MonitoredItem, PriceHistory
from celery_app import celery_app
from tasks import parse_and_save_sku
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="WB Analytics Pro")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def on_startup():
    await init_db()

# --- MONITORING API ---

@app.post("/api/monitor/add/{sku}")
async def add_to_monitor(sku: int):
    """Добавить товар в базу мониторинга (запускает парсинг немедленно)"""
    task = parse_and_save_sku.delay(sku)
    return {"status": "accepted", "task_id": task.id, "message": "Товар добавлен в трекер"}

@app.get("/api/monitor/list")
async def get_monitored_items(db: AsyncSession = Depends(get_db)):
    """Получить список всех отслеживаемых товаров"""
    result = await db.execute(select(MonitoredItem).order_by(MonitoredItem.id.desc()))
    items = result.scalars().all()
    return items

@app.get("/api/monitor/history/{sku}")
async def get_price_history(sku: int, db: AsyncSession = Depends(get_db)):
    """Получить историю цен для графика"""
    # Находим ID товара
    item_res = await db.execute(select(MonitoredItem).where(MonitoredItem.sku == sku))
    item = item_res.scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден в мониторинге")
    
    # Берем историю
    history_res = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.item_id == item.id)
        .order_by(PriceHistory.recorded_at.asc())
    )
    history = history_res.scalars().all()
    
    # Формируем данные для графика (Recharts)
    chart_data = [
        {
            "date": h.recorded_at.strftime("%d.%m %H:%M"),
            "wallet": h.wallet_price,
            "standard": h.standard_price
        }
        for h in history
    ]
    return {"sku": sku, "name": item.name, "history": chart_data}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)