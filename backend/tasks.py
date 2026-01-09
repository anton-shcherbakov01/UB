import asyncio
import logging
from celery_app import celery_app
from parser_service import parser_service
from analysis_service import analysis_service
# Импортируем СИНХРОННУЮ сессию
from database import SyncSessionLocal, MonitoredItem, PriceHistory
from sqlalchemy import select

logger = logging.getLogger("CeleryWorker")

def save_price_to_db_sync(sku: int, data: dict):
    """
    Синхронная функция сохранения в БД.
    Использует psycopg2, работает идеально внутри Celery.
    """
    if data.get("status") == "error": return

    session = SyncSessionLocal()
    try:
        # Ищем товар
        item = session.query(MonitoredItem).filter(MonitoredItem.sku == sku).first()
        
        if item:
            # Обновляем инфо
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
            session.commit()
            logger.info(f"DB: Saved history for {sku}")
        else:
             # Если товара нет в базе (добавлен через сканер, но не в мониторинг) - пропускаем
             # Или можно создать, если логика требует
             logger.warning(f"DB: Item {sku} not found in monitoring list")
    except Exception as e:
        logger.error(f"DB Sync Error: {e}")
        session.rollback()
    finally:
        session.close()

@celery_app.task(bind=True, name="parse_and_save_sku")
def parse_and_save_sku(self, sku: int):
    self.update_state(state='PROGRESS', meta={'status': 'Запуск браузера...'})
    
    # 1. Парсинг (Синхронно)
    raw_result = parser_service.get_product_data(sku)
    
    if raw_result.get("status") == "error": 
        return {"status": "error", "error": raw_result.get("message")}
    
    self.update_state(state='PROGRESS', meta={'status': 'Сохранение в базу...'})
    
    # 2. Сохранение (Синхронно - больше никаких loop error!)
    save_price_to_db_sync(sku, raw_result)
    
    return analysis_service.calculate_metrics(raw_result)

@celery_app.task(bind=True, name="analyze_reviews_task")
def analyze_reviews_task(self, sku: int, limit: int = 50):
    self.update_state(state='PROGRESS', meta={'status': 'Сбор отзывов (API)...'})
    
    # 1. Парсинг отзывов (Синхронно через parser_service)
    product_data = parser_service.get_full_product_info(sku, limit)
    
    if product_data.get("status") == "error":
        return {"status": "error", "error": product_data.get("message")}
    
    self.update_state(state='PROGRESS', meta={'status': 'Нейросеть думает...'})
    
    # 2. ИИ Анализ (Асинхронно, запускаем loop локально)
    ai_result = {}
    try:
        reviews = product_data.get('reviews', [])
        if reviews:
            # Создаем новый loop только для этого вызова
            ai_result = asyncio.run(analysis_service.analyze_reviews_with_ai(reviews, f"Товар {sku}"))
        else:
            ai_result = {"flaws": ["Отзывы не найдены"], "strategy": ["Попробуйте другой товар"]}
    except Exception as e:
        logger.error(f"AI Task Error: {e}")
        ai_result = {"flaws": ["Ошибка анализа"], "strategy": [str(e)]}

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