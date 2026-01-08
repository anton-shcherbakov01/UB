import asyncio
from celery_app import celery_app
from parser_service import parser_service
from database import AsyncSessionLocal, MonitoredItem, PriceHistory
from sqlalchemy import select
import logging

logger = logging.getLogger("CeleryWorker")

async def save_price_to_db(sku: int, data: dict):
    """Сохраняет результат парсинга в PostgreSQL"""
    if data.get("status") == "error":
        return

    async with AsyncSessionLocal() as session:
        # Ищем товар, если нет - создаем
        stmt = select(MonitoredItem).where(MonitoredItem.sku == sku)
        result = await session.execute(stmt)
        item = result.scalars().first()

        if not item:
            item = MonitoredItem(
                sku=sku,
                name=data.get("name"),
                brand=data.get("brand")
            )
            session.add(item)
            await session.commit()
            await session.refresh(item)
        
        # Добавляем запись в историю
        prices = data.get("prices", {})
        history = PriceHistory(
            item_id=item.id,
            wallet_price=prices.get("wallet_purple", 0),
            standard_price=prices.get("standard_black", 0),
            base_price=prices.get("base_crossed", 0)
        )
        session.add(history)
        await session.commit()
        logger.info(f"DB: Сохранена история для {sku}")

@celery_app.task(bind=True, name="parse_and_save_sku")
def parse_and_save_sku(self, sku: int):
    """Задача: Спарсить товар и сохранить в БД"""
    logger.info(f"Task: Анализ {sku} для мониторинга")
    raw_result = parser_service.get_product_data(sku)
    
    # Запускаем асинхронную функцию сохранения внутри синхронной Celery-задачи
    loop = asyncio.get_event_loop()
    loop.run_until_complete(save_price_to_db(sku, raw_result))
    
    return raw_result

@celery_app.task(name="update_all_monitored_items")
def update_all_monitored_items():
    """Фоновая задача: Обновить цены всех товаров в базе"""
    async def get_all_skus():
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MonitoredItem.sku))
            return result.scalars().all()

    loop = asyncio.get_event_loop()
    skus = loop.run_until_complete(get_all_skus())
    
    logger.info(f"Beat: Запуск обновления для {len(skus)} товаров")
    for sku in skus:
        parse_and_save_sku.delay(sku)