import logging
import asyncio
import redis
from datetime import datetime, timedelta

from celery_app import celery_app
from parser_service import parser_service
from analysis_service import analysis_service
from wb_api import wb_api_service
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

async def process_user_notifications(user, settings, r_client):
    """Проверка новых событий и отправка в ТГ"""
    if not user.wb_api_token or not user.telegram_id: return

    # Ключи в Redis для отслеживания уже отправленного
    orders_key = f"seen_orders:{user.id}"
    sales_key = f"seen_sales:{user.id}"

    # 1. ЗАКАЗЫ
    if settings.notify_new_orders:
        try:
            # Запрашиваем заказы с момента последней проверки
            new_orders = await wb_api_service.get_new_orders_since(user.wb_api_token, user.last_order_check)
            
            for order in new_orders:
                srid = order.get('srid')
                if not srid or r_client.sismember(orders_key, srid):
                    continue
                
                # Помечаем как отправленное
                r_client.sadd(orders_key, srid)
                r_client.expire(orders_key, 172800) # 48 часов

                price = order.get('priceWithDiscount', 0)
                msg = f"⚡️ <b>Новый заказ!</b>\n"
                msg += f"📦 {order.get('subject')} | <code>{order.get('supplierArticle')}</code>\n"
                msg += f"💰 Сумма: <b>{price:,.0f} ₽</b>\n"
                msg += f"📍 Склад: {order.get('warehouseName')}\n"
                
                if settings.show_daily_revenue:
                    msg += f"\n<i>Статистика за день доступна в ежечасной сводке.</i>"
                
                await bot_service.send_message(user.telegram_id, msg)
        except Exception as e:
            logger.error(f"Order notify error for {user.id}: {e}")

    # 2. ВЫКУПЫ
    if settings.notify_buyouts:
        try:
            df = (datetime.now() - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")
            sales = await wb_api_service.get_sales_since(user.wb_api_token, df)
            
            for sale in sales:
                sale_id = sale.get('saleID')
                if not sale_id or str(sale_id).startswith('R') or r_client.sismember(sales_key, sale_id):
                    continue

                r_client.sadd(sales_key, sale_id)
                r_client.expire(sales_key, 172800)

                price = sale.get('priceWithDiscount', 0)
                msg = f"💵 <b>Товар выкуплен!</b>\n"
                msg += f"📦 {sale.get('subject')} | <code>{sale.get('supplierArticle')}</code>\n"
                msg += f"💰 Выручка: <b>{price:,.0f} ₽</b>"
                
                await bot_service.send_message(user.telegram_id, msg)
        except Exception as e:
            logger.error(f"Sale notify error for {user.id}: {e}")

@celery_app.task(name="check_new_orders")
def check_new_orders():
    """Задача проверки заказов (раз в 10 мин)"""
    session = SyncSessionLocal()
    r_client = get_redis_client()
    try:
        # Ищем пользователей с токеном и включенными уведами
        users = session.query(User).join(NotificationSettings).filter(
            User.wb_api_token.isnot(None),
            (NotificationSettings.notify_new_orders == True) | (NotificationSettings.notify_buyouts == True)
        ).all()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        for user in users:
            loop.run_until_complete(process_user_notifications(user, user.notification_settings, r_client))
            # Обновляем время проверки
            user.last_order_check = datetime.now()
            session.commit()
            
        loop.close()
    finally:
        session.close()

@celery_app.task(name="send_hourly_summary")
def send_hourly_summary():
    """Задача часовой сводки"""
    session = SyncSessionLocal()
    try:
        users = session.query(User).join(NotificationSettings).filter(
            User.wb_api_token.isnot(None),
            NotificationSettings.notify_hourly_stats == True
        ).all()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        for user in users:
            try:
                stats = loop.run_until_complete(wb_api_service.get_statistics_today(user.wb_api_token))
                
                msg = f"📊 <b>Сводка на {datetime.now().strftime('%H:%M')}</b>\n"
                msg += f"➖➖➖➖➖➖➖➖\n"
                msg += f"💰 Заказов сегодня: <b>{stats['orders_sum']:,.0f} ₽</b> ({stats['orders_count']} шт)\n"
                msg += f"💵 Выкупов сегодня: <b>{stats['sales_sum']:,.0f} ₽</b> ({stats['sales_count']} шт)\n"
                
                if user.notification_settings.show_funnel:
                    msg += f"\n<b>Аналитика:</b>\n"
                    msg += f"👁 Просмотры: {stats['visitors']}\n"
                    msg += f"🛒 Корзины: {stats['addToCart']}"
                
                loop.run_until_complete(bot_service.send_message(user.telegram_id, msg))
            except: continue
            
        loop.close()
    finally:
        session.close()

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