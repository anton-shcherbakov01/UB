# ================
# File: backend/tasks.py
# ================
import json
import logging
import asyncio
import aiohttp
import os
import redis.asyncio as aioredis # Новый импорт для асинхронного Redis
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from celery_app import celery_app
from parser_service import parser_service
from analysis_service import analysis_service
from wb_api_service import wb_api_service
from bot_service import bot_service
from database import SyncSessionLocal, MonitoredItem, PriceHistory, SearchHistory, User, SeoPosition, BidderCampaign, BidderLog
from clickhouse_models import ch_service
from sqlalchemy import select
from bidder_engine import PIDController # Новый импорт

logger = logging.getLogger("CeleryTasks")

# Redis настройки
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

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

# --- HIGH-LOAD FINANCIAL SYNC (NEW) ---

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
            # (In a purely optimized scenario, we would use client.insert_df, but we stick to the service contract)
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


# --- REAL-TIME BIDDER SYSTEM (ASYNC WORKER) ---

class BidderWorker:
    """
    Producer-Consumer Architecture for RTB.
    Producer: Берет активные кампании из Postgres -> Кладет в очередь Redis.
    Consumer: Читает из Redis -> Запрос в WB API -> Расчет PID -> Обновление ставки/Лог.
    """
    QUEUE_KEY = "bidder:queue"
    STATE_KEY_PREFIX = "bidder:state:"

    def __init__(self):
        self.redis = aioredis.from_url(REDIS_URL, decode_responses=True)

    async def producer(self):
        """Читает активные кампании и заполняет очередь."""
        logger.info("BIDDER: Запуск Producer...")
        session = SyncSessionLocal()
        try:
            # Получаем активные кампании с токенами пользователей
            campaigns = session.query(BidderCampaign).join(User).filter(
                BidderCampaign.is_active == True,
                User.wb_api_token.isnot(None)
            ).all()

            if not campaigns:
                logger.info("BIDDER: Нет активных кампаний.")
                return

            pipe = self.redis.pipeline()
            # Очищаем старую очередь (чтобы не копились задачи при падении воркера)
            await pipe.delete(self.QUEUE_KEY)
            
            count = 0
            for camp in campaigns:
                # Payload задачи
                job_data = {
                    "campaign_id": camp.id,
                    "wb_campaign_id": camp.wb_campaign_id,
                    "user_id": camp.user_id,
                    "token": camp.user.wb_api_token,
                    "target_pos": camp.target_position,
                    "max_bid": camp.max_bid,
                    "min_bid": camp.min_bid,
                    "kp": camp.kp,
                    "ki": camp.ki,
                    "kd": camp.kd,
                    "safe_mode": camp.safe_mode,
                    "target_cpa": camp.target_cpa
                }
                await pipe.lpush(self.QUEUE_KEY, json.dumps(job_data))
                count += 1
            
            await pipe.execute()
            logger.info(f"BIDDER: В очереди {count} кампаний.")
            
        except Exception as e:
            logger.error(f"BIDDER Producer Error: {e}")
        finally:
            session.close()

    async def get_pid_state(self, campaign_id: int) -> Dict:
        """Получает состояние PID (интегралы, ошибки) из Redis."""
        key = f"{self.STATE_KEY_PREFIX}{campaign_id}"
        data = await self.redis.hgetall(key)
        if not data:
            return {
                "prev_error": 0.0,
                "integral": 0.0,
                "prev_pos": 0.0,
                "last_update": 0.0
            }
        return {
            "prev_error": float(data.get("prev_error", 0)),
            "integral": float(data.get("integral", 0)),
            "prev_pos": float(data.get("prev_pos", 0)),
            "last_update": float(data.get("last_update", 0))
        }

    async def save_pid_state(self, campaign_id: int, state: Dict):
        key = f"{self.STATE_KEY_PREFIX}{campaign_id}"
        # TTL 24 часа (если кампания остановлена, состояние очистится)
        await self.redis.hset(key, mapping=state)
        await self.redis.expire(key, 86400)

    async def check_cpa_safety(self, token: str, wb_campaign_id: int, target_cpa: int) -> bool:
        """
        Проверяет реальный CPA. Если CPA > Target, возвращает False (небезопасно).
        """
        if not target_cpa or target_cpa <= 0:
            return True # Проверка CPA отключена
            
        stats = await wb_api_service.get_advert_stats(token, wb_campaign_id)
        if not stats or 'days' not in stats:
            return True # Нет данных, считаем безопасным
            
        # Анализируем последние 3 дня
        total_spend = 0
        total_orders = 0
        for day in stats['days'][-3:]:
             total_spend += day.get('sum_price', 0)
             total_orders += day.get('orders', 0)
             
        if total_orders == 0:
            return True # Нельзя рассчитать CPA
            
        real_cpa = total_spend / total_orders
        if real_cpa > target_cpa:
            logger.warning(f"BIDDER: CPA Alert! Campaign {wb_campaign_id} CPA {real_cpa:.0f} > {target_cpa}")
            return False
            
        return True

    async def process_campaign(self, job: Dict):
        """Ядро Consumer: API -> PID -> Action -> Log"""
        camp_id = job['campaign_id']
        wb_id = job['wb_campaign_id']
        token = job['token']
        
        # 1. Получаем состояние
        state = await self.get_pid_state(camp_id)
        current_time = datetime.now().timestamp()
        dt = current_time - state['last_update']
        
        # 2. Получаем реальные данные от WB
        adv_info = await wb_api_service.get_advert_info(token, wb_id)
        if not adv_info:
            logger.error(f"BIDDER: Нет инфо для {wb_id}")
            return

        current_bid = adv_info.get('price', 0)
        # Получаем item_id для обновления ставки (обычно в params)
        params = adv_info.get('params', [])
        item_id = params[0].get('id') if params else None
        
        if not item_id: return

        # Симуляция получения позиции (В реальном проекте тут парсер)
        # Для MVP предполагаем, что позиция меняется динамически
        current_pos = 10 # Placeholder, в реальности: await parser.get_pos(...)
        
        # 3. CPA Guard
        if not await self.check_cpa_safety(token, wb_id, job['target_cpa']):
             # Снижаем ставку до минимума или пауза
             await self.log_action(camp_id, current_pos, current_bid, job['min_bid'], "CPA_GUARD_REDUCE")
             if not job['safe_mode']:
                 await wb_api_service.set_advert_bid(token, wb_id, job['min_bid'], item_id)
             return

        # 4. Расчет PID
        pid = PIDController(
            kp=job['kp'], ki=job['ki'], kd=job['kd'],
            target=job['target_pos'],
            min_out=job['min_bid'], max_out=job['max_bid']
        )
        
        res = pid.update(
            current_val=current_pos,
            current_bid=current_bid,
            dt=dt if dt < 3600 else 0, # Сброс dt, если разрыв большой
            prev_error=state['prev_error'],
            integral=state['integral'],
            prev_measurement=state['prev_pos']
        )
        
        new_bid = int(res['new_bid'])
        
        # 5. Выполнение или Лог (Safe Mode)
        action_type = "UPDATED"
        budget_saved = 0
        
        if res['action'] == 'hold':
            action_type = "HOLD_DEADBAND"
            new_bid = current_bid
        elif job['safe_mode']:
            action_type = "SAFE_MODE_SIMULATION"
            # Гипотетическая экономия (если бы мы перебили конкурента)
            budget_saved = max(0, current_bid - new_bid)
        else:
            # РЕАЛЬНОЕ ОБНОВЛЕНИЕ
            await wb_api_service.set_advert_bid(token, wb_id, new_bid, item_id)
            
        # 6. Сохранение состояния
        new_state = {
            "prev_error": res['error'],
            "integral": res['integral'],
            "prev_pos": current_pos,
            "last_update": current_time
        }
        await self.save_pid_state(camp_id, new_state)
        
        # 7. Лог в БД
        await self.log_action(camp_id, current_pos, current_bid, new_bid, action_type, budget_saved)

    async def log_action(self, camp_id, pos, old_bid, new_bid, action, saved=0):
        session = SyncSessionLocal()
        try:
            log_entry = BidderLog(
                campaign_id=camp_id,
                current_pos=pos,
                competitor_bid=old_bid,
                calculated_bid=new_bid,
                action_taken=action,
                budget_saved=saved
            )
            session.add(log_entry)
            session.commit()
        except Exception as e:
            logger.error(f"BIDDER Log Error: {e}")
        finally:
            session.close()

    async def consumer(self):
        """Читает задачи из Redis и выполняет их."""
        logger.info("BIDDER: Запуск Consumer...")
        while True:
            # Неблокирующее чтение
            job_json = await self.redis.rpop(self.QUEUE_KEY)
            if not job_json:
                break # Очередь пуста
            
            try:
                job = json.loads(job_json)
                await self.process_campaign(job)
            except Exception as e:
                logger.error(f"BIDDER Consumer Job Error: {e}")


