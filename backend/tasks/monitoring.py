import logging
import asyncio
from datetime import datetime

from celery_app import celery_app
from parser_service import parser_service
from analysis_service import analysis_service
from wb_api_service import wb_api_service
from bot_service import bot_service
from database import SyncSessionLocal, MonitoredItem, User
from .utils import save_price_sync, save_history_sync

logger = logging.getLogger("Tasks-Monitoring")

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

def _process_orders_sync():
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