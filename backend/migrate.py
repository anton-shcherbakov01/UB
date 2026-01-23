import logging
import time
import os
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from database import engine_sync, Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DB_Migration")

def wait_for_db(retries=30, delay=2):
    """Ожидание готовности базы данных к подключениям"""
    logger.info("⏳ Ожидание готовности БД...")
    for i in range(retries):
        try:
            with engine_sync.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("✅ Database is ready.")
            return True
        except OperationalError as e:
            logger.warning(f"⏳ Database not ready yet (Attempt {i+1}/{retries})... Error: {e}")
            time.sleep(delay)
        except Exception as e:
            logger.error(f"❌ Unexpected error connecting to DB: {e}")
            time.sleep(delay)
    return False

def migrate():
    run_migrations = os.getenv("RUN_MIGRATIONS", "true").lower() == "true"
    
    logger.info(f"🚀 Старт проверки БД (Режим мигратора: {run_migrations})...")
    
    if not wait_for_db():
        logger.error("❌ Не удалось подключиться к БД. Выход.")
        return

    if not run_migrations:
        logger.info("✋ Я воркер, миграции не запускаю. Просто жду БД. Готов к работе.")
        return

    # 1. Создание новых таблиц
    try:
        logger.info("🛠 Создание/проверка таблиц...")
        Base.metadata.create_all(bind=engine_sync)
        logger.info("✅ Структура таблиц проверена/создана.")
    except Exception as e:
        logger.error(f"❌ Ошибка создания таблиц: {e}")
        return

    # 2. Миграция колонок (ALTER TABLE)
    # Это добавит недостающие колонки в существующие таблицы
    try:
        with engine_sync.connect() as conn:
            trans = conn.begin()
            try:
                # --- Users ---
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS wb_api_token VARCHAR"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_order_check TIMESTAMP WITHOUT TIME ZONE"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS referrer_id BIGINT"))
                
                # --- Slot Monitors (ВАЖНОЕ ИСПРАВЛЕНИЕ) ---
                logger.info("📦 Обновление таблицы slot_monitors...")
                conn.execute(text("ALTER TABLE slot_monitors ADD COLUMN IF NOT EXISTS box_type_id INTEGER DEFAULT 1"))
                conn.execute(text("ALTER TABLE slot_monitors ADD COLUMN IF NOT EXISTS date_from TIMESTAMP WITHOUT TIME ZONE"))
                conn.execute(text("ALTER TABLE slot_monitors ADD COLUMN IF NOT EXISTS date_to TIMESTAMP WITHOUT TIME ZONE"))
                conn.execute(text("ALTER TABLE slot_monitors ADD COLUMN IF NOT EXISTS target_coefficient INTEGER DEFAULT 0"))
                conn.execute(text("ALTER TABLE slot_monitors ADD COLUMN IF NOT EXISTS auto_book BOOLEAN DEFAULT FALSE"))
                conn.execute(text("ALTER TABLE slot_monitors ADD COLUMN IF NOT EXISTS preorder_id BIGINT"))
                conn.execute(text("ALTER TABLE slot_monitors ADD COLUMN IF NOT EXISTS supply_id VARCHAR"))
                
                # Удаляем старую колонку box_type, если она мешает (опционально, но лучше оставить для совместимости или удалить позже)
                # conn.execute(text("ALTER TABLE slot_monitors DROP COLUMN IF EXISTS box_type"))

                trans.commit()
                logger.info("✅ Альтеры колонок успешно применены.")
            except Exception as e:
                trans.rollback()
                logger.error(f"⚠️ Ошибка при обновлении колонок (возможно, они уже есть): {e}")
                pass
    except Exception as e:
         logger.error(f"❌ Ошибка подключения для альтеров: {e}")

    logger.info("🎉 Миграция завершена успешно!")

if __name__ == "__main__":
    migrate()