import os
import logging
from celery import Celery
from celery.schedules import crontab

# Настройка логирования для конфигурации
logger = logging.getLogger("CeleryConfig")

# Получение URL Redis из переменных окружения
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Инициализация приложения Celery
# Имя 'wb_tasks' используется для идентификации в системе мониторинга (например, Flower)
celery_app = Celery(
    "wb_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        'tasks.monitoring',  # Проверка заказов, выкупов и сводки
        'tasks.seo',         # Мониторинг позиций и генерация текстов
        'tasks.finance',     # Синхронизация финансовых отчетов
        'tasks.supply',      # Планирование поставок и анализ остатков
        # 'tasks.bidder',    # Зарезервировано для модуля управления ставками
    ] 
)

# Детальная конфигурация параметров Celery
celery_app.conf.update(
    # Явное указание result backend (Redis)
    result_backend=REDIS_URL,
    result_expires=3600,  # Результаты хранятся 1 час
    
    # Настройки сериализации данных
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # Локализация времени (важно для корректной работы crontab)
    timezone="Europe/Moscow",
    enable_utc=True,
    
    # Настройки надежности соединения с брокером
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=None,  # Бесконечные попытки переподключения
    
    # Оптимизация транспорта для работы в Docker-сетях
    broker_transport_options={
        "visibility_timeout": 3600,      # Час на выполнение задачи перед возвратом в очередь
        "health_check_interval": 10,
        "socket_timeout": 15,
        "socket_connect_timeout": 15,
        "socket_keepalive": True,
    },
    
    # Настройки производительности воркеров
    worker_prefetch_multiplier=1,        # Воркер берет только одну задачу за раз (для тяжелых задач)
    task_acks_late=True,                 # Подтверждение после выполнения (защита от падения воркера)
    task_reject_on_worker_lost=True,     # Возврат в очередь, если воркер "упал"
    
    # Настройки очередей с приоритетами
    task_routes={
        'tasks.seo.analyze_reviews_task': {'queue': 'normal'},  # Будет перенаправлено в priority/normal через queue_service
    },
    task_default_queue='normal',
    task_default_exchange='tasks',
    task_default_routing_key='normal',
    
    # Таймауты для тяжелых задач (в секундах)
    # soft_time_limit - мягкий таймаут (задача может обработать SoftTimeLimitExceeded)
    # time_limit - жесткий таймаут (задача убивается принудительно)
    task_time_limit=600,          # 10 минут жесткий таймаут по умолчанию
    task_soft_time_limit=300,     # 5 минут мягкий таймаут по умолчанию
    
    # Специфичные таймауты для тяжелых задач
    task_annotations={
        'tasks.seo.analyze_reviews_task': {
            'time_limit': 600,      # 10 минут для AI анализа (парсинг + AI)
            'soft_time_limit': 480, # 8 минут мягкий таймаут
        },
        'tasks.seo.check_seo_position_task': {
            'time_limit': 300,      # 5 минут для проверки позиций (Selenium)
            'soft_time_limit': 240, # 4 минуты
        },
        'tasks.monitoring.parse_and_save_sku': {
            'time_limit': 300,      # 5 минут для парсинга Selenium
            'soft_time_limit': 240,
        },
        'tasks.finance.sync_financial_reports': {
            'time_limit': 600,      # 10 минут для синхронизации финансов
            'soft_time_limit': 480,
        },
    },
    
    # --- РАСПИСАНИЕ ПЕРИОДИЧЕСКИХ ЗАДАЧ (CELERY BEAT) ---
    beat_schedule={
        # 1. Мгновенные уведомления о заказах и выкупах
        # Проверка каждые 10 минут. Логика дедупликации внутри задачи исключает спам.
        "check-new-orders-every-10m": {
            "task": "check_new_orders",
            "schedule": crontab(minute="*/10"), 
        },

        # 2. Часовая сводка (Аналитика продаж и воронка в Telegram)
        # Отправляется ровно в 00 минут каждого часа (например, 10:00, 11:00)
        "send-hourly-summary": {
            "task": "send_hourly_summary",
            "schedule": crontab(minute=0), 
        },

        # 3. Мониторинг позиций и цен конкурентов
        # Запуск на 15-й минуте часа, чтобы не конфликтовать по ресурсам со сводкой
        "update-monitored-items-hourly": {
            "task": "update_all_monitored_items",
            "schedule": crontab(minute=15), 
        },
        
        # 4. Синхронизация данных о поставках и свободных слотах
        # Выполняется раз в сутки в 6 утра (перед началом рабочего дня)
        "sync-supply-daily": {
            "task": "sync_supply_data",
            "schedule": crontab(hour=6, minute=0),
        },

        # 5. Обучение и обновление AI моделей прогнозирования
        # Ресурсоемкая задача, выполняется глубокой ночью в 3:30
        "train-forecasts-daily": {
            "task": "train_forecasting_models",
            "schedule": crontab(hour=3, minute=30),
        },
        
        "check-prices-fast": {
            "task": "check_price_alerts",
            "schedule": crontab(minute="*/15"), # Каждые 15 минут
        }
    }
)

if __name__ == "__main__":
    logger.info("Celery application configuration loaded.")