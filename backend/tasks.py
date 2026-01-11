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
from bidder_engine import PIDController
from database import SyncSessionLocal, MonitoredItem, PriceHistory, SearchHistory, User, SeoPosition, BidderConfig, BidderLog
from clickhouse_models import ch_client
from sqlalchemy import select

logger = logging.getLogger("CeleryTasks")

# Настройка Redis клиента для хранения состояния PID (Hot Data)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

# Префикс ключей для состояния биддера
BIDDER_STATE_PREFIX = "bidder:state:"

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
    Инкапсулирует всю логику: получение данных -> PID -> Решение -> Действие.
    """
    session = SyncSessionLocal()
    try:
        # 1. Получаем конфиг из БД (Postgres)
        config = session.query(BidderConfig).join(User).filter(BidderConfig.campaign_id == campaign_id).first()
        if not config or not config.is_active:
            return # Кампания выключена или удалена

        user_token = config.user.wb_api_token
        if not user_token:
            logger.error(f"No token for campaign {campaign_id}")
            return

        # 2. Получаем текущее состояние аукциона и метрики (WB API)
        # get_campaign_info возвращает текущую ставку, статус и т.д.
        # Для простоты, предположим, что она возвращает и CTR (реально нужно 2 запроса: info + stats)
        camp_info = await wb_api_service.get_campaign_info(user_token, campaign_id)
        
        if not camp_info:
            logger.warning(f"Failed to fetch info for {campaign_id}")
            return

        current_bid = camp_info.get("price", 0) # CPM
        status = camp_info.get("status", 0)
        
        # Пропускаем, если кампания на паузе не нами (статус 9 - активна, 11 - пауза)
        if status not in [9, 11]: 
            return

        # 3. Эмуляция получения позиции (в реале нужен парсинг выдачи по config.keyword)
        # Для примера используем парсер, но это тяжело для частого запуска.
        # В продакшене лучше использовать легкое API чекера позиций.
        current_pos = 10 # Default fallback
        if config.keyword:
             # Внимание: parser_service использует Selenium, это может быть медленно.
             # В high-load системах здесь должен быть запрос к легкому микросервису парсинга.
             # Для задачи используем заглушку, чтобы не блокировать воркер
             # current_pos = parser_service.get_search_position(config.keyword, SKU_FROM_CAMPAIGN) 
             # Эмулируем плавающее значение для теста PID
             import random
             current_pos = config.target_position + random.randint(-2, 5)
             if current_pos < 1: current_pos = 1

        # 4. Проверка Target CPA / CTR Safeguard
        # Если CTR слишком низкий, мы сливаем бюджет. Пауза.
        # (В реальном API данные по CTR приходят с задержкой, берем последние доступные)
        # stats = await wb_api_service.get_campaign_stats(...) 
        # ctr = stats.ctr
        ctr = 2.0 # Stub
        if ctr < config.min_ctr:
             logger.info(f"Low CTR ({ctr}%) for {campaign_id}. Pausing/Lowering.")
             # Здесь логика паузы или сброса до min_bid
             # await wb_api_service.pause_campaign(user_token, campaign_id)
             # Log and return

        # 5. Получаем состояние PID из Redis (Hot State)
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
        
        # Инжектим время последнего обновления для корректного dt
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

        # 7. Safe Mode & Execution
        applied_bid = current_bid
        log_action = action
        money_saved = 0.0
        
        if config.safe_mode:
            log_action = "safe_mode"
            # Если PID хотел понизить ставку, считаем это экономией
            if new_bid < current_bid:
                money_saved = current_bid - new_bid
            # В Safe Mode не отправляем запрос в API WB
        else:
            if action == "update":
                success = await wb_api_service.set_campaign_bid(user_token, campaign_id, new_bid)
                if success:
                    applied_bid = new_bid
                    if new_bid < current_bid:
                        money_saved = current_bid - new_bid
                else:
                    log_action = "error_api"

        # 8. Сохраняем новое состояние PID в Redis
        new_state = {
            "prev_error": result["prev_error"],
            "integral": result["integral"],
            "last_pos": result["last_measurement"],
            "last_ts": time.time()
        }
        redis_client.hset(redis_key, mapping=new_state)
        # TTL на сутки, чтобы мусор не копился
        redis_client.expire(redis_key, 86400)

        # 9. Логируем в SQL (для отчетов)
        log_entry = BidderLog(
            config_id=config.id,
            current_pos=current_pos,
            target_pos=config.target_position,
            old_bid=current_bid,
            calculated_bid=new_bid,
            applied_bid=applied_bid,
            money_saved=money_saved,
            action_type=log_action,
            message=f"P:{result['components']['P']:.1f} I:{result['components']['I']:.1f}"
        )
        session.add(log_entry)
        
        # Обновляем last_check конфига
        config.last_check = datetime.utcnow()
        session.commit()
        
        logger.info(f"Bidder {campaign_id}: Pos {current_pos}->{config.target_position} | Bid {current_bid}->{new_bid} | {log_action}")

    except Exception as e:
        logger.error(f"Bidder error {campaign_id}: {e}")
        session.rollback()
    finally:
        session.close()

# --- CELERY TASKS ---

@celery_app.task(name="process_campaign_bid")
def process_campaign_bid(campaign_id: int):
    """
    Consumer: Воркер, который обрабатывает конкретную кампанию.
    Запускает асинхронный event loop для выполнения IO-операций.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_process_bidder_async(campaign_id))
    loop.close()

@celery_app.task(name="run_bidder_cycle")
def run_bidder_cycle():
    """
    Producer: Мастер-процесс (Beat).
    Сканирует активные кампании в БД и ставит задачи в очередь.
    """
    session = SyncSessionLocal()
    try:
        # Выбираем только активные кампании
        active_configs = session.query(BidderConfig.campaign_id).filter(BidderConfig.is_active == True).all()
        
        if not active_configs:
            return "No active campaigns"

        count = 0
        for (camp_id,) in active_configs:
            # Отправляем задачу в очередь Celery (Redis)
            process_campaign_bid.delay(camp_id)
            count += 1
            
        return f"Queued {count} campaigns"
    except Exception as e:
        return f"Error: {e}"
    finally:
        session.close()

# --- EXISTING TASKS (Parse, AI, SEO) ---

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
    session = SyncSessionLocal()
    try:
        skus = [i.sku for i in session.query(MonitoredItem).all()]
        for sku in skus: parse_and_save_sku.delay(sku)
    finally: session.close()

@celery_app.task(name="check_new_orders")
def check_new_orders():
    pass

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