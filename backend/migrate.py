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
    # Читаем флаг из environment. По умолчанию True, но в docker-compose для воркеров ставим False
    run_migrations = os.getenv("RUN_MIGRATIONS", "true").lower() == "true"
    
    logger.info(f"🚀 Старт проверки БД (Режим мигратора: {run_migrations})...")
    
    if not wait_for_db():
        logger.error("❌ Не удалось подключиться к БД. Выход.")
        return

    if not run_migrations:
        logger.info("✋ Я воркер, миграции не запускаю. Просто жду БД. Готов к работе.")
        return

    # Только API (или тот, у кого RUN_MIGRATIONS=true) создает таблицы
    try:
        logger.info("🛠 Создание/проверка таблиц...")
        Base.metadata.create_all(bind=engine_sync)
        logger.info("✅ Структура таблиц проверена/создана.")
    except Exception as e:
        logger.error(f"❌ Ошибка создания таблиц: {e}")
        return

    # Альтеры для существующих таблиц (защищенные try-except)
    try:
        with engine_sync.connect() as conn:
            trans = conn.begin()
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS wb_api_token VARCHAR"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_order_check TIMESTAMP WITHOUT TIME ZONE"))
                trans.commit()
                logger.info("✅ Альтеры колонок применены.")
            except Exception:
                trans.rollback()
                # Игнорируем ошибки "already exists" молча, чтобы не пугать в логах
                pass
    except Exception as e:
         logger.error(f"❌ Ошибка подключения для альтеров: {e}")

    logger.info("🎉 Миграция завершена успешно!")

if __name__ == "__main__":
    migrate()