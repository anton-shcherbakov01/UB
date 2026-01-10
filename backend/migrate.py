import logging
from sqlalchemy import text
from database import engine_sync, Base

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DB_Migration")

def migrate():
    """
    Скрипт миграции базы данных для обновления v2.0.
    1. Создает новые таблицы (SeoPosition, ProductCost), если их нет.
    2. Добавляет новые колонки в существующую таблицу users.
    """
    logger.info("🚀 Запуск миграции базы данных...")
    
    # 1. Создаем новые таблицы
    # create_all работает безопасно: создает только то, чего нет
    try:
        Base.metadata.create_all(bind=engine_sync)
        logger.info("✅ Структура новых таблиц проверена/создана.")
    except Exception as e:
        logger.error(f"❌ Ошибка создания таблиц: {e}")

    # 2. Обновляем существующую таблицу users
    with engine_sync.connect() as conn:
        # Транзакция для изменений
        trans = conn.begin()
        try:
            # Добавляем wb_api_token
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS wb_api_token VARCHAR"))
                logger.info("✅ Колонка 'wb_api_token' обработана.")
            except Exception as e:
                # Fallback для старых версий Postgres, где нет IF NOT EXISTS в ALTER COLUMN
                if "duplicate column" in str(e) or "already exists" in str(e):
                    logger.info("ℹ️ Колонка 'wb_api_token' уже существует.")
                else:
                    logger.warning(f"⚠️ Ошибка с 'wb_api_token': {e}")

            # Добавляем last_order_check
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_order_check TIMESTAMP"))
                logger.info("✅ Колонка 'last_order_check' обработана.")
            except Exception as e:
                if "duplicate column" in str(e) or "already exists" in str(e):
                    logger.info("ℹ️ Колонка 'last_order_check' уже существует.")
                else:
                    logger.warning(f"⚠️ Ошибка с 'last_order_check': {e}")
            
            trans.commit()
            logger.info("💾 Изменения сохранены.")
            
        except Exception as e:
            trans.rollback()
            logger.error(f"❌ Критическая ошибка миграции: {e}")

    logger.info("🎉 Миграция завершена успешно!")

if __name__ == "__main__":
    migrate()