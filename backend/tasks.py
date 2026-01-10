import asyncio
import json
import logging
from datetime import datetime
from sqlalchemy import select, update
from celery import Celery
from database import AsyncSessionLocal, MonitoredItem, PriceHistory, SearchHistory, SeoPosition
from parser_service import parser_service
from analysis_service import analysis_service
from celery_app import celery_app
from wb_api_service import wb_api_service
from bot_service import bot_service
from database import SyncSessionLocal, User

logger = logging.getLogger("CeleryTasks")

# --- HELPER FOR ASYNC DB ---
def run_async(coro):
    loop = asyncio.get_event_loop()
    if loop.is_running():
        return loop.create_task(coro)
    else:
        return loop.run_until_complete(coro)

async def save_search_history(user_id: int, sku: int, title: str, r_type: str, data: dict):
    # [FIX] Используем AsyncSessionLocal вместо SessionLocal
    async with AsyncSessionLocal() as db:
        try:
            # Ограничиваем размер JSON, чтобы не забивать БД
            json_str = json.dumps(data, ensure_ascii=False)
            item = SearchHistory(
                user_id=user_id,
                sku=sku,
                title=title[:100],
                request_type=r_type,
                result_json=json_str
            )
            db.add(item)
            await db.commit()
        except Exception as e:
            logger.error(f"History save error: {e}")

@celery_app.task
def parse_and_save_sku(sku: int, user_id: int):
    """Фоновая задача парсинга товара"""
    logger.info(f"Task: Parsing SKU {sku} for user {user_id}")
    
    # 1. Парсинг
    data = parser_service.get_product_data(sku)
    
    # 2. Сохранение в БД (синхронная обертка для Celery)
    async def _save():
        # [FIX] AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            # Обновляем имя товара
            stmt = select(MonitoredItem).where(MonitoredItem.sku == sku, MonitoredItem.user_id == user_id)
            item = (await db.execute(stmt)).scalars().first()
            if item and data.get('status') == 'success':
                item.name = data.get('name')
                item.brand = data.get('brand')
                db.add(item)
            
            # Пишем историю цены
            if data.get('status') == 'success':
                prices = data.get('prices', {})
                ph = PriceHistory(
                    item_id=item.id if item else 0, # Если товар удалили пока шла задача
                    wallet_price=prices.get('wallet_purple', 0),
                    standard_price=prices.get('standard_black', 0),
                    base_price=prices.get('base_crossed', 0)
                )
                db.add(ph)
                await db.commit()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_save())
    loop.close()
    
    return data

@celery_app.task
def analyze_reviews_task(sku: int, limit: int, user_id: int):
    """Анализ отзывов с AI"""
    logger.info(f"Task: Analyzing reviews for {sku}")
    
    # 1. Парсим отзывы
    product_info = parser_service.get_full_product_info(sku, limit)
    
    if product_info.get("status") == "error":
        return {"status": "error", "error": product_info.get("message")}
    
    reviews = product_info.get("reviews", [])
    if not reviews:
        return {"status": "error", "error": "Нет отзывов для анализа"}

    # 2. Анализируем через AI
    ai_result = analysis_service.analyze_reviews_with_ai(reviews, f"Товар {sku}")
    
    final_data = {
        "sku": sku,
        "rating": product_info.get("rating"),
        "reviews_count": product_info.get("reviews_count"),
        "image": product_info.get("image"),
        "ai_analysis": ai_result
    }

    # 3. Сохраняем в историю
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(save_search_history(user_id, sku, f"Анализ отзывов {sku}", "ai", final_data))
    loop.close()

    return final_data

@celery_app.task
def generate_seo_task(keywords: list, tone: str, sku: int, user_id: int, title_len: int = 100, desc_len: int = 1000):
    """
    Генерация SEO описания. 
    Принимает параметры длины текста.
    """
    logger.info(f"Task: SEO Gen for {sku}")
    
    # Генерация
    content = analysis_service.generate_product_content(keywords, tone, title_len, desc_len)
    
    result = {
        "sku": sku,
        "keywords": keywords,
        "generated_content": content
    }

    # Сохранение
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(save_search_history(user_id, sku, f"SEO Генерация {sku}", "seo", result))
    loop.close()

    return result

@celery_app.task
def check_seo_position_task(sku: int, query: str, user_id: int):
    """Проверка позиций (SERP)"""
    logger.info(f"Task: SERP check {sku} for '{query}'")
    
    pos = parser_service.get_search_position(query, sku)
    
    async def _save_pos():
        async with AsyncSessionLocal() as db:
            seo_rec = SeoPosition(
                user_id=user_id,
                sku=sku,
                keyword=query,
                position=pos,
                last_check=datetime.now()
            )
            db.add(seo_rec)
            await db.commit()
            
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_save_pos())
    loop.close()
    
    return {"position": pos}

@celery_app.task(name="update_all_monitored_items")
def update_all_monitored_items():
    session = SyncSessionLocal()
    try:
        skus = [i.sku for i in session.query(MonitoredItem).all()]
        logger.info(f"Beat: Starting update for {len(skus)} items")
        # Здесь логика запуска задач для каждого товара
        # Для упрощения пока оставим pass или можно итерироваться
        pass
    finally:
        session.close()

# --- NOTIFICATIONS ("ДЗЫНЬ!") ---

async def _process_orders_async():
    """Асинхронная логика внутри синхронной задачи Celery"""
    
    # [FIX] AsyncSessionLocal для асинхронной работы с базой
    async with AsyncSessionLocal() as db:
        try:
            # Fetch users with tokens
            result = await db.execute(select(User).where(User.wb_api_token.isnot(None)))
            users = result.scalars().all()
            
            for user in users:
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
                        
                        # Update last check
                        user.last_order_check = datetime.now()
                        db.add(user)
                        await db.commit()
                        
                except Exception as e:
                    logger.error(f"Error checking orders for user {user.telegram_id}: {e}")
                    
        except Exception as e:
             logger.error(f"Error in process_orders: {e}")

@celery_app.task(name="check_new_orders")
def check_new_orders():
    """Периодическая задача для проверки новых заказов."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_process_orders_async())
    loop.close()