import json
import logging
import asyncio
import os
import redis
import time
from datetime import datetime, timedelta

from celery_app import celery_app
from parser_service import parser_service
from analysis_service import analysis_service
from wb_api_service import wb_api_service
from bot_service import bot_service
from bidder_engine import PIDController
from database import SyncSessionLocal, MonitoredItem, PriceHistory, SearchHistory, User, SeoPosition, BidderConfig, BidderLog
from clickhouse_models import ch_client
from sqlalchemy import select

# Импортируем функцию прогнозирования
from forecasting import forecast_demand

logger = logging.getLogger("CeleryTasks")

# Настройка Redis клиента
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Префиксы ключей Redis
BIDDER_STATE_PREFIX = "bidder:state:"
FORECAST_CACHE_PREFIX = "forecast:"
POS_CACHE_PREFIX = "bidder:pos:"  # Кэш позиций, чтобы не парсить каждую минуту

# --- HELPER FUNCTIONS ---

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
            ph = PriceHistory(item_id=item.id, wallet_price=p.get("wallet_purple", 0), standard_price=p.get("standard_black", 0), base_price=p.get("base_crossed", 0))
            session.add(ph)
            session.commit()
    except Exception as e:
        session.rollback()
    finally:
        session.close()

def save_seo_position_sync(user_id, sku, keyword, position):
    session = SyncSessionLocal()
    try:
        pos_entry = session.query(SeoPosition).filter(SeoPosition.user_id == user_id, SeoPosition.sku == sku, SeoPosition.keyword == keyword).first()
        if pos_entry:
            pos_entry.position = position
            pos_entry.last_check = datetime.utcnow()
        else:
            pos_entry = SeoPosition(user_id=user_id, sku=sku, keyword=keyword, position=position)
            session.add(pos_entry)
        session.commit()
    except Exception as e:
        session.rollback()
    finally:
        session.close()

# --- BIDDER LOGIC (ASYNC) ---

