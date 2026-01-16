import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Обновляем include, указывая новые модули
celery_app = Celery(
    "juicystat_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        'tasks.monitoring',
        'tasks.seo',
        'tasks.finance',
      # В РАЗРАБОТКЕ: 'tasks.bidder',
        'tasks.supply'
    ] 
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=None,
    broker_transport_options={
        "visibility_timeout": 3600,
        "health_check_interval": 10,
        "socket_timeout": 15,
        "socket_connect_timeout": 15,
        "socket_keepalive": True,
    },
    worker_prefetch_multiplier=1, 
    task_acks_late=True,
    beat_schedule={
        "update-monitored-items-hourly": {
            "task": "update_all_monitored_items",
            "schedule": crontab(minute=0), 
        },
        "check-new-orders-every-10m": {
            "task": "check_new_orders",
            "schedule": 600.0, 
        },
        # В РАЗРАБОТКЕ:
        # "bidder-producer-every-5m": {
        #     "task": "bidder_producer_task",
        #     "schedule": 300.0,
        # },
        "train-forecasts-daily": {
            "task": "train_forecasting_models",
            "schedule": crontab(hour=3, minute=0),
        }
    }
)