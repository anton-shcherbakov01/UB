import logging
from sqlalchemy import text, inspect
from database import engine_sync

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Migration")

def run_migration():
    """
    Безопасное добавление колонок для Фазы 2.
    Работает через синхронный движок SQLAlchemy.
    """
    logger.info("Starting migration check...")
    
    inspector = inspect(engine_sync)
    
    if not inspector.has_table("users"):
        logger.info("Table 'users' does not exist yet. Init DB will handle it.")
        return

    with engine_sync.connect() as connection:
        trans = connection.begin()
        try:
            # 1. Проверяем и добавляем wb_api_token (если не добавили на прошлом шаге)
            columns_users = [c['name'] for c in inspector.get_columns('users')]
            if 'wb_api_token' not in columns_users:
                logger.info("Adding 'wb_api_token' to users...")
                connection.execute(text("ALTER TABLE users ADD COLUMN wb_api_token VARCHAR"))

            # 2. Добавляем last_order_check в users (для уведомлений)
            if 'last_order_check' not in columns_users:
                logger.info("Adding 'last_order_check' to users...")
                connection.execute(text("ALTER TABLE users ADD COLUMN last_order_check TIMESTAMP WITHOUT TIME ZONE"))

            # 3. Добавляем cost_price в monitored_items (для Unit-экономики)
            columns_items = [c['name'] for c in inspector.get_columns('monitored_items')]
            if 'cost_price' not in columns_items:
                logger.info("Adding 'cost_price' to monitored_items...")
                connection.execute(text("ALTER TABLE monitored_items ADD COLUMN cost_price INTEGER DEFAULT 0"))

            trans.commit()
            logger.info("Migration completed successfully.")
        except Exception as e:
            trans.rollback()
            logger.error(f"Migration failed: {e}")
            raise e

if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        logger.error(f"Fatal migration error: {e}")