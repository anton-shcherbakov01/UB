import logging
from sqlalchemy import text
from database import engine_sync, Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DB_Migration")

def migrate():
    """
    Миграция v3.1: Исправление структуры BidderConfig.
    Добавляет колонку campaign_name, если её нет.
    """
    logger.info("🚀 Запуск миграции базы данных...")
    
    try:
        # 1. Создаем новые таблицы (если их вообще нет)
        Base.metadata.create_all(bind=engine_sync)
        logger.info("✅ create_all выполнен.")
        
        # 2. Обновляем существующие таблицы (ALTER TABLE)
        with engine_sync.connect() as conn:
            trans = conn.begin()
            try:
                # Добавляем campaign_name в bidder_configs
                try:
                    conn.execute(text("ALTER TABLE bidder_configs ADD COLUMN IF NOT EXISTS campaign_name VARCHAR"))
                    logger.info("✅ bidder_configs: добавлена колонка 'campaign_name'")
                except Exception as e:
                    # Обработка для старых версий PG где нет IF NOT EXISTS в ADD COLUMN
                    if "duplicate column" in str(e).lower():
                        logger.info("ℹ️ Колонка 'campaign_name' уже существует.")
                    else:
                        logger.warning(f"⚠️ Ошибка campaign_name: {e}")

                # Добавляем keyword (на всякий случай, если тоже забыли)
                try:
                    conn.execute(text("ALTER TABLE bidder_configs ADD COLUMN IF NOT EXISTS keyword VARCHAR"))
                    logger.info("✅ bidder_configs: добавлена колонка 'keyword'")
                except Exception as e:
                    if "duplicate column" in str(e).lower(): pass
                    else: logger.warning(f"⚠️ Ошибка keyword: {e}")

                trans.commit()
            except Exception as e:
                trans.rollback()
                logger.error(f"Error executing ALTER statements: {e}")

    except Exception as e:
        logger.error(f"❌ Критическая ошибка миграции: {e}")

    logger.info("🎉 Миграция завершена!")

if __name__ == "__main__":
    migrate()