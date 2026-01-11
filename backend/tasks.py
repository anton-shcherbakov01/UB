import json
import logging
import asyncio
import aiohttp
import pandas as pd
import redis
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from celery_app import celery_app, REDIS_URL
from parser_service import parser_service
from analysis_service import analysis_service
from wb_api_service import wb_api_service
from bot_service import bot_service
from forecasting import forecast_demand
from database import SyncSessionLocal, MonitoredItem, PriceHistory, SearchHistory, User, SeoPosition, BidderLog, ProductCost
from clickhouse_models import ch_service
from sqlalchemy import select
from bidder_engine import PIDController

logger = logging.getLogger("CeleryTasks")

# Redis Client for Bidder State and Forecasting
try:
    # Parsing "redis://host:port/0"
    r_client = redis.from_url(REDIS_URL, decode_responses=True)
except Exception as e:
    logger.error(f"Redis connect error: {e}")
    r_client = None

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

def log_bidder_action_sync(user_id, campaign_id, current_pos, target_pos, prev_bid, calc_bid, action):
    """
    Saves bidder action to Postgres log.
    """
    session = SyncSessionLocal()
    try:
        saved = 0
        if prev_bid and calc_bid:
            saved = prev_bid - calc_bid
            
        log = BidderLog(
            user_id=user_id,
            campaign_id=campaign_id,
            current_pos=current_pos,
            target_pos=target_pos,
            previous_bid=prev_bid,
            calculated_bid=calc_bid,
            saved_amount=saved,
            action=action
        )
        session.add(log)
        session.commit()
    except Exception as e:
        logger.error(f"Bidder Log DB Error: {e}")
    finally:
        session.close()

# --- FORECASTING TRAIN TASK (NEW) ---

@celery_app.task(name="train_forecasting_models")
def train_forecasting_models():
    """
    Ежесуточная задача:
    1. Берет все товары, у которых есть продажи в ClickHouse.
    2. Обучает Prophet модель.
    3. Сохраняет прогноз на 30 дней в Redis (для мгновенной отдачи в API).
    """
    logger.info("Starting forecasting training cycle...")
    
    # 1. Получаем уникальные пары user_id, nm_id из ClickHouse за последние 90 дней
    try:
        ch_client = ch_service.get_client()
        # Выбираем товары, у которых были продажи
        query_items = """
        SELECT DISTINCT supplier_id, nm_id 
        FROM wb_analytics.realization_reports 
        WHERE sale_dt > now() - INTERVAL 90 DAY
        """
        result = ch_client.query(query_items)
        items = result.result_rows
        
        logger.info(f"Found {len(items)} items to forecast.")
        
        for row in items:
            supplier_id, sku = row
            
            # 2. Получаем историю продаж для SKU
            query_history = """
            SELECT toDate(sale_dt) as ds, sum(quantity) as y
            FROM wb_analytics.realization_reports
            WHERE supplier_id = %(uid)s AND nm_id = %(sku)s AND doc_type_name = 'Продажа'
            GROUP BY ds
            ORDER BY ds ASC
            """
            history_res = ch_client.query(query_history, parameters={'uid': supplier_id, 'sku': sku})
            history_rows = history_res.result_rows
            
            if not history_rows: continue
            
            # Преобразуем в формат списка словарей
            sales_history = [{"date": str(h[0]), "qty": int(h[1])} for h in history_rows]
            
            # 3. Запускаем Prophet
            forecast_result = forecast_demand(sales_history, horizon_days=30)
            
            # 4. Сохраняем в Redis (TTL 25 часов - 90000 сек)
            if r_client and forecast_result.get("status") == "success":
                key = f"forecast:{supplier_id}:{sku}"
                # Сохраняем JSON строку
                r_client.set(key, json.dumps(forecast_result), ex=90000)
                # logger.info(f"Forecast saved for {sku}")
                
    except Exception as e:
        logger.error(f"Forecasting cycle failed: {e}")

# --- REAL-TIME BIDDER LOGIC (ASYNC WORKER) ---

