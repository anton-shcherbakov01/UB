import json
import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from celery_app import celery_app
from parser_service import parser_service
from analysis_service import analysis_service
from wb_api_service import wb_api_service
from bot_service import bot_service
from database import SyncSessionLocal, MonitoredItem, PriceHistory, SearchHistory, User, SeoPosition, BidderConfig
from clickhouse_models import ch_client
from sqlalchemy import select

logger = logging.getLogger("CeleryTasks")

# ... (Существующие методы: save_history_sync, save_price_sync, save_seo_position_sync оставляем без изменений) ...
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

# ... (Существующие tasks: parse_and_save_sku, analyze_reviews_task, generate_seo_task, check_seo_position_task, update_all_monitored_items, check_new_orders, run_bidder_cycle оставляем) ...

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
    # ... existing implementation ...
    pass 

@celery_app.task(name="run_bidder_cycle")
def run_bidder_cycle():
    # ... existing implementation ...
    pass

# --- NEW: FINANCIAL SYNC TASK ---

@celery_app.task(bind=True, name="sync_financial_reports")
def sync_financial_reports(self):
    """
    Задача синхронизации финансовых отчетов.
    1. Берет всех юзеров с токенами.
    2. Асинхронно выкачивает реализацию (/api/v5/supplier/reportDetailByPeriod).
    3. Кладет в ClickHouse.
    """
    self.update_state(state='PROGRESS', meta={'status': 'Starting Sync...'})
    
    # Инициализация схемы если еще нет
    ch_client.init_schema()
    
    session = SyncSessionLocal()
    try:
        users = session.query(User).filter(User.wb_api_token.isnot(None)).all()
        logger.info(f"Syncing finances for {len(users)} users")

        async def fetch_and_save(user):
            date_from = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d") # Забираем последние 3 месяца
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
                            # Определяем столбцы, соответствующие схеме ClickHouse
                            columns = [
                                'rrd_id', 'supplier_id', 'realizationreport_id', 
                                'sale_dt', 'create_dt', 'date_from', 'date_to',
                                'nm_id', 'brand_name', 'sa_name', 'subject_name', 'ts_name', 'barcode',
                                'doc_type_name', 'supplier_oper_name',
                                'retail_price', 'retail_amount', 'commission_percent', 
                                'commission_amount', 'retail_price_withdisc_rub',
                                'delivery_rub', 'delivery_amount', 'return_amount', 
                                'penalty', 'additional_payment',
                                'office_name', 'site_country',
                                'record_status'
                            ]
                            
                            for item in data:
                                try:
                                    # Парсинг дат
                                    s_dt = datetime.strptime(item.get('sale_dt', ''), "%Y-%m-%dT%H:%M:%SZ") if item.get('sale_dt') else datetime.now()
                                    c_dt = datetime.strptime(item.get('create_dt', ''), "%Y-%m-%dT%H:%M:%SZ") if item.get('create_dt') else datetime.now()
                                    d_from = datetime.strptime(item.get('date_from', ''), "%Y-%m-%dT%H:%M:%SZ") if item.get('date_from') else datetime.now()
                                    d_to = datetime.strptime(item.get('date_to', ''), "%Y-%m-%dT%H:%M:%SZ") if item.get('date_to') else datetime.now()

                                    row = [
                                        int(item.get('rrd_id', 0)),
                                        user.id, # Используем ID юзера как supplier_id
                                        int(item.get('realizationreport_id', 0)),
                                        s_dt, c_dt, d_from, d_to,
                                        int(item.get('nm_id', 0)),
                                        str(item.get('brand_name', '')),
                                        str(item.get('sa_name', '')),
                                        str(item.get('subject_name', '')),
                                        str(item.get('ts_name', '')),
                                        str(item.get('barcode', '')),
                                        str(item.get('doc_type_name', '')),
                                        str(item.get('supplier_oper_name', '')),
                                        float(item.get('retail_price', 0) or 0),
                                        float(item.get('retail_amount', 0) or 0),
                                        float(item.get('commission_percent', 0) or 0),
                                        float(item.get('commission_amount', 0) or 0),
                                        float(item.get('retail_price_withdisc_rub', 0) or 0),
                                        float(item.get('delivery_rub', 0) or 0),
                                        int(item.get('delivery_amount', 0)),
                                        int(item.get('return_amount', 0)),
                                        float(item.get('penalty', 0) or 0),
                                        float(item.get('additional_payment', 0) or 0),
                                        str(item.get('office_name', '')),
                                        str(item.get('site_country', '')),
                                        'actual' # record_status
                                    ]
                                    rows_to_insert.append(row)
                                except Exception as e:
                                    # Skip bad rows
                                    continue
                                    
                            if rows_to_insert:
                                # Вставка в ClickHouse
                                ch_client.insert_reports(rows_to_insert, columns)
                                logger.info(f"Inserted {len(rows_to_insert)} rows for user {user.id}")

                        elif resp.status == 429:
                            logger.warning(f"Rate limit for user {user.id}")
                            await asyncio.sleep(5)
                        else:
                            logger.error(f"WB API Error {resp.status} for user {user.id}")
                except Exception as e:
                    logger.error(f"Fetch error user {user.id}: {e}")

        # Запуск цикла событий для асинхронной выкачки
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Ограничиваем одновременные запросы семафором, если нужно,
        # но здесь просто последовательно/параллельно через gather
        tasks = [fetch_and_save(u) for u in users]
        loop.run_until_complete(asyncio.gather(*tasks))
        loop.close()

    finally:
        session.close()

    return {"status": "finished"}