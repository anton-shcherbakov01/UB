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

def get_redis_client():
    return redis.Redis(host='redis', port=6379, db=0, decode_responses=True)

async def notify_user_events(user, settings, r_client):
    if not user.wb_api_token or not user.telegram_id: return
    orders_key = f"notif:seen:orders:{user.id}"
    sales_key = f"notif:seen:sales:{user.id}"

    if settings.notify_new_orders:
        orders = await wb_api_service.get_new_orders_since(user.wb_api_token, user.last_order_check)
        for o in orders:
            srid = o.get('srid')
            if not srid or r_client.sismember(orders_key, srid): continue
            r_client.sadd(orders_key, srid)
            r_client.expire(orders_key, 172800)
            price = o.get('priceWithDiscount', 0)
            msg = f"⚡️ <b>Новый заказ!</b>\n📦 {o.get('subject')} | <code>{o.get('supplierArticle')}</code>\n💰 Сумма: <b>{price:,.0f} ₽</b>\n📍 {o.get('warehouseName')} ➡️ {o.get('oblastOkrugName')}\n"
            await bot_service.send_message(user.telegram_id, msg)

    if settings.notify_buyouts:
        date_from = (datetime.utcnow() - timedelta(minutes=30)).isoformat()
        sales = await wb_api_service.get_sales_since(user.wb_api_token, date_from)
        for s in sales:
            sale_id = s.get('saleID')
            if not sale_id or str(sale_id).startswith('R') or r_client.sismember(sales_key, sale_id): continue
            r_client.sadd(sales_key, sale_id)
            r_client.expire(sales_key, 172800)
            price = s.get('priceWithDiscount', 0)
            msg = f"💵 <b>Товар выкуплен!</b>\n📦 {s.get('subject')} | <code>{s.get('supplierArticle')}</code>\n💰 К перечислению: <b>{price:,.0f} ₽</b>"
            await bot_service.send_message(user.telegram_id, msg)

@celery_app.task(name="check_new_orders")
def check_new_orders():
    session = SyncSessionLocal()
    r_client = get_redis_client()
    try:
        users = session.query(User).join(NotificationSettings).filter(User.wb_api_token.isnot(None)).all()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        for user in users:
            loop.run_until_complete(notify_user_events(user, user.notification_settings, r_client))
            user.last_order_check = datetime.utcnow()
            session.commit()
        loop.close()
    finally: session.close()

@celery_app.task(name="send_hourly_summary")
def send_hourly_summary():
    """Сводка с учетом персонального интервала пользователя"""
    session = SyncSessionLocal()
    try:
        # Берем пользователей, у которых включена сводка
        users = session.query(User).join(NotificationSettings).filter(
            User.wb_api_token.isnot(None),
            NotificationSettings.notify_hourly_stats == True
        ).all()
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        now = datetime.utcnow()

        for user in users:
            settings = user.notification_settings
            # Проверяем, пришло ли время отправки по интервалу
            last_sent = settings.last_summary_at or (now - timedelta(hours=settings.summary_interval))
            if (now - last_sent).total_seconds() >= (settings.summary_interval * 3600 - 60):
                try:
                    stats = loop.run_until_complete(wb_api_service.get_statistics_today(user.wb_api_token))
                    msg = f"📊 <b>Сводка за сегодня</b> ({datetime.now().strftime('%H:%M')})\n➖➖➖➖➖➖➖➖\n💰 Заказы: <b>{stats['orders_sum']:,.0f} ₽</b> ({stats['orders_count']} шт)\n💵 Выкупы: <b>{stats['sales_sum']:,.0f} ₽</b> ({stats['sales_count']} шт)\n"
                    # Воронка показывается если включена в настройках (даже если данные 0 - заглушка)
                    if settings.show_funnel:
                        visitors = stats.get('visitors', 0)
                        addToCart = stats.get('addToCart', 0)
                        if visitors > 0 or addToCart > 0:
                            msg += f"\n<b>Воронка:</b>\n👁 Просмотры: {visitors}\n🛒 Корзины: {addToCart}\n"
                        else:
                            msg += f"\n<b>Воронка:</b>\n👁 Просмотры: <i>данные недоступны</i>\n🛒 Корзины: <i>данные недоступны</i>\n"
                    
                    loop.run_until_complete(bot_service.send_message(user.telegram_id, msg))
                    # Обновляем время последней отправки
                    settings.last_summary_at = now
                    session.commit()
                except Exception as e:
                    logger.error(f"Summary failed for {user.id}: {e}")
        
        loop.close()
    finally: session.close()