class BidderWorker:
    """
    Async Processor for Campaign Bidding.
    """
    def __init__(self, user_id: int, token: str):
        self.user_id = user_id
        self.token = token
        # Config (can be moved to DB settings per campaign)
        self.config = {
            "target_pos": 2, 
            "min_bid": 125, 
            "max_bid": 1000, 
            "safe_mode": True, # ! Important for testing
            "kp": 1.5, "ki": 0.1, "kd": 0.5,
            "min_ctr": 2.5 # Minimum CTR to continue aggressive bidding
        }

    async def process_campaign(self, campaign_id: int):
        campaign_key = f"bidder:state:{campaign_id}"
        
        # 1. Check Metrics (Target CPA safeguard)
        stats = await wb_api_service.get_advert_stats(self.token, campaign_id)
        if stats and stats.get('ctr', 0) < self.config['min_ctr']:
            logger.warning(f"Campaign {campaign_id} paused due to low CTR {stats.get('ctr')}%")
            # Logic to pause campaign or set min bid
            log_bidder_action_sync(self.user_id, campaign_id, 0, 0, 0, 0, "paused_low_ctr")
            return

        # 2. Get Current State from WB
        info = await wb_api_service.get_current_bid_info(self.token, campaign_id)
        current_bid = info.get('price', 0)
        current_pos = info.get('position', 100)
        
        # 3. Load PID State from Redis
        integral = 0.0
        prev_meas = None
        last_update = 0.0
        
        if r_client:
            state = r_client.hgetall(campaign_key)
            if state:
                integral = float(state.get('integral', 0.0))
                prev_meas = float(state.get('prev_meas')) if state.get('prev_meas') else None
                last_update = float(state.get('last_update', 0.0))

        # 4. Calculate DT
        now = datetime.now().timestamp()
        dt = now - last_update if last_update > 0 else 1.0
        
        # 5. PID Calculation
        pid = PIDController(
            kp=self.config['kp'],
            ki=self.config['ki'],
            kd=self.config['kd'],
            target_pos=self.config['target_pos'],
            min_bid=self.config['min_bid'],
            max_bid=self.config['max_bid']
        )
        pid.load_state(integral, prev_meas)
        
        new_bid = pid.update(current_pos, current_bid, dt)
        
        # 6. Save State
        new_integral, new_prev_meas = pid.get_state()
        if r_client:
            r_client.hset(campaign_key, mapping={
                'integral': new_integral,
                'prev_meas': new_prev_meas if new_prev_meas else '',
                'last_update': now
            })
            r_client.expire(campaign_key, 3600) # Expire after 1 hour of inactivity

        # 7. Apply or Safe Mode
        action_type = "update"
        if self.config['safe_mode']:
            logger.info(f"[SAFE MODE] Camp {campaign_id}: Pos {current_pos} -> {self.config['target_pos']}. Bid {current_bid} -> {new_bid}")
            action_type = "safe_mode"
        else:
            if new_bid != current_bid:
                await wb_api_service.update_bid(self.token, campaign_id, new_bid)
                logger.info(f"Updated Camp {campaign_id}: {current_bid} -> {new_bid}")
            else:
                action_type = "no_change"

        # 8. Log
        log_bidder_action_sync(self.user_id, campaign_id, current_pos, self.config['target_pos'], current_bid, new_bid, action_type)

# --- PRODUCER TASK ---

@celery_app.task(name="bidder_producer_task")
def bidder_producer_task():
    """
    Master process: Finds active users and campaigns, queues them for workers.
    Runs every X minutes (e.g., 5 min).
    """
    session = SyncSessionLocal()
    try:
        # Get users with Business plan and token
        users = session.query(User).filter(
            User.subscription_plan == 'business',
            User.wb_api_token.isnot(None)
        ).all()
        
        logger.info(f"Bidder Producer: Found {len(users)} eligible users.")
        
        for user in users:
            # For each user, trigger consumer
            bidder_consumer_task.delay(user.id, user.wb_api_token)
            
    finally:
        session.close()

# --- CONSUMER TASK ---

@celery_app.task(bind=True, name="bidder_consumer_task")
def bidder_consumer_task(self, user_id: int, token: str):
    """
    Worker process: Async wrapper to handle multiple campaigns for a user.
    """
    async def run_cycle():
        # 1. Get Campaigns
        campaigns = await wb_api_service.get_advert_campaigns(token)
        worker = BidderWorker(user_id, token)
        
        tasks = []
        for camp in campaigns:
            # Filter only active campaigns (status 9 = Active usually)
            if camp.get('status') in [9, 11]: 
                tasks.append(worker.process_campaign(camp['id']))
        
        if tasks:
            await asyncio.gather(*tasks)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_cycle())
        loop.close()
    except Exception as e:
        logger.error(f"Bidder Consumer failed for user {user_id}: {e}")


# --- HIGH-LOAD FINANCIAL SYNC (EXISTING) ---

