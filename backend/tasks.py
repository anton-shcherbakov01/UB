import asyncio
from celery_app import celery_app
from parser_service import parser_service
from analysis_service import analysis_service
from database import AsyncSessionLocal, User
from sqlalchemy import select
import logging

logger = logging.getLogger("CeleryWorker")

async def save_price_to_db(sku: int, data: dict):
    if data.get("status") == "error": return

    async with AsyncSessionLocal() as session:
        stmt = select(MonitoredItem).where(MonitoredItem.sku == sku)
        result = await session.execute(stmt)
        item = result.scalars().first()

        if not item:
            item = MonitoredItem(sku=sku, name=data.get("name"), brand=data.get("brand"))
            session.add(item)
            await session.commit()
            await session.refresh(item)
        
        prices = data.get("prices", {})
        history = PriceHistory(
            item_id=item.id,
            wallet_price=prices.get("wallet_purple", 0),
            standard_price=prices.get("standard_black", 0),
            base_price=prices.get("base_crossed", 0)
        )
        session.add(history)
        await session.commit()
        logger.info(f"DB: Данные для {sku} сохранены.")

@celery_app.task(bind=True, name="parse_and_save_sku")
def parse_and_save_sku(self, sku: int):
    """
    Задача с обновлением статуса для пользователя.
    """
    logger.info(f"Task: Начало обработки {sku}")
    
    # Сообщаем фронтенду: "Я начал!"
    self.update_state(state='PROGRESS', meta={'status': 'Запуск браузера...'})
    
    # Парсинг
    raw_result = parser_service.get_product_data(sku)
    
    if raw_result.get("status") == "error":
        # Если ошибка, не просто падаем, а возвращаем причину
        return {"status": "error", "error": raw_result.get("message")}
    
    # Сообщаем фронтенду: "Сохраняю..."
    self.update_state(state='PROGRESS', meta={'status': 'Анализ и сохранение...'})

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(save_price_to_db(sku, raw_result))
    except Exception as e:
        logger.error(f"Ошибка БД: {e}")

    final_result = analysis_service.calculate_metrics(raw_result)
    return final_result

@celery_app.task(name="update_all_monitored_items")
def update_all_monitored_items():
    async def get_all_skus():
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(MonitoredItem.sku))
            return result.scalars().all()

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        skus = loop.run_until_complete(get_all_skus())
        
        logger.info(f"Beat: Обновление {len(skus)} товаров...")
        for sku in skus:
            parse_and_save_sku.delay(sku)
    except Exception as e:
        logger.error(f"Beat Error: {e}")

@celery_app.task(bind=True, name="analyze_reviews_task")
def analyze_reviews_task(self, sku: int, user_id: int):
    """
    Задача: Собрать отзывы -> Отправить в ИИ -> Вернуть результат.
    """
    logger.info(f"Task: AI Анализ отзывов {sku} для юзера {user_id}")
    self.update_state(state='PROGRESS', meta={'status': 'Сбор отзывов с WB...'})
    
    # 1. Проверяем тариф пользователя, чтобы узнать лимит
    # (Здесь упрощенно, в идеале нужно делать запрос в БД, но можно передать лимит в аргументах)
    limit = 50 # Default Free
    
    # 2. Парсим отзывы
    product_data = parser_service.get_full_product_info(sku, limit)
    
    if product_data.get("status") == "error":
        return {"status": "error", "error": product_data.get("message")}
    
    self.update_state(state='PROGRESS', meta={'status': 'Думает нейросеть...'})
    
    # 3. Отправляем в ИИ
    ai_result = {}
    if product_data['reviews']:
        # Запускаем асинхронный вызов ИИ внутри синхронной задачи
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ai_result = loop.run_until_complete(
            analysis_service.analyze_reviews_with_ai(product_data['reviews'], f"Товар {sku}")
        )
    
    # 4. Формируем красивый отчет
    return {
        "status": "success",
        "sku": sku,
        "image": product_data['image'],
        "rating": product_data['rating'],
        "ai_analysis": ai_result,
        "reviews_count": product_data['reviews_count']
    }