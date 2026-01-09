import asyncio
import logging
import json
from celery_app import celery_app
from parser_service import parser_service
from analysis_service import analysis_service
from database import SyncSessionLocal, MonitoredItem, PriceHistory, SearchHistory, User
from sqlalchemy import select

logger = logging.getLogger("CeleryWorker")

def save_history_sync(user_id, sku, type, title, result_data):
    """Сохраняем историю с полным JSON результатом"""
    if not user_id: return
    session = SyncSessionLocal()
    try:
        # Сериализуем результат в строку
        json_str = json.dumps(result_data, ensure_ascii=False)
        h = SearchHistory(
            user_id=user_id, 
            sku=sku, 
            request_type=type, 
            title=title,
            result_json=json_str
        )
        session.add(h)
        session.commit()
    except Exception as e:
        logger.error(f"History error: {e}")
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
        logger.error(f"DB Error: {e}")
    finally:
        session.close()

@celery_app.task(bind=True, name="parse_and_save_sku")
def parse_and_save_sku(self, sku: int, user_id: int = None):
    self.update_state(state='PROGRESS', meta={'status': 'Запуск браузера...'})
    
    # 1. Парсинг цен (Selenium)
    raw_result = parser_service.get_product_data(sku)
    
    if raw_result.get("status") == "error": 
        return {"status": "error", "error": raw_result.get("message")}
    
    # Сохраняем в мониторинг
    save_price_sync(sku, raw_result)
    
    # Считаем метрики
    final_result = analysis_service.calculate_metrics(raw_result)

    # Сохраняем в историю (если это ручной запрос)
    if user_id:
        p = raw_result.get('prices', {})
        title = f"{p.get('wallet_purple')}₽ | {raw_result.get('brand')}"
        save_history_sync(user_id, sku, 'price', title, final_result)

    return final_result

@celery_app.task(bind=True, name="analyze_reviews_task")
def analyze_reviews_task(self, sku: int, limit: int = 50, user_id: int = None):
    self.update_state(state='PROGRESS', meta={'status': 'Сбор отзывов (API)...'})
    
    product_data = parser_service.get_full_product_info(sku, limit)
    if product_data.get("status") == "error":
        return {"status": "error", "error": product_data.get("message")}
    
    self.update_state(state='PROGRESS', meta={'status': 'Нейросеть думает...'})
    
    ai_result = {}
    reviews = product_data.get('reviews', [])
    if reviews:
        try:
            # Синхронный вызов ИИ
            ai_result = analysis_service.analyze_reviews_with_ai(reviews, f"Товар {sku}")
        except Exception as e:
            ai_result = {"flaws": ["Ошибка"], "strategy": [str(e)]}
    else:
        ai_result = {"flaws": ["Отзывы не найдены"], "strategy": ["-"]}

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
    logger.info("Beat: Часовое обновление цен запущено...")
    session = SyncSessionLocal()
    try:
        items = session.query(MonitoredItem).all()
        logger.info(f"Beat: Найдено {len(items)} товаров для обновления.")
        for item in items:
            parse_and_save_sku.delay(item.sku)
    finally:
        session.close()