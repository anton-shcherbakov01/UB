import asyncio
import logging
from datetime import datetime
from celery import shared_task

from database import SyncSessionLocal, SlotMonitor, User
from services.wb_supply_service import WBSupplyBookingService
from bot_service import bot_service

logger = logging.getLogger("SlotsSniper")

@shared_task(name="sniper_check_slots")
def sniper_check_slots():
    """
    Периодическая задача: проверяет слоты и бронирует/уведомляет.
    """
    session = SyncSessionLocal()
    try:
        # 1. Получаем все активные мониторы с токенами пользователей
        monitors = session.query(SlotMonitor).join(User).filter(
            SlotMonitor.is_active == True,
            User.wb_api_token.isnot(None)
        ).all()

        if not monitors:
            return "No active monitors"

        # 2. Группируем по пользователям (чтобы делать 1 запрос к WB API на юзера)
        user_tasks = {}
        for m in monitors:
            if m.user_id not in user_tasks:
                user_tasks[m.user_id] = []
            user_tasks[m.user_id].append(m)

        # 3. Запуск асинхронного цикла проверки
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(process_users_slots(user_tasks, session))
        finally:
            loop.close()
        
    except Exception as e:
        logger.error(f"Sniper critical error: {e}")
    finally:
        session.close()

async def process_users_slots(user_tasks, session):
    for user_id, monitors in user_tasks.items():
        # Берем первого попавшегося монитора, чтобы достать юзера и токен
        if not monitors: continue
        user = monitors[0].user
        
        # Инициализируем сервис с токеном юзера
        service = WBSupplyBookingService(user.wb_api_token)
        
        # Собираем ID складов для оптимизации запроса (только уникальные)
        wh_ids = list(set([m.warehouse_id for m in monitors]))
        
        try:
            # Получаем слоты для всех интересующих складов одним запросом
            slots_data = await service.get_coefficients_v2(wh_ids)
            if not slots_data: continue
            
            # Проверяем каждый монитор этого пользователя
            for monitor in monitors:
                # Фильтр по ID склада и Типу короба (в API WB они должны совпадать)
                relevant_slots = [
                    s for s in slots_data 
                    if s.get('warehouseID') == monitor.warehouse_id 
                    and s.get('boxTypeID') == monitor.box_type_id
                ]
                
                for slot in relevant_slots:
                    slot_date_str = slot.get('date') # Пример: '2024-01-25T00:00:00Z'
                    coeff = slot.get('coefficient')
                    
                    try:
                        # Парсим дату (обрезаем Z если есть, для простоты)
                        clean_date_str = slot_date_str.replace('Z', '')
                        slot_date = datetime.fromisoformat(clean_date_str)
                    except:
                        continue # Ошибка парсинга даты, пропускаем
                    
                    # --- ПРОВЕРКА УСЛОВИЙ ---
                    
                    # 1. Дата входит в диапазон? (сравниваем date(), чтобы игнорировать время)
                    monitor_from = monitor.date_from.date() if monitor.date_from else datetime.min.date()
                    monitor_to = monitor.date_to.date() if monitor.date_to else datetime.max.date()
                    current_date = slot_date.date()
                    
                    if not (monitor_from <= current_date <= monitor_to):
                        continue
                        
                    # 2. Коэффициент подходит? (меньше или равен целевому, и не закрыт -1)
                    # Если кэф -1 (приемка закрыта), то это нам не подходит
                    if coeff == -1 or coeff > monitor.target_coefficient:
                        continue
                        
                    # --- ДЕЙСТВИЕ ---
                    display_date = slot_date.strftime("%d.%m.%Y")
                    
                    # A. АВТО-БРОНИРОВАНИЕ
                    if monitor.auto_book and monitor.preorder_id:
                        success = await service.book_slot(
                            monitor.preorder_id, 
                            slot_date_str, 
                            coeff, 
                            monitor.warehouse_id
                        )
                        
                        if success:
                            msg = (
                                f"✅ <b>СЛОТ ЗАБРОНИРОВАН!</b>\n"
                                f"📦 Склад: {monitor.warehouse_name}\n"
                                f"📅 Дата: {display_date}\n"
                                f"💰 Кэф: <b>x{coeff}</b>\n"
                                f"🆔 Поставка: {monitor.preorder_id}"
                            )
                            await bot_service.send_message(user.telegram_id, msg)
                            
                            # Отключаем монитор, задача выполнена
                            monitor.is_active = False
                            # ВНИМАНИЕ: session.add - синхронный метод, await не нужен!
                            session.add(monitor)
                            break # Выходим из цикла слотов для этого монитора (поймали!)
                    
                    # B. УВЕДОМЛЕНИЕ (если не авто-бронь или если авто-бронь не сработала/не настроена)
                    else:
                        # Анти-спам: не чаще 1 раза в час для одной задачи
                        last_sent = monitor.last_notified_at
                        if not last_sent or (datetime.utcnow() - last_sent).total_seconds() > 3600:
                            msg = (
                                f"🔔 <b>НАЙДЕН СЛОТ!</b>\n"
                                f"📦 Склад: {monitor.warehouse_name}\n"
                                f"📅 Дата: {display_date}\n"
                                f"💰 Кэф: <b>x{coeff}</b>\n"
                                f"<i>Зайдите на портал, чтобы забронировать!</i>"
                            )
                            await bot_service.send_message(user.telegram_id, msg)
                            
                            monitor.last_notified_at = datetime.utcnow()
                            # ВНИМАНИЕ: session.add - синхронный метод, await не нужен!
                            session.add(monitor)
                            
        except Exception as e:
            logger.error(f"Error processing user {user_id}: {e}")
    
    # ВНИМАНИЕ: session.commit - синхронный метод, await не нужен!
    session.commit()