async def _process_bidder_async(campaign_id: int):
    """
    Асинхронный воркер обработки одной кампании.
    Инкапсулирует всю логику: получение данных -> Проверка позиции -> PID -> Решение -> Действие.
    """
    session = SyncSessionLocal()
    try:
        # 1. Получаем конфиг из БД
        config = session.query(BidderConfig).join(User).filter(BidderConfig.campaign_id == campaign_id).first()
        if not config or not config.is_active:
            return 

        user_token = config.user.wb_api_token
        if not user_token:
            logger.error(f"No token for campaign {campaign_id}")
            return

        # 2. Получаем текущее состояние аукциона (WB API)
        camp_info = await wb_api_service.get_campaign_info(user_token, campaign_id)
        
        if not camp_info:
            logger.warning(f"Failed to fetch info for {campaign_id}")
            return

        current_bid = camp_info.get("price", 0) 
        status = camp_info.get("status", 0)
        
        # Пропускаем, если кампания на паузе (статус 9 - активна, 11 - пауза)
        if status not in [9, 11]: 
            return

        # Пытаемся найти SKU товара в кампании (нужен для проверки позиции)
        target_sku = None
        items = camp_info.get("items", [])
        if items and len(items) > 0:
            target_sku = items[0].get("nmId") # Берем первый товар

        # 3. Определение текущей позиции (Real Parsing + Caching)
        current_pos = 100 # Default fallback (далеко)
        
        if config.keyword and target_sku:
            # Проверяем кэш Redis, чтобы не парсить выдачу каждую минуту (экономим ресурсы)
            pos_cache_key = f"{POS_CACHE_PREFIX}{campaign_id}:{config.keyword}"
            cached_pos = redis_client.get(pos_cache_key)
            
            if cached_pos:
                current_pos = int(cached_pos)
            else:
                # Если в кэше нет - парсим реально
                # ВАЖНО: parser_service использует Selenium, это может быть медленно.
                # В production лучше использовать легковесный HTTP клиент.
                try:
                    real_pos = parser_service.get_search_position(config.keyword, target_sku)
                    if real_pos > 0:
                        current_pos = real_pos
                        # Кэшируем позицию на 10 минут
                        redis_client.setex(pos_cache_key, 600, real_pos)
                except Exception as e:
                    logger.error(f"Parser error for bidder {campaign_id}: {e}")
        
        # 4. Проверка Target CPA / CTR Safeguard
        # Получаем статистику (нужен отдельный запрос к /stat/days, здесь упрощено)
        # Если API не возвращает CTR прямо сейчас, используем безопасное значение
        # В реальной реализации здесь должен быть запрос: await wb_api_service.get_campaign_stats(...)
        ctr = 2.0 # Заглушка, так как API статистики тяжелое. В prod нужно раскомментировать запрос.
        
        applied_bid = current_bid
        log_action = "hold"
        money_saved = 0.0
        new_bid = current_bid
        pid_components = {"P": 0, "I": 0, "D": 0}

        # ЛОГИКА ЗАЩИТЫ БЮДЖЕТА
        if ctr < config.min_ctr:
             logger.info(f"Low CTR ({ctr}%) for {campaign_id}. Lowering to min bid.")
             new_bid = config.min_bid
             log_action = "paused_low_ctr"
             
             if not config.safe_mode and current_bid > config.min_bid:
                 await wb_api_service.set_campaign_bid(user_token, campaign_id, new_bid)
                 applied_bid = new_bid
        else:
            # 5. Получаем состояние PID из Redis
            redis_key = f"{BIDDER_STATE_PREFIX}{campaign_id}"
            state_data = redis_client.hgetall(redis_key)
            
            prev_error = float(state_data.get("prev_error", 0.0))
            accumulated_integral = float(state_data.get("integral", 0.0))
            last_measurement = float(state_data.get("last_pos", current_pos))
            last_update_ts = float(state_data.get("last_ts", time.time() - 60))

            # 6. Расчет PID
            pid = PIDController(
                kp=config.kp, ki=config.ki, kd=config.kd,
                min_bid=config.min_bid, max_bid=config.max_bid,
                target_pos=config.target_position
            )
            pid.last_time = last_update_ts

            result = pid.update(
                current_pos=current_pos,
                current_bid=current_bid,
                prev_error=prev_error,
                accumulated_integral=accumulated_integral,
                last_measurement=last_measurement
            )
            
            new_bid = result["new_bid"]
            action = result["action"]
            pid_components = result["components"]

            # 7. Execution
            log_action = action
            
            if config.safe_mode:
                log_action = "safe_mode"
                if new_bid < current_bid:
                    money_saved = current_bid - new_bid
            else:
                if action == "update":
                    success = await wb_api_service.set_campaign_bid(user_token, campaign_id, new_bid)
                    if success:
                        applied_bid = new_bid
                        if new_bid < current_bid:
                            money_saved = current_bid - new_bid
                    else:
                        log_action = "error_api"

            # 8. Сохраняем состояние PID
            new_state = {
                "prev_error": result["prev_error"],
                "integral": result["integral"],
                "last_pos": result["last_measurement"],
                "last_ts": time.time()
            }
            redis_client.hset(redis_key, mapping=new_state)
            redis_client.expire(redis_key, 86400)

        # 9. Логируем в БД
        log_entry = BidderLog(
            config_id=config.id,
            current_pos=current_pos,
            target_pos=config.target_position,
            old_bid=current_bid,
            calculated_bid=new_bid,
            applied_bid=applied_bid,
            money_saved=money_saved,
            action_type=log_action,
            message=f"P:{pid_components.get('P',0):.1f} I:{pid_components.get('I',0):.1f} CTR:{ctr}"
        )
        session.add(log_entry)
        config.last_check = datetime.utcnow()
        session.commit()
        
    except Exception as e:
        logger.error(f"Bidder error {campaign_id}: {e}")
        session.rollback()
    finally:
        session.close()

