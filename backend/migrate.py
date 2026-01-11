import logging
from sqlalchemy import text
from database import engine_sync, Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DB_Migration")

def migrate():
    """
    Миграция v4.0 (Unit Economics 2025).
    """
    logger.info("🚀 Запуск миграции...")
    
    try:
        # 1. Создаем таблицы если нет
        Base.metadata.create_all(bind=engine_sync)
        
        # 2. Обновляем ProductCost для поддержки EBITDA и P&L
        with engine_sync.connect() as conn:
            trans = conn.begin()
            try:
                # fixed_costs (для EBITDA)
                try:
                    conn.execute(text("ALTER TABLE product_costs ADD COLUMN IF NOT EXISTS fixed_costs FLOAT DEFAULT 0"))
                    logger.info("✅ product_costs: +fixed_costs")
                except Exception as e:
                    if "duplicate" not in str(e).lower(): logger.warning(f"Error: {e}")

                # external_marketing (для CM3)
                try:
                    conn.execute(text("ALTER TABLE product_costs ADD COLUMN IF NOT EXISTS external_marketing FLOAT DEFAULT 0"))
                    logger.info("✅ product_costs: +external_marketing")
                except Exception as e:
                    if "duplicate" not in str(e).lower(): logger.warning(f"Error: {e}")

                # fulfillment_cost (для CM2)
                try:
                    conn.execute(text("ALTER TABLE product_costs ADD COLUMN IF NOT EXISTS fulfillment_cost FLOAT DEFAULT 0"))
                    logger.info("✅ product_costs: +fulfillment_cost")
                except Exception as e:
                    if "duplicate" not in str(e).lower(): logger.warning(f"Error: {e}")

                # Campaign Name для биддера (на всякий случай)
                try:
                    conn.execute(text("ALTER TABLE bidder_configs ADD COLUMN IF NOT EXISTS campaign_name VARCHAR"))
                except: pass

                trans.commit()
            except Exception as e:
                trans.rollback()
                logger.error(f"Migration error: {e}")

    except Exception as e:
        logger.error(f"Critical error: {e}")

    logger.info("🎉 Готово!")

if __name__ == "__main__":
    migrate()