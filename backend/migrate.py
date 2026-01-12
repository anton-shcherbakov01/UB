import logging
import time
import os
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from database import engine_sync, Base

# Настройка логирования
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
    """
    Скрипт миграции.
    Если RUN_MIGRATIONS=true (по умолчанию), создает таблицы.
    Если RUN_MIGRATIONS=false, только ждет подключения к БД.
    """
    # Читаем переменную окружения (по умолчанию true)
    run_migrations = os.getenv("RUN_MIGRATIONS", "true").lower() == "true"
    
    logger.info(f"🚀 Старт скрипта инициализации (Создание таблиц: {run_migrations})...")
    
    if not wait_for_db():
        logger.error("❌ Не удалось подключиться к БД. Выход.")
        return

    if not run_migrations:
        logger.info("✋ Пропуск создания таблиц (RUN_MIGRATIONS=false). Сервис готов к работе.")
        return

    # 1. Создаем новые таблицы (ТОЛЬКО ЕСЛИ RUN_MIGRATIONS=true)
    try:
        logger.info("🛠 Создание/проверка таблиц...")
        Base.metadata.create_all(bind=engine_sync)
        logger.info("✅ Структура таблиц проверена/создана.")
    except Exception as e:
        logger.error(f"❌ Ошибка создания таблиц: {e}")
        return

    # 2. Обновляем существующую таблицу users (если нужно)
    try:
        with engine_sync.connect() as conn:
            trans = conn.begin()
            try:
                # Добавляем wb_api_token
                try:
                    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS wb_api_token VARCHAR"))
                except Exception as e:
                    if "duplicate column" not in str(e) and "already exists" not in str(e):
                        logger.warning(f"⚠️ Warning wb_api_token: {e}")

                # Добавляем last_order_check
                try:
                    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_order_check TIMESTAMP WITHOUT TIME ZONE"))
                except Exception as e:
                    if "duplicate column" not in str(e) and "already exists" not in str(e):
                        logger.warning(f"⚠️ Warning last_order_check: {e}")
                
                trans.commit()
                logger.info("✅ Альтеры колонок применены.")
                
            except Exception as e:
                trans.rollback()
                logger.error(f"❌ Ошибка при изменении колонок: {e}")
    except Exception as e:
         logger.error(f"❌ Ошибка подключения для альтеров: {e}")

    logger.info("🎉 Миграция завершена успешно!")

if __name__ == "__main__":
    migrate()