# --- CELERY TASKS ---

@celery_app.task(name="process_campaign_bid")
def process_campaign_bid(campaign_id: int):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_process_bidder_async(campaign_id))
    loop.close()

@celery_app.task(name="run_bidder_cycle")
def run_bidder_cycle():
    session = SyncSessionLocal()
    try:
        active_configs = session.query(BidderConfig.campaign_id).filter(BidderConfig.is_active == True).all()
        if not active_configs: return "No active campaigns"
        count = 0
        for (camp_id,) in active_configs:
            process_campaign_bid.delay(camp_id)
            count += 1
        return f"Queued {count} campaigns"
    except Exception as e:
        return f"Error: {e}"
    finally:
        session.close()

# --- FORECASTING TASK ---

@celery_app.task(name="train_forecasting_models")
def train_forecasting_models():
    """
    Ежедневная задача переобучения моделей Prophet.
    """
    logger.info("Starting Daily Forecasting Job...")
    session = SyncSessionLocal()
    
    try:
        users = session.query(User).filter(User.wb_api_token.isnot(None)).all()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def process_user(user):
            try:
                # Берем историю продаж (90 дней)
                sales_data = await wb_api_service.get_sales_history(user.wb_api_token, days=90)
                if not sales_data: return
                
                sales_map = {} 
                for order in sales_data:
                    sku = order.get('nmId')
                    date_str = order.get('date', '')[:10]
                    if not sku or not date_str: continue
                    if sku not in sales_map: sales_map[sku] = {}
                    sales_map[sku][date_str] = sales_map[sku].get(date_str, 0) + 1
                
                for sku, daily_map in sales_map.items():
                    history_list = []
                    today = datetime.now().date()
                    days_depth = 90
                    # Формируем список продаж от старых к новым
                    for i in range(days_depth, 0, -1):
                        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                        history_list.append(daily_map.get(d, 0))
                    
                    # Прогноз
                    forecast = forecast_demand(history_list, horizon_days=30)
                    
                    if forecast['status'] == 'success':
                        key = f"{FORECAST_CACHE_PREFIX}{sku}"
                        # Кэшируем на 25 часов
                        redis_client.setex(key, timedelta(hours=25), json.dumps(forecast))
                        
            except Exception as e:
                logger.error(f"Error forecasting for user {user.id}: {e}")

        tasks = [process_user(u) for u in users]
        loop.run_until_complete(asyncio.gather(*tasks))
        loop.close()
        logger.info(f"Forecasting finished for {len(users)} users.")
        
    except Exception as e:
        logger.error(f"Global Forecasting Error: {e}")
    finally:
        session.close()

# --- OTHER TASKS ---

@celery_app.task(bind=True, name="parse_and_save_sku")
def parse_and_save_sku(self, sku: int, user_id: int = None):
    self.update_state(state='PROGRESS', meta={'status': 'Запуск парсера...'})
    raw_result = parser_service.get_product_data(sku)
    if raw_result.get("status") == "error": return {"status": "error", "error": raw_result.get("message")}
    save_price_sync(sku, raw_result)
    final_result = analysis_service.calculate_metrics(raw_result)
    if user_id:
        p = raw_result.get('prices', {})
        brand = raw_result.get('brand', 'WB')
        title = f"{p.get('wallet_purple')}₽ | {brand}"
        save_history_sync(user_id, sku, 'price', title, final_result)
    return final_result

