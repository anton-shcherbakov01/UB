import logging
from sqlalchemy import text, inspect
from database import engine_sync

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Migration")

def run_migration():
    logger.info("Starting migration check...")
    inspector = inspect(engine_sync)
    
    with engine_sync.connect() as connection:
        trans = connection.begin()
        try:
            # 1. Таблица для себестоимости собственных товаров (Unit Economics)
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

            # 2. Проверяем поля User (на случай если это первый запуск фазы 2)
            if inspector.has_table("users"):
                cols = [c['name'] for c in inspector.get_columns('users')]
                if 'wb_api_token' not in cols:
                    connection.execute(text("ALTER TABLE users ADD COLUMN wb_api_token VARCHAR"))
                if 'last_order_check' not in cols:
                    connection.execute(text("ALTER TABLE users ADD COLUMN last_order_check TIMESTAMP WITHOUT TIME ZONE"))

            trans.commit()
            logger.info("Migration completed successfully.")
        except Exception as e:
            trans.rollback()
            logger.error(f"Migration failed: {e}")
            raise e

if __name__ == "__main__":
    run_migration()