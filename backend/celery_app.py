import os
from celery import Celery
from celery.schedules import crontab

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
    worker_max_tasks_per_child=5, # Перезагрузка воркера почаще для очистки памяти Selenium
)

# Расписание задач (BEAT)
celery_app.conf.beat_schedule = {
    # Запускать обновление всех товаров каждые 4 часа
    'update-all-prices-every-4-hours': {
        'task': 'update_all_monitored_items',
        'schedule': crontab(minute=0, hour='*/4'),
    },
}