@celery_app.task(bind=True, name="analyze_reviews_task")
def analyze_reviews_task(self, sku: int, limit: int = 50, user_id: int = None):
    self.update_state(state='PROGRESS', meta={'status': 'Сбор отзывов...'})
    product_info = parser_service.get_full_product_info(sku, limit)
    if product_info.get("status") == "error": return {"status": "error", "error": product_info.get("message")}
    self.update_state(state='PROGRESS', meta={'status': 'Нейросеть думает...'})
    reviews = product_info.get('reviews', [])
    if not reviews: return {"status": "error", "error": "Нет отзывов"}
    ai_result = analysis_service.analyze_reviews_with_ai(reviews, f"Товар {sku}")
    final_result = {"status": "success", "sku": sku, "image": product_info.get('image'), "rating": product_info.get('rating'), "reviews_count": product_info.get('reviews_count'), "ai_analysis": ai_result}
    if user_id: save_history_sync(user_id, sku, 'ai', f"AI Отзывы: {product_info.get('rating')}★", final_result)
    return final_result

@celery_app.task(bind=True, name="generate_seo_task")
def generate_seo_task(self, keywords: list, tone: str, sku: int = 0, user_id: int = None, title_len: int = 100, desc_len: int = 1000):
    content = analysis_service.generate_product_content(keywords, tone, title_len, desc_len)
    final_result = {"status": "success", "sku": sku, "keywords": keywords, "tone": tone, "generated_content": content}
    if user_id and sku > 0: save_history_sync(user_id, sku, 'seo', f"SEO: {content.get('title', 'Без заголовка')[:20]}...", final_result)
    return final_result

@celery_app.task(bind=True, name="check_seo_position_task")
def check_seo_position_task(self, sku: int, keyword: str, user_id: int):
    position = parser_service.get_search_position(keyword, sku)
    save_seo_position_sync(user_id, sku, keyword, position)
    return {"status": "success", "sku": sku, "keyword": keyword, "position": position}

@celery_app.task(name="update_all_monitored_items")
def update_all_monitored_items():
    """Периодическое обновление цен для всех товаров в мониторинге"""
    session = SyncSessionLocal()
    try:
        skus = [i.sku for i in session.query(MonitoredItem).all()]
        for sku in skus:
            # Используем .delay чтобы не блокировать воркер
            parse_and_save_sku.delay(sku)
        return f"Queued updates for {len(skus)} items"
    except Exception as e:
        logger.error(f"Update error: {e}")
    finally:
        session.close()

@celery_app.task(name="check_new_orders")
def check_new_orders():
    """
    Проверка новых заказов для всех пользователей.
    Отправляет уведомления в Telegram.
    """
    logger.info("Checking new orders...")
    session = SyncSessionLocal()
    try:
        # Берем только тех, у кого есть токен
        users = session.query(User).filter(User.wb_api_token.isnot(None)).all()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def check_user(user):
            try:
                # Если проверки не было никогда, берем за последний час
                last_check = user.last_order_check or (datetime.utcnow() - timedelta(hours=1))
                
                # Запрашиваем новые заказы
                new_orders = await wb_api_service.get_new_orders_since(user.wb_api_token, last_check)
                
                if new_orders:
                    total_sum = sum(item.get("priceWithDiscount", 0) for item in new_orders)
                    count = len(new_orders)
                    
                    # Формируем сообщение
                    msg = (
                        f"💰 <b>Новые заказы: +{count} шт</b>\n"
                        f"Сумма: {total_sum:,.0f} ₽\n\n"
                    )
                    # Добавляем детали по первым 3 товарам
                    for order in new_orders[:3]:
                        msg += f"▫️ {order.get('category', 'Товар')} - {int(order.get('priceWithDiscount', 0))} ₽\n"
                    
                    if count > 3:
                        msg += f"... и еще {count - 3}"
                        
                    # Отправляем в телеграм
                    await bot_service.send_message(user.telegram_id, msg)
                
                # Обновляем время проверки
                # Важно: используем session.merge или update, т.к. user объект привязан к сессии
                user.last_order_check = datetime.utcnow()
                session.add(user)
                session.commit()
                
            except Exception as e:
                logger.error(f"Order check error for user {user.id}: {e}")
                session.rollback()

        tasks = [check_user(u) for u in users]
        if tasks:
            loop.run_until_complete(asyncio.gather(*tasks))
        loop.close()
        
    except Exception as e:
        logger.error(f"Global order check error: {e}")
    finally:
        session.close()