# --- ЗАДАЧИ CELERY ---

@celery_app.task(bind=True, name="sync_financial_reports")
def sync_financial_reports(self, user_id: int):
    # ... (код функции оставлен без изменений, см. выше в вашем файле) ...
    self.update_state(state='PROGRESS', meta={'status': 'Initializing Sync...'})
    session = SyncSessionLocal()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user or not user.wb_api_token:
            return {"status": "error", "message": "No token"}
        token = user.wb_api_token
    finally:
        session.close()

    processor = FinancialSyncProcessor(token, user_id)
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(processor.run_full_sync())
        loop.close()
        return {"status": "success", "message": "Financial data synced"}
    except Exception as e:
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
    self.update_state(state='PROGRESS', meta={'status': 'Сбор отзывов...'})
    
    product_info = parser_service.get_full_product_info(sku, limit)
    
    if product_info.get("status") == "error":
        return {"status": "error", "error": product_info.get("message")}
    
    self.update_state(state='PROGRESS', meta={'status': 'Нейросеть думает...'})
    
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

# --- НОВАЯ ЗАДАЧА ДЛЯ БИДДЕРА ---

@celery_app.task(name="bidder_master_task")
def bidder_master_task():
    """
    Периодическая задача (Beat), управляющая ставками.
    Запускается каждые 2-5 минут (настраивается в celery_app).
    """
    worker = BidderWorker()
    
    # Создаем event loop для асинхронного выполнения
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # 1. Producer: Наполнить очередь активными кампаниями
        loop.run_until_complete(worker.producer())
        # 2. Consumer: Обработать задачи из очереди
        loop.run_until_complete(worker.consumer())
    finally:
        loop.close()

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