class FinancialSyncProcessor:
    """
    Handles asynchronous fetching, buffering, and batch insertion of WB financial data.
    Implements 'Double Entry' logic (Actual vs Provisional).
    """
    WB_STATS_URL = "https://statistics-api.wildberries.ru/api/v5/supplier/reportDetailByPeriod"
    WB_ORDERS_URL = "https://statistics-api.wildberries.ru/api/v1/supplier/orders"
    BATCH_SIZE = 5000
    
    def __init__(self, token: str, user_id: int):
        self.token = token
        self.user_id = user_id
        self.headers = {"Authorization": token}
        self.semaphore = asyncio.Semaphore(3) # Limit parallel requests to WB
        self.buffer = []

    async def _fetch_with_retry(self, session, url, params, retries=3):
        for i in range(retries):
            async with self.semaphore:
                try:
                    async with session.get(url, params=params, headers=self.headers, timeout=60) as resp:
                        if resp.status == 429:
                            await asyncio.sleep(2 ** (i + 1))
                            continue
                        if resp.status != 200:
                            logger.error(f"WB API Error {resp.status}: {await resp.text()}")
                            return None
                        return await resp.json()
                except Exception as e:
                    logger.warning(f"Fetch attempt {i} failed: {e}")
                    await asyncio.sleep(1)
        return None

    def _flush_buffer(self):
        """Inserts buffered data into ClickHouse."""
        if not self.buffer:
            return
        
        try:
            # Use Pandas for data cleaning/normalization before insert
            df = pd.DataFrame(self.buffer)
            
            # Type casting to match ClickHouse Schema
            numeric_cols = [
                'retail_price', 'retail_amount', 'retail_price_withdisc_rub', 
                'delivery_rub', 'ppvz_for_pay', 'penalty', 'additional_payment',
                'ppvz_sales_commission', 'ppvz_reward'
            ]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            # Convert dates
            date_cols = ['create_dt', 'order_dt', 'sale_dt', 'rr_dt']
            for col in date_cols:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce').fillna(datetime.now())

            # Convert back to list of dicts for the existing ClickHouse service interface
            records = df.to_dict('records')
            
            ch_service.insert_reports(records)
            logger.info(f" flushed {len(records)} records to ClickHouse for user {self.user_id}")
            self.buffer = []
        except Exception as e:
            logger.error(f"Failed to flush buffer: {e}")
            # Keep buffer to retry or drop depending on policy. Here we drop to avoid loop.
            self.buffer = []

    async def sync_actual_reports(self, date_from: datetime, date_to: datetime):
        """
        Fetches 'Actual' data from Realization Reports.
        Uses rrdid for cursor-based pagination.
        """
        async with aiohttp.ClientSession() as session:
            rrdid = 0
            while True:
                params = {
                    "dateFrom": date_from.strftime("%Y-%m-%dT%H:%M:%S"),
                    "dateTo": date_to.strftime("%Y-%m-%dT%H:%M:%S"),
                    "limit": 1000,
                    "rrdid": rrdid
                }
                
                data = await self._fetch_with_retry(session, self.WB_STATS_URL, params)
                if not data:
                    break
                
                if not data: # Empty list
                    break

                processed_batch = []
                for row in data:
                    row['supplier_id'] = self.user_id
                    # Ensure date fields are parsed correctly
                    if not row.get('rr_dt'): row['rr_dt'] = row.get('create_dt')
                    processed_batch.append(row)
                    rrdid = row.get('rrd_id', rrdid)

                self.buffer.extend(processed_batch)
                
                if len(self.buffer) >= self.BATCH_SIZE:
                    self._flush_buffer()
                
                # If we got fewer records than limit, we are done
                if len(data) < 1000:
                    break
        
        # Flush remaining
        self._flush_buffer()

    async def sync_provisional_orders(self):
        """
        Fetches 'Provisional' data (Orders from today/yesterday) to estimate P&L.
        Reconciliation Logic: These records are marked as 'Provisional' in doc_type_name.
        """
        date_from = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
        
        async with aiohttp.ClientSession() as session:
            # Using flag=0 (active orders)
            params = {"dateFrom": date_from, "flag": 0} 
            data = await self._fetch_with_retry(session, self.WB_ORDERS_URL, params)
            
            if not data: return

            for order in data:
                # Map Order Object -> Realization Report Schema
                # This is "Double Entry" logic: estimating costs for unclosed orders
                report_row = {
                    "rrd_id": order.get("odid", 0), # Using Order ID as temp ID
                    "realizationreport_id": 0, # 0 indicates provisional
                    "supplier_id": self.user_id,
                    "nm_id": order.get("nmId"),
                    "gi_id": 0,
                    "subject_name": order.get("category"),
                    "brand_name": order.get("brand"),
                    "sa_name": order.get("article"),
                    "ts_name": "",
                    "barcode": "",
                    "doc_type_name": "Provisional_Order", # MARKER
                    "office_name": order.get("warehouseName"),
                    "supplier_oper_name": "",
                    "site_country": order.get("regionName"),
                    "create_dt": order.get("date"),
                    "order_dt": order.get("date"),
                    "sale_dt": order.get("date"), # Assumption for P&L
                    "rr_dt": datetime.now(),
                    "quantity": 1,
                    "retail_price": order.get("priceBeforeDisc", 0),
                    "retail_amount": order.get("priceWithDiscount", 0),
                    "sale_percent": order.get("discountPercent", 0),
                    "commission_percent": 25.00, # Estimate
                    "retail_price_withdisc_rub": order.get("priceWithDiscount", 0),
                    "delivery_rub": 50.00, # Estimate Logistics
                    "ppvz_sales_commission": order.get("priceWithDiscount", 0) * 0.25, # Estimate
                    "penalty": 0,
                    "additional_payment": 0,
                    "return_amount": 0,
                    "delivery_amount": 1,
                    "product_discount_for_report": 0,
                    "supplier_promo": 0,
                    "rid": order.get("gNumber", 0)
                }
                self.buffer.append(report_row)
            
            self._flush_buffer()

    async def run_full_sync(self):
        # 1. Sync Actual (Last 30 days for safety)
        end = datetime.now()
        start = end - timedelta(days=30)
        logger.info(f"Starting Actual Sync for user {self.user_id}")
        await self.sync_actual_reports(start, end)
        
        # 2. Sync Provisional
        logger.info(f"Starting Provisional Sync for user {self.user_id}")
        await self.sync_provisional_orders()


