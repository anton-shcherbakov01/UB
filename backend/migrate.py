import logging
from sqlalchemy import text, inspect
from database import engine_sync

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Migration")

def run_migration():
    """
    Безопасное добавление колонки wb_api_token в таблицу users.
    Работает через синхронный движок SQLAlchemy.
    """
    logger.info("Starting migration check...")
    
    # 1. Создаем инспектор для проверки структуры БД
    inspector = inspect(engine_sync)
    
    # Проверяем, существует ли таблица users
    if not inspector.has_table("users"):
        logger.info("Table 'users' does not exist yet. Using init_db() logic instead.")
        return

    # 2. Получаем список колонок
    columns = [c['name'] for c in inspector.get_columns('users')]
    
    # 3. Проверяем наличие целевой колонки
    if 'wb_api_token' in columns:
        logger.info("Column 'wb_api_token' already exists. No migration needed.")
        return

    # 4. Если колонки нет, добавляем её через сырой SQL
    logger.info("Column 'wb_api_token' missing. Applying ALTER TABLE...")
    
    with engine_sync.connect() as connection:
        # Начинаем транзакцию
        trans = connection.begin()
        try:
            connection.execute(text("ALTER TABLE users ADD COLUMN wb_api_token VARCHAR"))
            trans.commit()
            logger.info("Successfully added 'wb_api_token' column to 'users' table.")
        except Exception as e:
            trans.rollback()
            logger.error(f"Migration failed: {e}")
            raise e

if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        logger.error(f"Fatal migration error: {e}")