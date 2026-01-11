import json
import logging
import asyncio
from datetime import datetime
from celery_app import celery_app
from parser_service import parser_service
from analysis_service import analysis_service
from wb_api_service import wb_api_service
from bot_service import bot_service
from database import SyncSessionLocal, MonitoredItem, PriceHistory, SearchHistory, User, SeoPosition, BidderConfig
from sqlalchemy import select

logger = logging.getLogger("CeleryTasks")


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ (SYNC) ---

def save_history_sync(user_id, sku, type, title, result_data):
    if not user_id: return
    session = SyncSessionLocal()
    try:
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
        # Используем синхронный query
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

def save_seo_position_sync(user_id, sku, keyword, position):
    session = SyncSessionLocal()
    try:
        pos_entry = session.query(SeoPosition).filter(
            SeoPosition.user_id == user_id, 
            SeoPosition.sku == sku, 
            SeoPosition.keyword == keyword
        ).first()
        
        if pos_entry:
            pos_entry.position = position
            pos_entry.last_check = datetime.utcnow()
        else:
            pos_entry = SeoPosition(user_id=user_id, sku=sku, keyword=keyword, position=position)
            session.add(pos_entry)
        session.commit()
    except Exception as e:
        logger.error(f"SEO DB Error: {e}")
        session.rollback()
    finally:
        session.close()

# --- ЗАДАЧИ CELERY (SYNC) ---

@celery_app.task(bind=True, name="parse_and_save_sku")
def parse_and_save_sku(self, sku: int, user_id: int = None):
    self.update_state(state='PROGRESS', meta={'status': 'Запуск парсера...'})
    
    # 1. Парсинг (метод внутри синхронный или сам создает луп)
    raw_result = parser_service.get_product_data(sku)
    
    if raw_result.get("status") == "error": 
        err_msg = raw_result.get("message", "Unknown error")
        return {"status": "error", "error": err_msg}
    
    self.update_state(state='PROGRESS', meta={'status': 'Сохранение...'})
    
    # 2. Сохранение (Синхронно)
    save_price_sync(sku, raw_result)
    
    # 3. Аналитика
    final_result = analysis_service.calculate_metrics(raw_result)

    # 4. История
    if user_id:
        p = raw_result.get('prices', {})
        brand = raw_result.get('brand', 'WB')
        title = f"{p.get('wallet_purple')}₽ | {brand}"
        save_history_sync(user_id, sku, 'price', title, final_result)

    return final_result

@celery_app.task(bind=True, name="analyze_reviews_task")
def analyze_reviews_task(self, sku: int, limit: int = 50, user_id: int = None):
    self.update_state(state='PROGRESS', meta={'status': 'Сбор отзывов...'})
    
    # 1. Парсинг API (Requests - синхронно)
    product_info = parser_service.get_full_product_info(sku, limit)
    
    if product_info.get("status") == "error":
        return {"status": "error", "error": product_info.get("message")}
    
    self.update_state(state='PROGRESS', meta={'status': 'Нейросеть думает...'})
    
    # 2. ИИ Анализ (Requests - синхронно)
    reviews = product_info.get('reviews', [])
    if not reviews:
        return {"status": "error", "error": "Нет отзывов"}

    ai_result = analysis_service.analyze_reviews_with_ai(reviews, f"Товар {sku}")

    final_result = {
        "status": "success",
        "sku": sku,
        "image": product_info.get('image'),
        "rating": product_info.get('rating'),
        "reviews_count": product_info.get('reviews_count'),
        "ai_analysis": ai_result
    }

    if user_id:
        title = f"AI Отзывы: {product_info.get('rating')}★"
        save_history_sync(user_id, sku, 'ai', title, final_result)

    return final_result