# --- ЗАДАЧИ CELERY ---

@celery_app.task(bind=True, name="sync_financial_reports")
def sync_financial_reports(self, user_id: int):
    """
    Основная задача синхронизации финансовых данных.
    Запускает асинхронный процессор внутри синхронного воркера.
    """
    self.update_state(state='PROGRESS', meta={'status': 'Initializing Sync...'})
    
    # 1. Get Token
    session = SyncSessionLocal()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user or not user.wb_api_token:
            logger.error(f"User {user_id} has no token")
            return {"status": "error", "message": "No token"}
        
        token = user.wb_api_token
    finally:
        session.close()

    # 2. Run Async Logic
    processor = FinancialSyncProcessor(token, user_id)
    
    try:
        # Create a new event loop for this task
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        loop.run_until_complete(processor.run_full_sync())
        loop.close()
        
        return {"status": "success", "message": "Financial data synced"}
    except Exception as e:
        logger.error(f"Sync failed for user {user_id}: {e}")
        return {"status": "error", "error": str(e)}

@celery_app.task(bind=True, name="parse_and_save_sku")
def parse_and_save_sku(self, sku: int, user_id: int = None):
    self.update_state(state='PROGRESS', meta={'status': 'Запуск парсера...'})
    
    raw_result = parser_service.get_product_data(sku)
    
    if raw_result.get("status") == "error": 
        err_msg = raw_result.get("message", "Unknown error")
        return {"status": "error", "error": err_msg}
    
    self.update_state(state='PROGRESS', meta={'status': 'Сохранение...'})
    
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
    """
    Refactored Orchestration:
    1. Calls Parser to get reviews and product metadata.
    2. Passes everything to AnalysisService (even if empty, for a graceful ABSA response).
    3. Saves enriched history.
    """
    self.update_state(state='PROGRESS', meta={'status': 'Парсинг карточки и отзывов...'})
    
    # [AUDIT] Парсер вызывается здесь. Мы получаем и отзывы, и название товара.
    product_info = parser_service.get_full_product_info(sku, limit)
    
    if product_info.get("status") == "error":
        # Если даже карточка не найдена - тогда возвращаем ошибку
        return {"status": "error", "error": product_info.get("message")}
    
    self.update_state(state='PROGRESS', meta={'status': 'ABSA Аналитика (DeepSeek-V3)...'})
    
    reviews = product_info.get('reviews', [])
    product_name = product_info.get('name', f"Товар {sku}")
    
    # [AUDIT] Передаем данные в сервис аналитики. 
    # Даже если reviews=[], сервис вернет структуру с советами "Как получить первые отзывы".
    ai_result = analysis_service.analyze_reviews_with_ai(reviews, product_name)

    final_result = {
        "status": "success",
        "sku": sku,
        "product_name": product_name,
        "image": product_info.get('image'),
        "rating": product_info.get('rating'),
        "reviews_count": len(reviews),
        "ai_analysis": ai_result
    }

    if user_id:
        title = f"ABSA: {product_name[:30]} ({len(reviews)} отз.)"
        save_history_sync(user_id, sku, 'ai', title, final_result)

    return final_result

@celery_app.task(bind=True, name="generate_seo_task")
def generate_seo_task(self, keywords: list, tone: str, sku: int = 0, user_id: int = None, title_len: int = 100, desc_len: int = 1000):
    self.update_state(state='PROGRESS', meta={'status': 'Генерация контента...'})
    
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
    self.update_state(state='PROGRESS', meta={'status': 'Парсинг поиска...'})
    
    position = parser_service.get_search_position(keyword, sku)
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

def _process_orders_sync():
    """Синхронная обертка для проверки заказов (уведомления)."""
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
                    return True
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

@celery_app.task(name="check_new_orders")
def check_new_orders():
    _process_orders_sync()