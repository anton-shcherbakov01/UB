import logging
from sqlalchemy import text, inspect
from database import engine_sync

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Migration")

def run_migration():
    """
    Безопасное обновление структуры БД.
    1. Создает таблицу product_costs (если нет).
    2. Добавляет колонки в users (wb_api_token, last_order_check).
    """
    logger.info("Starting migration check...")
    
    # Инспектор для проверки текущего состояния БД
    inspector = inspect(engine_sync)
    
    with engine_sync.connect() as connection:
        trans = connection.begin()
        try:
            # 1. Создаем таблицу для себестоимости СОБСТВЕННЫХ товаров
            if not inspector.has_table("product_costs"):
                logger.info("Creating table 'product_costs'...")
                connection.execute(text("""
                    CREATE TABLE product_costs (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        sku BIGINT NOT NULL,
                        cost_price INTEGER DEFAULT 0,
                        updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc')
                    );
                    CREATE INDEX idx_product_costs_user_sku ON product_costs (user_id, sku);
                """))
            else:
                logger.info("Table 'product_costs' already exists.")

            # 2. Проверяем и обновляем таблицу users
            if inspector.has_table("users"):
                existing_columns = [c['name'] for c in inspector.get_columns('users')]
                
                if 'wb_api_token' not in existing_columns:
                    logger.info("Adding 'wb_api_token' to users...")
                    connection.execute(text("ALTER TABLE users ADD COLUMN wb_api_token VARCHAR"))
                
                if 'last_order_check' not in existing_columns:
                    logger.info("Adding 'last_order_check' to users...")
                    connection.execute(text("ALTER TABLE users ADD COLUMN last_order_check TIMESTAMP WITHOUT TIME ZONE"))

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