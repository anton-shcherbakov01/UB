import logging
import json
import asyncio
from celery_app import celery_app
from parser_service import parser_service
from analysis_service import analysis_service
from database import SyncSessionLocal, MonitoredItem, PriceHistory, SearchHistory

logger = logging.getLogger("CeleryWorker")

# Вспомогательные функции сохранения (Синхронные для Celery)
def save_history_sync(user_id, sku, type, title, result_data):
    if not user_id: return
    session = SyncSessionLocal()
    try:
        # Сериализуем данные, если это dict
        if isinstance(result_data, dict):
            json_str = json.dumps(result_data, ensure_ascii=False)
        else:
            json_str = str(result_data)
            
        h = SearchHistory(user_id=user_id, sku=sku, request_type=type, title=title, result_json=json_str)
        session.add(h)
        session.commit()
    except Exception as e:
        logger.error(f"History DB error: {e}")
        session.rollback()
    finally:
        session.close()

def save_price_sync(sku, data):
    if data.get("status") == "error": return
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
            logger.info(f"DB: Updated price for {sku}")
    except Exception as e:
        logger.error(f"Price DB Error: {e}")
        session.rollback()
    finally:
        session.close()

# --- ЗАДАЧИ ---

@celery_app.task(bind=True, name="parse_and_save_sku")
def parse_and_save_sku(self, sku: int, user_id: int = None):
    self.update_state(state='PROGRESS', meta={'status': 'Запуск парсера...'})
    
    # 1. Парсинг
    raw_result = parser_service.get_product_data(sku)
    
    if raw_result.get("status") == "error": 
        err_msg = raw_result.get("message", "Unknown error")
        return {"status": "error", "error": err_msg}
    
    self.update_state(state='PROGRESS', meta={'status': 'Сохранение...'})
    
    # 2. Сохранение
    save_price_sync(sku, raw_result)
    
    # 3. Аналитика цен
    final_result = analysis_service.calculate_metrics(raw_result)

    # 4. История
    if user_id:
        p = raw_result.get('prices', {})
        title = f"{p.get('wallet_purple')}₽ | {raw_result.get('brand')}"
        save_history_sync(user_id, sku, 'price', title, final_result)

    return final_result

@celery_app.task(bind=True, name="analyze_reviews_task")
def analyze_reviews_task(self, sku: int, limit: int = 50, user_id: int = None):
    self.update_state(state='PROGRESS', meta={'status': 'Сбор отзывов...'})
    
    # 1. Парсинг API
    product_data = parser_service.get_full_product_info(sku, limit)
    
    if product_data.get("status") == "error":
        return {"status": "error", "error": product_data.get("message")}
    
    self.update_state(state='PROGRESS', meta={'status': 'Нейросеть думает...'})
    
    # 2. ИИ Анализ
    reviews = product_data.get('reviews', [])
    ai_result = analysis_service.analyze_reviews_with_ai(reviews, f"Товар {sku}")

    final_result = {
        "status": "success",
        "sku": sku,
        "image": product_data.get('image'),
        "rating": product_data.get('rating'),
        "reviews_count": product_data.get('reviews_count'),
        "ai_analysis": ai_result
    }

    if user_id:
        title = f"AI Отзывы: {product_data.get('rating')}★"
        save_history_sync(user_id, sku, 'ai', title, final_result)

    return final_result

@celery_app.task(name="update_all_monitored_items")
def update_all_monitored_items():
    session = SyncSessionLocal()
    try:
        skus = [i.sku for i in session.query(MonitoredItem).all()]
        logger.info(f"Beat: Starting update for {len(skus)} items")
        for sku in skus:
            # Запускаем задачи в очередь
            parse_and_save_sku.delay(sku)
    finally:
        session.close()