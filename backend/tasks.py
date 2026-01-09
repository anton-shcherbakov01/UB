import asyncio
import logging
from celery_app import celery_app
from parser_service import parser_service
from analysis_service import analysis_service
from database import SyncSessionLocal, MonitoredItem, PriceHistory, SearchHistory, User
from sqlalchemy import select

logger = logging.getLogger("CeleryWorker")

def save_history_sync(user_id: int, sku: int, type: str, title: str):
    """Сохранение истории запросов"""
    if not user_id: return
    session = SyncSessionLocal()
    try:
        h = SearchHistory(user_id=user_id, sku=sku, type=type, title=title)
        session.add(h)
        session.commit()
    except Exception as e:
        logger.error(f"History Save Error: {e}")
    finally:
        session.close()

def save_price_sync(sku: int, data: dict):
    """Сохранение цены мониторинга"""
    session = SyncSessionLocal()
    try:
        item = session.query(MonitoredItem).filter(MonitoredItem.sku == sku).first()
        if item:
            item.name = data.get("name")
            item.brand = data.get("brand")
            p = data.get("prices", {})
            ph = PriceHistory(
                item_id=item.id,
                wallet_price=p.get("wallet_purple", 0),
                standard_price=p.get("standard_black", 0),
                base_price=p.get("base_crossed", 0)
            )
            session.add(ph)
            session.commit()
    except Exception as e:
        logger.error(f"DB Error: {e}")
    finally:
        session.close()

@celery_app.task(bind=True, name="parse_and_save_sku")
def parse_and_save_sku(self, sku: int, user_id: int = None):
    self.update_state(state='PROGRESS', meta={'status': 'Парсинг цен...'})
    raw_result = parser_service.get_product_data(sku)
    
    if raw_result.get("status") == "error": 
        return {"status": "error", "error": raw_result.get("message")}
    
    # Сохраняем в мониторинг (если товар там есть)
    save_price_sync(sku, raw_result)
    
    # Сохраняем в историю запросов (если вызвано пользователем)
    if user_id:
        title = f"{raw_result.get('prices', {}).get('wallet_purple')}₽ - {raw_result.get('name')}"
        save_history_sync(user_id, sku, 'price', title)

    return analysis_service.calculate_metrics(raw_result)

@celery_app.task(bind=True, name="analyze_reviews_task")
def analyze_reviews_task(self, sku: int, limit: int = 50, user_id: int = None):
    self.update_state(state='PROGRESS', meta={'status': 'Сбор отзывов...'})
    product_data = parser_service.get_full_product_info(sku, limit)
    
    if product_data.get("status") == "error":
        return {"status": "error", "error": product_data.get("message")}
    
    self.update_state(state='PROGRESS', meta={'status': 'Нейросеть думает...'})
    
    ai_result = {}
    try:
        # Синхронный вызов AI (так как analysis_service переписан на requests)
        reviews = product_data.get('reviews', [])
        if reviews:
            ai_result = analysis_service.analyze_reviews_with_ai(reviews, f"Товар {sku}")
            
            # Сохраняем в историю
            if user_id:
                title = f"AI Анализ: {product_data.get('rating')}★"
                save_history_sync(user_id, sku, 'ai', title)
        else:
            ai_result = {"flaws": ["Нет отзывов"], "strategy": ["-"]}
    except Exception as e:
        ai_result = {"flaws": ["Ошибка"], "strategy": [str(e)]}

    return {
        "status": "success",
        "sku": sku,
        "ai_analysis": ai_result,
        "image": product_data.get('image'),
        "rating": product_data.get('rating'),
        "reviews_count": product_data.get('reviews_count')
    }

@celery_app.task(name="update_all_monitored_items")
def update_all_monitored_items():
    logger.info("Beat: Запуск обновления цен...")
    session = SyncSessionLocal()
    try:
        items = session.query(MonitoredItem).all()
        for item in items:
            parse_and_save_sku.delay(item.sku)
        logger.info(f"Beat: Запущено {len(items)} задач.")
    finally:
        session.close()