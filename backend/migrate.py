import logging
from sqlalchemy import text, inspect
from database import engine_sync, Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DB_Migration")

def migrate():
    """
    Миграция v5.0 (Financial Engine Upgrade).
    
    Changes:
    1. Schema Sync (Create 'cost_history', 'users' update)
    2. Add 'tax_scheme' column to 'users'
    3. Data Migration: 'product_costs' -> 'cost_history'
    """
    logger.info("🚀 Запуск миграции v5.0...")
    
    try:
        # 1. Синхронизация схемы (SQLAlchemy создаст отсутствующие таблицы)
        Base.metadata.create_all(bind=engine_sync)
        logger.info("✅ Schema synchronized (tables created)")

        with engine_sync.connect() as conn:
            trans = conn.begin()
            try:
                inspector = inspect(conn)
                
                # --- 2. Обновление таблицы Users (Tax Scheme) ---
                user_columns = [c['name'] for c in inspector.get_columns('users')]
                
                if 'tax_scheme' not in user_columns:
                    logger.info("⚡ Adding 'tax_scheme' column to users...")
                    
                    # Пытаемся создать ENUM тип, игнорируя ошибку если он уже есть (Postgres specific)
                    try:
                        conn.execute(text("CREATE TYPE taxscheme AS ENUM ('USN_6', 'USN_15', 'OSNO', 'USN_1')"))
                    except Exception as e:
                        logger.info(f"ℹ️ Enum type might already exist or not needed (SQLite/MySQL): {e}")

                    # Добавляем колонку
                    dialect = conn.dialect.name
                    if dialect == 'postgresql':
                        conn.execute(text("ALTER TABLE users ADD COLUMN tax_scheme taxscheme DEFAULT 'USN_6'"))
                    else:
                        conn.execute(text("ALTER TABLE users ADD COLUMN tax_scheme VARCHAR DEFAULT 'USN_6'"))
                        
                    logger.info("✅ Column 'tax_scheme' added.")

                # --- 3. Миграция данных (ProductCost -> CostHistory) ---
                # Если в cost_history пусто, но есть старые данные в product_costs, переносим их.
                
                history_exists = conn.execute(text("SELECT 1 FROM cost_history LIMIT 1")).scalar()
                
                if not history_exists:
                    logger.info("📦 Checking for legacy data to migrate...")
                    
                    pc_columns = [c['name'] for c in inspector.get_columns('product_costs')]
                    
                    if 'cost_price' in pc_columns:
                        # Определяем поля для переноса
                        select_fields = "user_id, sku, cost_price"
                        if 'fulfillment_cost' in pc_columns:
                            select_fields += ", fulfillment_cost"
                        else:
                            select_fields += ", 0.0"
                            
                        # Выбираем старые данные
                        legacy_query = text(f"SELECT {select_fields} FROM product_costs WHERE cost_price > 0")
                        legacy_data = conn.execute(legacy_query).fetchall()
                        
                        if legacy_data:
                            logger.info(f"🔄 Migrating {len(legacy_data)} records to CostHistory...")
                            
                            insert_values = []
                            for row in legacy_data:
                                insert_values.append({
                                    "user_id": row[0],
                                    "sku": row[1],
                                    "cost_price": row[2],
                                    "fulfillment_cost": row[3],
                                    "valid_from": "2024-01-01 00:00:00" # Историческая дата начала для старых данных
                                })
                            
                            stmt = text("""
                                INSERT INTO cost_history (user_id, sku, cost_price, fulfillment_cost, valid_from)
                                VALUES (:user_id, :sku, :cost_price, :fulfillment_cost, :valid_from)
                            """)
                            
                            conn.execute(stmt, insert_values)
                            logger.info("✅ Data migration complete.")
                        else:
                            logger.info("ℹ️ No legacy data found.")
                    else:
                        logger.info("ℹ️ Legacy column 'cost_price' not found, skipping data migration.")
                
                trans.commit()
                logger.info("🎉 Migration v5.0 success!")

            except Exception as e:
                trans.rollback()
                logger.error(f"❌ Migration failed: {e}")
                raise e

    except Exception as e:
        logger.error(f"❌ Critical error: {e}")

if __name__ == "__main__":
    migrate()