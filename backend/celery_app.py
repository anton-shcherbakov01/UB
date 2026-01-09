import os
from celery import Celery
from celery.schedules import crontab

# Настройки Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Инициализация приложения БЕЗ прямого импорта tasks
celery_app = Celery(
    "wb_parser_worker",
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Конфигурация
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    worker_max_tasks_per_child=50,  # Увеличили до 50 для стабильности
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    # Явно указываем, где искать задачи, чтобы Celery сам их нашел после старта
    imports=['tasks']
)

# Расписание: КАЖДЫЙ ЧАС
celery_app.conf.beat_schedule = {
    'update-all-prices-hourly': {
        'task': 'update_all_monitored_items', # Ссылка по строковому имени
        'schedule': crontab(minute=0, hour='*'),
    },
}