import logging
import asyncio
from datetime import datetime, timedelta

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
    """
    Синхронная обертка для проверки заказов и отправки уведомлений.
    """
    session = SyncSessionLocal()
    try:
        # Берем только пользователей с токеном
        users = session.query(User).filter(User.wb_api_token.isnot(None)).all()
        
        async def check_user_orders(user):
            # Фиксируем время ДО запроса, чтобы не потерять заказы в "окне" выполнения
            current_check_time = datetime.now()

            # 1. Защита от спама при первом запуске
            if not user.last_order_check:
                # Если это первая проверка, просто сохраняем время и выходим.
                # Иначе пользователю прилетит 100 сообщений за прошлые сутки.
                user.last_order_check = current_check_time
                session.commit()
                return False

            try:
                # Получаем заказы с момента прошлой проверки
                new_orders = await wb_api_service.get_new_orders_since(user.wb_api_token, user.last_order_check)
                
                if not new_orders:
                    # Даже если нет заказов, обновляем время проверки, чтобы в след раз не сканировать лишнее
                    user.last_order_check = current_check_time
                    session.commit()
                    return False

                # 2. Формируем красивое сообщение (Dashboard Style)
                count = len(new_orders)
                total_sum = sum(x.get('priceWithDiscount', 0) for x in new_orders)
                
                # Заголовок
                msg = f"⚡️ <b>Новый заказ! +{count} шт.</b>\n"
                msg += f"➖➖➖➖➖➖➖➖\n\n"
                
                # Список товаров (максимум 5, чтобы не засорять чат)
                for order in new_orders[:5]:
                    price = order.get('priceWithDiscount', 0)
                    # Пытаемся найти понятное название
                    category = order.get('category') or order.get('subject') or 'Товар'
                    article = order.get('supplierArticle', '') or order.get('nmId', '')
                    
                    msg += f"📦 <b>{category}</b>\n"
                    if article:
                        msg += f"└ <code>{article}</code>\n"
                    msg += f"   💰 <b>{price:,.0f} ₽</b>\n\n"
                
                if count > 5:
                    msg += f"<i>...и еще {count - 5} позиций</i>\n\n"
                
                # Футер
                msg += f"➖➖➖➖➖➖➖➖\n"
                msg += f"💸 <b>Выручка: {total_sum:,.0f} ₽</b>"

                # 3. Отправляем и СОХРАНЯЕМ время
                await bot_service.send_message(user.telegram_id, msg)
                
                # Обновляем время только после успешной обработки
                user.last_order_check = current_check_time
                session.commit()
                return True

            except Exception as e:
                logger.error(f"Error checking orders for user {user.id}: {e}")
                return False

        # Запуск асинхронного цикла внутри синхронной задачи Celery
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        for user in users:
            loop.run_until_complete(check_user_orders(user))
            
        loop.close()
        
    finally:
        session.close()

@celery_app.task(name="check_new_orders")
def check_new_orders():
    _process_orders_sync()