@celery_app.task(bind=True, name="sync_financial_reports")
def sync_financial_reports(self):
    self.update_state(state='PROGRESS', meta={'status': 'Starting Sync...'})
    ch_client.init_schema()
    session = SyncSessionLocal()
    try:
        users = session.query(User).filter(User.wb_api_token.isnot(None)).all()
        async def fetch_and_save(user):
            date_from = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
            date_to = datetime.now().strftime("%Y-%m-%d")
            url = "https://statistics-api.wildberries.ru/api/v5/supplier/reportDetailByPeriod"
            params = {"dateFrom": date_from, "dateTo": date_to}
            headers = {"Authorization": user.wb_api_token}
            async with aiohttp.ClientSession() as http_session:
                try:
                    async with http_session.get(url, headers=headers, params=params, timeout=120) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if not data: return
                            rows_to_insert = []
                            columns = ['rrd_id', 'supplier_id', 'realizationreport_id', 'sale_dt', 'create_dt', 'date_from', 'date_to', 'nm_id', 'brand_name', 'sa_name', 'subject_name', 'ts_name', 'barcode', 'doc_type_name', 'supplier_oper_name', 'retail_price', 'retail_amount', 'commission_percent', 'commission_amount', 'retail_price_withdisc_rub', 'delivery_rub', 'delivery_amount', 'return_amount', 'penalty', 'additional_payment', 'office_name', 'site_country', 'record_status']
                            for item in data:
                                try:
                                    s_dt = datetime.strptime(item.get('sale_dt', ''), "%Y-%m-%dT%H:%M:%SZ") if item.get('sale_dt') else datetime.now()
                                    c_dt = datetime.strptime(item.get('create_dt', ''), "%Y-%m-%dT%H:%M:%SZ") if item.get('create_dt') else datetime.now()
                                    d_from = datetime.strptime(item.get('date_from', ''), "%Y-%m-%dT%H:%M:%SZ") if item.get('date_from') else datetime.now()
                                    d_to = datetime.strptime(item.get('date_to', ''), "%Y-%m-%dT%H:%M:%SZ") if item.get('date_to') else datetime.now()
                                    row = [int(item.get('rrd_id', 0)), user.id, int(item.get('realizationreport_id', 0)), s_dt, c_dt, d_from, d_to, int(item.get('nm_id', 0)), str(item.get('brand_name', '')), str(item.get('sa_name', '')), str(item.get('subject_name', '')), str(item.get('ts_name', '')), str(item.get('barcode', '')), str(item.get('doc_type_name', '')), str(item.get('supplier_oper_name', '')), float(item.get('retail_price', 0) or 0), float(item.get('retail_amount', 0) or 0), float(item.get('commission_percent', 0) or 0), float(item.get('commission_amount', 0) or 0), float(item.get('retail_price_withdisc_rub', 0) or 0), float(item.get('delivery_rub', 0) or 0), int(item.get('delivery_amount', 0)), int(item.get('return_amount', 0)), float(item.get('penalty', 0) or 0), float(item.get('additional_payment', 0) or 0), str(item.get('office_name', '')), str(item.get('site_country', '')), 'actual']
                                    rows_to_insert.append(row)
                                except: continue
                            if rows_to_insert: ch_client.insert_reports(rows_to_insert, columns)
                        elif resp.status == 429: await asyncio.sleep(5)
                except Exception as e: logger.error(f"Fetch error user {user.id}: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        tasks = [fetch_and_save(u) for u in users]
        loop.run_until_complete(asyncio.gather(*tasks))
        loop.close()
    finally:
        session.close()
    return {"status": "finished"}