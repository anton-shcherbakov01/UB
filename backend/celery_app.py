import os
from celery import Celery

# Подключение к Redis (нужен для хранения очереди)
# Если запускаем через Docker Compose, хост будет 'redis'
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
    # Ограничиваем количество задач на одного воркера, чтобы Selenium не тек по памяти
    worker_max_tasks_per_child=10,
)