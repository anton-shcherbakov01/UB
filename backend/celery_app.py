import os
from celery import Celery
from celery.schedules import crontab

# Используем Redis как брокер и бэкенд результатов
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "wb_parser_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    # ВАЖНО: Указываем, где искать задачи (@task)
    include=['tasks']
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    worker_max_tasks_per_child=10, # Перезагрузка воркера для очистки памяти
    # Убираем префетч, чтобы задачи не копились у одного воркера
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Расписание периодических задач (если нужно)
celery_app.conf.beat_schedule = {
    'update-all-prices-every-4-hours': {
        'task': 'update_all_monitored_items',
        'schedule': crontab(minute=0, hour='*/4'),
    },
}