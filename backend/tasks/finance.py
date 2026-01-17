import logging
import asyncio
import aiohttp
import json
import redis
import pandas as pd
from datetime import datetime, timedelta

from celery_app import celery_app, REDIS_URL
from wb_api_service import wb_api_service
from clickhouse_models import ch_service
from database import SyncSessionLocal, User
from forecasting import forecast_demand

logger = logging.getLogger("Tasks-Finance")

try:
    r_client = redis.from_url(REDIS_URL, decode_responses=True)
except Exception as e:
    logger.error(f"Redis connect error: {e}")
    r_client = None

class FinancialSyncProcessor:
    WB_STATS_URL = "https://statistics-api.wildberries.ru/api/v5/supplier/reportDetailByPeriod"
    WB_ORDERS_URL = "https://statistics-api.wildberries.ru/api/v1/supplier/orders"
    BATCH_SIZE = 5000
    
    # Define valid columns strictly matching ClickHouse schema
    VALID_COLUMNS = {
        'rrd_id', 'realizationreport_id', 'supplier_id', 'gi_id', 'subject_name', 
        'nm_id', 'brand_name', 'sa_name', 'ts_name', 'barcode', 'doc_type_name', 
        'office_name', 'supplier_oper_name', 'site_country', 'create_dt', 
        'order_dt', 'sale_dt', 'rr_dt', 'quantity', 'retail_price', 
        'retail_amount', 'sale_percent', 'commission_percent', 
        'retail_price_withdisc_rub', 'delivery_amount', 'return_amount', 
        'delivery_rub', 'gi_box_type_name', 'product_discount_for_report', 
        'supplier_promo', 'rid', 'ppvz_spp_prc', 'ppvz_kvw_prc_base', 
        'ppvz_kvw_prc', 'sup_rating_prc_up', 'is_kgvp_v2', 'ppvz_sales_commission', 
        'ppvz_for_pay', 'ppvz_reward', 'acquiring_fee', 'acquiring_bank', 
        'ppvz_vw', 'ppvz_vw_nds', 'ppvz_office_id', 'penalty', 
        'additional_payment', 'rebill_logistic_cost'
    }

    def __init__(self, token: str, user_id: int):
        self.token = token
        self.user_id = user_id
        self.headers = {"Authorization": token}
        self.semaphore = asyncio.Semaphore(3)
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
        if not self.buffer: 
            return
        try:
            df = pd.DataFrame(self.buffer)
            
            # Filter only valid columns to avoid "Unrecognized column" errors
            valid_cols = [c for c in df.columns if c in self.VALID_COLUMNS]
            df = df[valid_cols]

            numeric_cols = ['retail_price', 'retail_amount', 'retail_price_withdisc_rub', 'delivery_rub', 'ppvz_for_pay', 'penalty', 'additional_payment', 'ppvz_sales_commission', 'ppvz_reward']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            date_cols = ['create_dt', 'order_dt', 'sale_dt', 'rr_dt']
            for col in date_cols:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce').fillna(datetime.now())

            records = df.to_dict('records')
            if records:
                try:
                    ch_service.insert_reports(records)
                    logger.info(f"✅ Flushed {len(records)} records to ClickHouse for user {self.user_id}")
                except Exception as e:
                    # Silently skip if ClickHouse is unavailable (already logged in insert_reports)
                    pass
            self.buffer = []
        except Exception as e:
            logger.error(f"Failed to flush buffer: {e}")
            self.buffer = []

    async def sync_actual_reports(self, date_from: datetime, date_to: datetime):
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
                if not data: break

                processed_batch = []
                for row in data:
                    row['supplier_id'] = self.user_id
                    if not row.get('rr_dt'): row['rr_dt'] = row.get('create_dt')
                    processed_batch.append(row)
                    rrdid = row.get('rrd_id', rrdid)

                self.buffer.extend(processed_batch)
                if len(self.buffer) >= self.BATCH_SIZE:
                    self._flush_buffer()
                
                if len(data) < 1000: break
        
        self._flush_buffer()

    async def sync_provisional_orders(self):
        date_from = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
        async with aiohttp.ClientSession() as session:
            params = {"dateFrom": date_from, "flag": 0} 
            data = await self._fetch_with_retry(session, self.WB_ORDERS_URL, params)
            if not data: return

            for order in data:
                report_row = {
                    "rrd_id": order.get("odid", 0),
                    "realizationreport_id": 0,
                    "supplier_id": self.user_id,
                    "nm_id": order.get("nmId"),
                    "gi_id": 0,
                    "subject_name": order.get("category"),
                    "brand_name": order.get("brand"),
                    "sa_name": order.get("article"),
                    "ts_name": "",
                    "barcode": "",
                    "doc_type_name": "Provisional_Order",
                    "office_name": order.get("warehouseName"),
                    "supplier_oper_name": "",
                    "site_country": order.get("regionName"),
                    "create_dt": order.get("date"),
                    "order_dt": order.get("date"),
                    "sale_dt": order.get("date"),
                    "rr_dt": datetime.now(),
                    "quantity": 1,
                    "retail_price": order.get("priceBeforeDisc", 0),
                    "retail_amount": order.get("priceWithDiscount", 0),
                    "sale_percent": order.get("discountPercent", 0),
                    "commission_percent": 25.00,
                    "retail_price_withdisc_rub": order.get("priceWithDiscount", 0),
                    "delivery_rub": 50.00,
                    "ppvz_sales_commission": order.get("priceWithDiscount", 0) * 0.25,
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
        end = datetime.now()
        start = end - timedelta(days=30)
        logger.info(f"Starting Actual Sync for user {self.user_id}")
        await self.sync_actual_reports(start, end)
        logger.info(f"Starting Provisional Sync for user {self.user_id}")
        await self.sync_provisional_orders()

@celery_app.task(bind=True, name="sync_financial_reports")
def sync_financial_reports(self, user_id: int):
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
        logger.error(f"Sync failed for user {user_id}: {e}")
        return {"status": "error", "error": str(e)}

@celery_app.task(name="train_forecasting_models")
def train_forecasting_models():
    logger.info("Starting forecasting training cycle...")
    try:
        ch_client = ch_service.get_client()
        query_items = "SELECT DISTINCT supplier_id, nm_id FROM wb_analytics.realization_reports WHERE sale_dt > now() - INTERVAL 90 DAY"
        result = ch_client.query(query_items)
        items = result.result_rows
        
        logger.info(f"Found {len(items)} items to forecast.")
        
        for row in items:
            supplier_id, sku = row
            query_history = """
            SELECT toDate(sale_dt) as ds, sum(quantity) as y
            FROM wb_analytics.realization_reports
            WHERE supplier_id = %(uid)s AND nm_id = %(sku)s AND doc_type_name = 'Продажа'
            GROUP BY ds ORDER BY ds ASC
            """
            history_res = ch_client.query(query_history, parameters={'uid': supplier_id, 'sku': sku})
            history_rows = history_res.result_rows
            
            if not history_rows: continue
            
            sales_history = [{"date": str(h[0]), "qty": int(h[1])} for h in history_rows]
            forecast_result = forecast_demand(sales_history, horizon_days=30)
            
            if r_client and forecast_result.get("status") == "success":
                key = f"forecast:{supplier_id}:{sku}"
                r_client.set(key, json.dumps(forecast_result), ex=90000)
                
    except Exception as e:
        logger.error(f"Forecasting cycle failed: {e}")

@celery_app.task(name="sync_product_metadata")
def sync_product_metadata(user_id: int):
    """
    Фоновая задача:
    1. Скачивает габариты всех товаров.
    2. Скачивает текущие комиссии WB.
    3. Скачивает тарифы логистики.
    4. Сохраняет все в Redis для быстрого доступа.
    """
    logger.info(f"Starting metadata sync for user {user_id}")
    session = SyncSessionLocal()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user or not user.wb_api_token:
            return
        token = user.wb_api_token
    finally:
        session.close()

    if not r_client:
        logger.error("Redis not available")
        return

    # Используем asyncio внутри celery для вызова асинхронных методов WB API
    async def _async_sync():
        async with aiohttp.ClientSession() as http_session:
            # Инжектим сессию в сервис (нужно доработать wb_api_service для приема сессии или использовать его методы)
            # Для простоты предполагаем, что wb_api_service методы обновлены для приема session
            
            # 1. Габариты
            dimensions_map = await wb_api_service.get_cards_with_dimensions(token)
            
            # 2. Комиссии
            commissions_map = await wb_api_service.get_all_commissions(token)
            
            # 3. Тарифы логистики (берем на сегодня)
            today = datetime.now().strftime("%Y-%m-%d")
            logistics_tariffs = await wb_api_service.get_box_tariffs(token, today)
            
            # Сохраняем в Redis
            pipe = r_client.pipeline()
            
            # Кешируем габариты на 24 часа
            for nm_id, data in dimensions_map.items():
                key = f"meta:product:{user_id}:{nm_id}"
                pipe.set(key, json.dumps(data), ex=86400)
                
            # Кешируем комиссии на 24 часа (общие для юзера или глобально)
            # Можно кешировать глобально, но тарифы могут зависеть от СПП юзера в будущем
            pipe.set(f"meta:commissions:{user_id}", json.dumps(commissions_map), ex=86400)
            
            # Кешируем логистику
            pipe.set(f"meta:logistics_tariffs", json.dumps(logistics_tariffs), ex=3600*4) # на 4 часа
            
            pipe.execute()
            logger.info(f"Synced {len(dimensions_map)} products metadata")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_async_sync())
    loop.close()