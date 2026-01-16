import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Инициализация приложения
celery_app = Celery(
    "wb_tasks",  # Имя приложения
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        'tasks.monitoring',
        'tasks.seo',
        'tasks.finance',
        'tasks.supply',
        # 'tasks.bidder', # В разработке
    ] 
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    
    # Настройки надежности соединения
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
    
    # --- РАСПИСАНИЕ ЗАДАЧ (BEAT) ---
    beat_schedule={
        # 1. Мгновенные уведомления (Заказы/Выкупы)
        # Проверяем каждые 10 минут
        "check-new-orders-every-10m": {
            "task": "check_new_orders",
            "schedule": crontab(minute="*/10"), 
        },

        # 2. [НОВОЕ] Часовая сводка (Аналитика в Telegram)
        # Отправляем ровно в начале каждого часа
        "send-hourly-summary": {
            "task": "send_hourly_summary",
            "schedule": crontab(minute=0), 
        },

        # 3. Парсинг позиций и цен конкурентов
        # Ставим на 15-ю минуту каждого часа, чтобы не грузить сервер одновременно со сводкой
        "update-monitored-items-hourly": {
            "task": "update_all_monitored_items",
            "schedule": crontab(minute=15), 
        },
        
        # 4. Синхронизация поставок (Склады)
        # Раз в день утром (например, в 6:00)
        "sync-supply-daily": {
            "task": "sync_supply_data",
            "schedule": crontab(hour=6, minute=0),
        },

        # 5. Обучение AI моделей
        # Глубокой ночью
        "train-forecasts-daily": {
            "task": "train_forecasting_models",
            "schedule": crontab(hour=3, minute=30),
        }
    }
)