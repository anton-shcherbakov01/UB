import logging
import asyncio
import redis
from datetime import datetime, timedelta

from celery_app import celery_app
from parser_service import parser_service
from analysis_service import analysis_service
from wb_api_service import wb_api_service
from bot_service import bot_service
from database import SyncSessionLocal, MonitoredItem, User, NotificationSettings
from sqlalchemy import select
from .utils import save_price_sync, save_history_sync

logger = logging.getLogger("Tasks-Monitoring")

# --- Парсинг и Мониторинг товаров (Оставляем как было) ---

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

# --- НОВАЯ ЛОГИКА УВЕДОМЛЕНИЙ (Telegram Bot) ---

def get_redis_conn():
    # Соединение с Redis для проверки дублей
    return redis.Redis(host='redis', port=6379, db=0, decode_responses=True)

async def process_user_events(user, settings, r_redis):
    """
    Асинхронная проверка заказов и выкупов с дедупликацией через Redis.
    """
    if not user.wb_api_token or not user.telegram_id:
        return

    # Ключи множеств (Sets) в Redis для хранения ID уже отправленных событий
    # TTL (время жизни) ключей ставим 48 часов, чтобы точно не спамить
    orders_set_key = f"seen_orders:{user.id}"
    sales_set_key = f"seen_sales:{user.id}"
    
    # --- 1. ЗАКАЗЫ ---
    if settings.notify_new_orders:
        # Берем заказы за последний час (с запасом), Redis отфильтрует старые
        date_from = (datetime.utcnow() - timedelta(minutes=60)).isoformat()
        try:
            orders = await wb_api_service.get_new_orders_since(user.wb_api_token, date_from)
            
            for order in orders:
                srid = order.get('srid')
                if not srid: continue
                
                # ПРОВЕРКА ДУБЛЕЙ: Если srid уже есть в Redis, пропускаем
                if r_redis.sismember(orders_set_key, srid):
                    continue 
                
                # Если нет - добавляем в базу "просмотренных" и продлеваем жизнь ключа
                r_redis.sadd(orders_set_key, srid)
                r_redis.expire(orders_set_key, 172800) # 48 часов
                
                # Формируем сообщение
                price = order.get('priceWithDiscount', 0)
                subject = order.get('subject', 'Товар')
                article = order.get('supplierArticle', '') or order.get('nmId', '')
                warehouse = order.get('warehouseName', 'Склад')
                region = order.get('oblastOkrugName', 'Регион')

                msg = f"⚡️ <b>Новый заказ!</b>\n"
                msg += f"📦 {subject} | <code>{article}</code>\n"
                msg += f"💰 <b>{price:,.0f} ₽</b>\n"
                msg += f"📍 {warehouse} ➡️ {region}\n"
                
                if settings.show_daily_revenue:
                    msg += f"\n<i>(Итоги дня будут в часовой сводке)</i>"

                await bot_service.send_message(user.telegram_id, msg)

        except Exception as e:
            logger.error(f"Error processing orders for user {user.id}: {e}")

    # --- 2. ВЫКУПЫ (Продажи) ---
    if settings.notify_buyouts:
        date_from = (datetime.utcnow() - timedelta(minutes=60)).isoformat()
        try:
            # Используем метод API продаж (реализован в wb_api_service)
            # Если метода get_sales нет, нужно добавить. Используем заглушку логики.
            sales = await wb_api_service.get_sales(user.wb_api_token, date_from) 
            
            for sale in sales:
                sale_id = sale.get('saleID')
                if not sale_id or str(sale_id).startswith("R"): continue # Игнорируем возвраты пока
                
                if r_redis.sismember(sales_set_key, sale_id):
                    continue
                
                r_redis.sadd(sales_set_key, sale_id)
                r_redis.expire(sales_set_key, 172800)
                
                price = sale.get('priceWithDiscount', 0)
                subject = sale.get('subject', '')
                
                msg = f"💵 <b>ВЫКУП! Товар оплачен.</b>\n"
                msg += f"📦 {subject}\n"
                msg += f"💰 <b>+{price:,.0f} ₽</b> (К перечислению)\n"
                
                await bot_service.send_message(user.telegram_id, msg)

        except Exception as e:
            logger.error(f"Error processing sales for user {user.id}: {e}")

async def send_user_summary(user, settings):
    """
    Отправка часовой сводки (Выручка, воронка).
    """
    if not settings.notify_hourly_stats: return

    try:
        # Получаем статистику за сегодня (метод должен быть в wb_api_service)
        # Если его нет, вернет пустой dict, и мы не упадем
        stats = await wb_api_service.get_statistics_today(user.wb_api_token) 
        
        if not stats or (stats.get('orders_count', 0) == 0 and stats.get('sales_count', 0) == 0):
            return # Не спамим пустыми отчетами

        msg = f"📊 <b>Сводка за сегодня</b> ({datetime.now().strftime('%H:%M')})\n"
        msg += "➖➖➖➖➖➖➖➖\n"
        
        # Финансы
        orders_sum = stats.get('orders_sum', 0)
        sales_sum = stats.get('sales_sum', 0)
        
        msg += f"💰 <b>Заказов:</b> {orders_sum:,.0f} ₽ ({stats.get('orders_count', 0)} шт)\n"
        msg += f"💵 <b>Выкупов:</b> {sales_sum:,.0f} ₽ ({stats.get('sales_count', 0)} шт)\n\n"
        
        # Воронка (если включена и данные есть)
        if settings.show_funnel and stats.get('visitors'):
            msg += "<b>Воронка продаж:</b>\n"
            msg += f"👁 Просмотры: {stats['visitors']}\n"
            msg += f"🛒 В корзину: {stats.get('addToCart', 0)}\n"
            msg += f"⚡️ Заказы: {stats.get('orders_count', 0)}\n"
        
        await bot_service.send_message(user.telegram_id, msg)
    except Exception as e:
        logger.error(f"Error sending summary for user {user.id}: {e}")

# --- Celery Tasks для Уведомлений ---

@celery_app.task(name="check_new_orders")
def check_new_orders():
    """
    Задача запускается часто (каждые 5-10 мин).
    Проверяет новые заказы/выкупы и шлет мгновенные уведомления.
    """
    session = SyncSessionLocal()
    r_redis = get_redis_conn()
    
    try:
        # Загружаем пользователей вместе с настройками
        users = session.query(User).filter(User.wb_api_token.isnot(None)).all()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        for user in users:
            # Если настроек нет, пропускаем (или создаем дефолтные, если логика позволяет)
            if not user.notification_settings:
                continue 
                
            loop.run_until_complete(process_user_events(user, user.notification_settings, r_redis))
            
        loop.close()
    except Exception as e:
        logger.error(f"Global order check failed: {e}")
    finally:
        session.close()

@celery_app.task(name="send_hourly_summary")
def send_hourly_summary_task():
    """
    Задача запускается раз в час.
    Шлет сводку по выручке и воронке.
    """
    session = SyncSessionLocal()
    try:
        users = session.query(User).filter(User.wb_api_token.isnot(None)).all()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        for user in users:
            if user.notification_settings and user.notification_settings.notify_hourly_stats:
                loop.run_until_complete(send_user_summary(user, user.notification_settings))
        
        loop.close()
    except Exception as e:
        logger.error(f"Global summary send failed: {e}")
    finally:
        session.close()