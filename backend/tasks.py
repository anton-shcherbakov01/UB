import asyncio
import logging
from celery_app import celery_app
from parser_service import parser_service
from analysis_service import analysis_service
from database import AsyncSessionLocal, MonitoredItem, PriceHistory
from sqlalchemy import select

logger = logging.getLogger("CeleryWorker")

async def save_price_to_db_async(sku: int, data: dict):
    if data.get("status") == "error": return
    async with AsyncSessionLocal() as session:
        stmt = select(MonitoredItem).where(MonitoredItem.sku == sku)
        result = await session.execute(stmt)
        item = result.scalars().first()
        
        if item:
            item.name = data.get("name")
            item.brand = data.get("brand")
            prices = data.get("prices", {})
            history = PriceHistory(
                item_id=item.id,
                wallet_price=prices.get("wallet_purple", 0),
                standard_price=prices.get("standard_black", 0),
                base_price=prices.get("base_crossed", 0)
            )
            session.add(history)
            await session.commit()
            logger.info(f"DB: Saved {sku}")

@celery_app.task(bind=True, name="parse_and_save_sku")
def parse_and_save_sku(self, sku: int):
    self.update_state(state='PROGRESS', meta={'status': 'Запуск браузера...'})
    raw_result = parser_service.get_product_data(sku)
    
    if raw_result.get("status") == "error": 
        return {"status": "error", "error": raw_result.get("message")}
    
    self.update_state(state='PROGRESS', meta={'status': 'Сохранение...'})
    try:
        # Для БД нужен асинхронный контекст
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(save_price_to_db_async(sku, raw_result))
        loop.close()
    except Exception as e:
        logger.error(f"DB Error: {e}")
    
    return analysis_service.calculate_metrics(raw_result)

@celery_app.task(bind=True, name="analyze_reviews_task")
def analyze_reviews_task(self, sku: int, limit: int = 50):
    self.update_state(state='PROGRESS', meta={'status': 'Сбор отзывов (API)...'})
    
    product_data = parser_service.get_full_product_info(sku, limit)
    
    if product_data.get("status") == "error":
        return {"status": "error", "error": product_data.get("message")}
    
    self.update_state(state='PROGRESS', meta={'status': 'Нейросеть думает...'})
    
    ai_result = {}
    reviews = product_data.get('reviews', [])
    
    if reviews:
        try:
            # ВАЖНО: analysis_service теперь синхронный (requests), 
            # поэтому вызываем его напрямую, БЕЗ asyncio.run()
            ai_result = analysis_service.analyze_reviews_with_ai(reviews, f"Товар {sku}")
        except Exception as e:
            logger.error(f"AI Task Error: {e}")
            ai_result = {"flaws": ["Ошибка анализа"], "strategy": [str(e)]}
    else:
        ai_result = {"flaws": ["Отзывы не найдены"], "strategy": ["Попробуйте другой товар"]}

    return {
        "status": "success",
        "sku": sku,
        "image": product_data.get('image'),
        "rating": product_data.get('rating'),
        "reviews_count": product_data.get('reviews_count'),
        "ai_analysis": ai_result
    }

@celery_app.task(name="update_all_monitored_items")
def update_all_monitored_items():
    # Для периодических задач тоже используем синхронную сессию
    session = SyncSessionLocal()
    try:
        skus = [item.sku for item in session.query(MonitoredItem).all()]
        logger.info(f"Beat: Обновление {len(skus)} товаров...")
        for sku in skus:
            parse_and_save_sku.delay(sku)
    finally:
        session.close()