import logging
from sqlalchemy import text
from database import engine_sync, Base

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DB_Migration")

def migrate():
    """
    Скрипт миграции базы данных для обновления v2.1 (Unit-экономика).
    Добавляет поля для детального расчета P&L в таблицу product_costs.
    """
    logger.info("🚀 Запуск миграции базы данных...")
    
    # 1. Создаем новые таблицы (если вы запускаете проект с нуля)
    try:
        Base.metadata.create_all(bind=engine_sync)
        logger.info("✅ Структура таблиц проверена (create_all).")
    except Exception as e:
        logger.error(f"❌ Ошибка проверки/создания таблиц: {e}")

    # 2. Обновляем существующие таблицы (ALTER TABLE)
    # Используем сырой SQL, так как это надежнее для простых миграций без Alembic
    with engine_sync.connect() as conn:
        trans = conn.begin()
        try:
            # --- USERS (из предыдущих версий) ---
            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS wb_api_token VARCHAR"))
            except Exception: pass

            try:
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_order_check TIMESTAMP"))
            except Exception: pass

            # --- PRODUCT_COSTS (Новые поля для P&L) ---
            
            # 1. fulfillment_cost (Стоимость упаковки/фулфилмента на единицу)
            try:
                conn.execute(text("ALTER TABLE product_costs ADD COLUMN IF NOT EXISTS fulfillment_cost FLOAT DEFAULT 0"))
                logger.info("✅ product_costs: добавлено поле 'fulfillment_cost'")
            except Exception as e:
                # Ошибки типа "duplicate column" игнорируем, остальные логируем
                if "duplicate column" not in str(e).lower():
                    logger.warning(f"⚠️ Ошибка fulfillment_cost: {e}")

            # 2. external_marketing (Внешняя реклама - бюджет)
            try:
                conn.execute(text("ALTER TABLE product_costs ADD COLUMN IF NOT EXISTS external_marketing FLOAT DEFAULT 0"))
                logger.info("✅ product_costs: добавлено поле 'external_marketing'")
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    logger.warning(f"⚠️ Ошибка external_marketing: {e}")

            # 3. tax_rate (Налоговая ставка, %)
            try:
                conn.execute(text("ALTER TABLE product_costs ADD COLUMN IF NOT EXISTS tax_rate FLOAT DEFAULT 6.0"))
                logger.info("✅ product_costs: добавлено поле 'tax_rate'")
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    logger.warning(f"⚠️ Ошибка tax_rate: {e}")
            
            # 4. cost_price (Конвертация Integer -> Float для точности копеек)
            # В Postgres для смены типа с данными может потребоваться USING
            try:
                conn.execute(text("ALTER TABLE product_costs ALTER COLUMN cost_price TYPE FLOAT USING cost_price::double precision"))
                logger.info("✅ product_costs: тип 'cost_price' обновлен до FLOAT")
            except Exception as e:
                # Часто падает, если уже Float или база не поддерживает (SQLite)
                logger.info(f"ℹ️ Тип 'cost_price' не изменен (возможно, уже Float или не поддерживается драйвером): {e}")

            trans.commit()
            logger.info("💾 Изменения успешно сохранены в БД.")
            
        except Exception as e:
            trans.rollback()
            logger.error(f"❌ Критическая ошибка миграции: {e}")

    logger.info("🎉 Миграция завершена!")

if __name__ == "__main__":
    migrate()