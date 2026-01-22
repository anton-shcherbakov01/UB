import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import select

from celery_app import celery_app
from database import SyncSessionLocal, PriceAlert, User, NotificationSettings
from wb_api_service import wb_api_service
from bot_service import bot_service

logger = logging.getLogger("Task-PriceControl")

@celery_app.task(name="check_price_alerts")
def check_price_alerts():
    """
    Проверка цен через официальный API.
    Работает быстро, проверяет всех активных юзеров.
    """
    session = SyncSessionLocal()
    try:
        # 1. Находим пользователей, у которых есть активные алерты
        # Группируем, чтобы делать по 1 запросу к API на юзера
        users_with_alerts = session.query(User).join(PriceAlert).filter(
            PriceAlert.is_active == True,
            PriceAlert.min_price > 0,
            User.wb_api_token.isnot(None)
        ).distinct().all()
        
        logger.info(f"Checking prices for {len(users_with_alerts)} users...")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        for user in users_with_alerts:
            try:
                # 2. Получаем ВСЕ текущие цены юзера одним запросом
                # Это занимает миллисекунды
                current_goods = loop.run_until_complete(wb_api_service.get_all_goods_prices(user.wb_api_token))
                
                # Создаем мапу {sku: {price, discount}}
                goods_map = {
                    item['nmID']: {
                        'base': int(item['price']),
                        'discount': int(item['discount'])
                    } 
                    for item in current_goods
                }
                
                # 3. Проверяем алерты этого юзера
                alerts = session.query(PriceAlert).filter(
                    PriceAlert.user_id == user.id,
                    PriceAlert.is_active == True,
                    PriceAlert.min_price > 0
                ).all()
                
                messages = []
                
                for alert in alerts:
                    product = goods_map.get(alert.sku)
                    if not product: continue
                    
                    # Расчет цены селлера
                    current_price = int(product['base'] * (1 - product['discount'] / 100))
                    
                    # Сохраняем в БД для истории
                    alert.last_price = current_price
                    alert.last_check = datetime.utcnow()
                    
                    # ЛОГИКА ТРЕВОГИ
                    if current_price < alert.min_price:
                        # Анти-спам: не чаще раза в сутки, если цена все еще низкая
                        last_sent = alert.last_alert_sent
                        should_notify = False
                        
                        if not last_sent:
                            should_notify = True
                        elif (datetime.utcnow() - last_sent).total_seconds() > 86400: # 24 часа
                            should_notify = True
                            
                        if should_notify:
                            diff = alert.min_price - current_price
                            percent = round((diff / alert.min_price) * 100, 1)
                            
                            # Добавляем в список уведомлений
                            messages.append(
                                f"📦 <b>SKU {alert.sku}</b>\n"
                                f"📉 Цена: <b>{current_price} ₽</b> (Мин: {alert.min_price})\n"
                                f"⚠️ Скидка: {product['discount']}% (Упала на {diff} ₽)"
                            )
                            
                            alert.last_alert_sent = datetime.utcnow()

                # 4. Отправка сводного уведомления
                if messages:
                    # Проверяем настройки
                    settings = session.query(NotificationSettings).filter_by(user_id=user.id).first()
                    if settings and settings.notify_price_drop:
                        header = "🚨 <b>PRICE ALERT: Цены упали ниже порога!</b>\n\n"
                        # Разбиваем на сообщения, если их много
                        full_text = header + "\n\n".join(messages)
                        
                        # Если текст слишком длинный, шлем частями (Telegram лимит 4096)
                        if len(full_text) > 4000:
                            parts = [messages[i:i+10] for i in range(0, len(messages), 10)]
                            for part in parts:
                                txt = header + "\n\n".join(part)
                                loop.run_until_complete(bot_service.send_message(user.telegram_id, txt))
                        else:
                            loop.run_until_complete(bot_service.send_message(user.telegram_id, full_text))
                            
                        logger.info(f"Sent {len(messages)} alerts to user {user.id}")

            except Exception as e:
                logger.error(f"Error checking user {user.id}: {e}")
        
        session.commit()
        loop.close()
    finally:
        session.close()