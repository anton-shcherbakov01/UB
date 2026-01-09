import os
from celery import Celery
from celery.schedules import crontab

# Настройки Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "wb_parser_worker",
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    worker_max_tasks_per_child=50,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    imports=['tasks']
)

# Расписание
celery_app.conf.beat_schedule = {
    # 1. Обновление цен парсингом - каждый час
    'update-all-prices-hourly': {
        'task': 'update_all_monitored_items',
        'schedule': crontab(minute=0, hour='*'),
    },
    # 2. "Дзынь!" - проверка заказов каждые 15 минут
    'check-new-orders-15min': {
        'task': 'check_new_orders',
        'schedule': crontab(minute='*/15'),
    },
}