@celery_app.task(bind=True, name="generate_seo_task")
def generate_seo_task(self, keywords: list, tone: str, sku: int = 0, user_id: int = None, title_len: int = 100, desc_len: int = 1000):
    """Генерация SEO. Аргументы длины прокинуты."""
    self.update_state(state='PROGRESS', meta={'status': 'Генерация контента...'})
    
    # Генерация (Requests - синхронно)
    content = analysis_service.generate_product_content(keywords, tone, title_len, desc_len)
    
    final_result = {
        "status": "success",
        "sku": sku,
        "keywords": keywords,
        "tone": tone,
        "generated_content": content
    }
    
    if user_id and sku > 0:
        title = f"SEO: {content.get('title', 'Без заголовка')[:20]}..."
        save_history_sync(user_id, sku, 'seo', title, final_result)
        
    return final_result

@celery_app.task(bind=True, name="check_seo_position_task")
def check_seo_position_task(self, sku: int, keyword: str, user_id: int):
    """Проверка позиций (SERP)"""
    self.update_state(state='PROGRESS', meta={'status': 'Парсинг поиска...'})
    
    # Парсинг (Selenium - синхронно)
    position = parser_service.get_search_position(keyword, sku)
    
    # Сохранение (Синхронно)
    save_seo_position_sync(user_id, sku, keyword, position)
    
    return {"status": "success", "sku": sku, "keyword": keyword, "position": position}

@celery_app.task(name="update_all_monitored_items")
def update_all_monitored_items():
    session = SyncSessionLocal()
    try:
        skus = [i.sku for i in session.query(MonitoredItem).all()]
        logger.info(f"Beat: Starting update for {len(skus)} items")
        for sku in skus:
            parse_and_save_sku.delay(sku)
    finally:
        session.close()

# --- NOTIFICATIONS ("ДЗЫНЬ!") ---

def _process_orders_sync():
    """
    Синхронная обертка для проверки заказов.
    Используем asyncio.run для вызова асинхронных методов WB API.
    """
    async def run_check():
        # Важно: Здесь можно использовать AsyncSession или SyncSession, но так как
        # мы внутри asyncio.run, лучше создать сессию внутри.
        # Для простоты используем wb_api_service напрямую, а базу через SyncSession
        pass # Реализация ниже

    session = SyncSessionLocal()
    try:
        users = session.query(User).filter(User.wb_api_token.isnot(None)).all()
        
        async def check_user(user):
            try:
                new_orders = await wb_api_service.get_new_orders_since(user.wb_api_token, user.last_order_check)
                if new_orders:
                    total_sum = sum(x.get('priceWithDiscount', 0) for x in new_orders)
                    msg = f"🔔 <b>Дзынь! Новые заказы: +{len(new_orders)}</b>\n"
                    msg += f"💰 Сумма: {total_sum:,.0f} ₽\n\n"
                    
                    for o in new_orders[:3]: 
                        price = o.get('priceWithDiscount', 0)
                        category = o.get('category', 'Товар')
                        msg += f"📦 {category}: {price:,.0f} ₽\n"
                    
                    if len(new_orders) > 3:
                        msg += f"...и еще {len(new_orders)-3} шт."
                    
                    await bot_service.send_message(user.telegram_id, msg)
                    return True # Orders found
            except Exception as e:
                logger.error(f"User {user.id} error: {e}")
            return False

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        for user in users:
            found = loop.run_until_complete(check_user(user))
            if found:
                user.last_order_check = datetime.now()
                session.commit()
                
        loop.close()
        
    finally:
        session.close()

