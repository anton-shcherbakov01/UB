import logging
import time
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from database import engine_sync, Base

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DB_Migration")

def wait_for_db(retries=10, delay=2):
    """Ожидание готовности базы данных к подключениям"""
    for i in range(retries):
        try:
            with engine_sync.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("✅ Database is ready.")
            return True
        except OperationalError as e:
            logger.warning(f"⏳ Database not ready yet (Attempt {i+1}/{retries})...")
            time.sleep(delay)
        except Exception as e:
            logger.error(f"❌ Unexpected error connecting to DB: {e}")
            time.sleep(delay)
    return False

def migrate():
    """
    Скрипт миграции базы данных для обновления v2.0.
    1. Создает новые таблицы (SeoPosition, ProductCost, BidderLog), если их нет.
    2. Добавляет новые колонки в существующую таблицу users.
    """
    logger.info("🚀 Запуск процесса миграции...")
    
    if not wait_for_db():
        logger.error("❌ Не удалось подключиться к БД после нескольких попыток. Миграция отменена.")
        return

    # 1. Создаем новые таблицы
    try:
        # create_all безопасно создает таблицы, если их нет
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
                    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_order_check TIMESTAMP"))
                except Exception as e:
                    if "duplicate column" not in str(e) and "already exists" not in str(e):
                        logger.warning(f"⚠️ Warning last_order_check: {e}")
                
                trans.commit()
                logger.info("✅ Альтеры колонок применены (если требовалось).")
                
            except Exception as e:
                trans.rollback()
                logger.error(f"❌ Ошибка при изменении колонок: {e}")
    except Exception as e:
         logger.error(f"❌ Ошибка подключения для альтеров: {e}")

    logger.info("🎉 Миграция завершена успешно!")

if __name__ == "__main__":
    migrate()