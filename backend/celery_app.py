import os
import logging
from celery import Celery
from celery.schedules import crontab

# Настройка логирования для конфигурации
logger = logging.getLogger("CeleryConfig")

# Получение URL Redis из переменных окружения
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Инициализация приложения Celery
celery_app = Celery(
    "wb_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        'tasks.monitoring',    
        'tasks.seo',           
        'tasks.finance',       
        'tasks.supply',        
        'tasks.price_control', # Оставляем импорт файла, чтобы не ломался код
    ] 
)

# Детальная конфигурация параметров Celery
celery_app.conf.update(
    result_backend=REDIS_URL,
    result_expires=3600,
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
    task_reject_on_worker_lost=True,
    task_routes={
        'tasks.seo.analyze_reviews_task': {'queue': 'normal'},
    },
    task_default_queue='normal',
    task_default_exchange='tasks',
    task_default_routing_key='normal',
    task_time_limit=600,
    task_soft_time_limit=300,
    task_annotations={
        'tasks.seo.analyze_reviews_task': {
            'time_limit': 600,
            'soft_time_limit': 480,
        },
        'tasks.seo.check_seo_position_task': {
            'time_limit': 300,
            'soft_time_limit': 240,
        },
        'tasks.monitoring.parse_and_save_sku': {
            'time_limit': 300,
            'soft_time_limit': 240,
        },
        'tasks.finance.sync_financial_reports': {
            'time_limit': 600,
            'soft_time_limit': 480,
        },
    },
    
    # --- РАСПИСАНИЕ ПЕРИОДИЧЕСКИХ ЗАДАЧ (CELERY BEAT) ---
    beat_schedule={
        # 1. Мгновенные уведомления о заказах и выкупах (каждые 10 мин)
        "check-new-orders-every-10m": {
            "task": "check_new_orders",
            "schedule": crontab(minute="*/10"), 
        },

        # 2. Часовая сводка (в начале каждого часа)
        "send-hourly-summary": {
            "task": "send_hourly_summary",
            "schedule": crontab(minute=0), 
        },

        # 3. Мониторинг цен конкурентов (15-я минута часа)
        "update-monitored-items-hourly": {
            "task": "update_all_monitored_items",
            "schedule": crontab(minute=15), 
        },
        
        # 4. ОТКЛЮЧЕНО: Контроль СВОИХ цен
        # "check-prices-fast": {
        #    "task": "check_price_alerts",
        #    "schedule": crontab(minute="*/15"),
        # },

        # 5. Синхронизация данных о поставках (раз в сутки в 6 утра)
        "sync-supply-daily": {
            "task": "sync_supply_data",
            "schedule": crontab(hour=6, minute=0),
        },

        # 6. Обучение AI моделей (раз в сутки ночью)
        "train-forecasts-daily": {
            "task": "train_forecasting_models",
            "schedule": crontab(hour=3, minute=30),
        }
    }
)

if __name__ == "__main__":
    logger.info("Celery application configuration loaded.")