def _process_bidder_sync():
    """
    Основной цикл биддера.
    1. Берет активные конфиги.
    2. Проверяет позицию.
    3. Считает PID.
    4. Обновляет ставку.
    """
    session = SyncSessionLocal()
    try:
        # Получаем активные задачи
        configs = session.query(BidderConfig).join(User).filter(BidderConfig.is_active == True, User.wb_api_token.isnot(None)).all()
        
        async def process_one(config):
            try:
                user = config.user
                token = user.wb_api_token
                
                # 1. Получаем текущую инфу о кампании (реальная ставка и статус)
                info = await wb_api_service.get_campaign_info(token, config.campaign_id)
                if not info: 
                    config.last_log = "Ошибка доступа к API"
                    return

                # Извлекаем SKU из кампании (обычно это первый товар) для проверки позиции
                # В ответе /advert детали могут быть вложены, берем упрощенно
                # Для MVP предполагаем, что пользователь указал ключевое слово в config.keyword
                if not config.keyword:
                    config.last_log = "Нет ключевого слова"
                    return

                # Извлекаем SKU (предполагаем, что оно есть в конфиге или кампании, 
                # но для простоты возьмем из мониторинга юзера, если есть)
                # Для полноценной версии нужно хранить SKU кампании в БД.
                # Пока пропустим шаг парсинга позиции, если нет SKU, и используем заглушку
                # Но план требует РЕАЛЬНЫХ данных.
                
                # Попробуем найти товар пользователя, соответствующий кампании (сложно без маппинга)
                # Допустим, мы парсим позицию по ключевому слову для ПЕРВОГО товара юзера (упрощение)
                # В проде нужно точное соответствие.
                target_sku = session.query(MonitoredItem).filter(MonitoredItem.user_id == user.id).first()
                current_pos = 100
                if target_sku:
                    current_pos = parser_service.get_search_position(config.keyword, target_sku.sku)
                    if current_pos == 0: current_pos = 100 # Не найдено
                
                # Текущая ставка в кампании
                # Структура ответа API WB меняется, ищем 'params' -> 'price' или 'cpm'
                current_bid = 0
                if 'params' in info:
                    current_bid = info['params'][0].get('price', 0)
                
                if current_bid == 0:
                    current_bid = config.min_bid # Fallback

                # 2. PID Расчет
                pid = analysis_service.get_pid_bidder(config)
                new_bid, acc_err, err = pid.calculate_new_bid(
                    current_rank=current_pos,
                    target_rank=config.target_position,
                    current_bid=current_bid,
                    accumulated_error=config.accumulated_error,
                    last_error=config.last_error
                )
                
                # 3. Применение (или Safe Mode)
                log_msg = f"Pos: {current_pos} -> {config.target_position} | Bid: {current_bid} -> {new_bid} (Err: {err})"
                
                if config.safe_mode:
                    log_msg += " [SAFE MODE]"
                else:
                    if new_bid != current_bid:
                        success = await wb_api_service.set_campaign_bid(token, config.campaign_id, new_bid)
                        if success:
                            log_msg += " [UPDATED]"
                        else:
                            log_msg += " [API FAIL]"
                    else:
                        log_msg += " [NO CHANGE]"

                # 4. Сохранение состояния
                config.accumulated_error = acc_err
                config.last_error = err
                config.last_log = log_msg
                config.last_check = datetime.utcnow()
                session.commit()
                
            except Exception as e:
                logger.error(f"Bidder error {config.campaign_id}: {e}")
                session.rollback()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        for conf in configs:
            loop.run_until_complete(process_one(conf))
        loop.close()

    except Exception as e:
        logger.error(f"Bidder cycle error: {e}")
    finally:
        session.close()

@celery_app.task(name="run_bidder_cycle")
def run_bidder_cycle():
    _process_bidder_sync()


def _process_orders_sync():
    session = SyncSessionLocal()
    try:
        users = session.query(User).filter(User.wb_api_token.isnot(None)).all()
        async def check_user(user):
            try:
                new_orders = await wb_api_service.get_new_orders_since(user.wb_api_token, user.last_order_check)
                if new_orders:
                    total_sum = sum(x.get('priceWithDiscount', 0) for x in new_orders)
                    msg = f"🔔 <b>Дзынь! Новые заказы: +{len(new_orders)}</b>\n💰 Сумма: {total_sum:,.0f} ₽"
                    await bot_service.send_message(user.telegram_id, msg)
                    return True
            except Exception as e: logger.error(f"User {user.id} error: {e}")
            return False
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        for user in users:
            found = loop.run_until_complete(check_user(user))
            if found:
                user.last_order_check = datetime.now()
                session.commit()
        loop.close()
    finally: session.close()

@celery_app.task(name="check_new_orders")
def check_new_orders():
    _process_orders_sync()