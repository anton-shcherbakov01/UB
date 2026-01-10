import os
from celery import Celery

# Получаем URL из окружения (по умолчанию локальный Docker)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# FIX: Используем include=['tasks'] для прямой загрузки задач
celery_app = Celery(
    "wb_bot_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['tasks'] 
)

celery_app.conf.update(
    # --- Основные настройки ---
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,

    # --- FIX: Устойчивость к падениям Redis ---
    
    # 1. Разрешить ретрай подключения при старте
    broker_connection_retry_on_startup=True,
    
    # 2. Бесконечные попытки переподключения
    broker_connection_max_retries=None,

    # 3. Настройки транспорта Redis (Healthchecks)
    broker_transport_options={
        "visibility_timeout": 3600,  # 1 час на задачу
        "health_check_interval": 10, # Проверять пульс Redis каждые 10 сек
        "socket_timeout": 15,        # Таймаут операций
        "socket_connect_timeout": 15,
        "socket_keepalive": True,
    },

    # --- Оптимизация исполнения задач ---
    # Брать по 1 задаче за раз (важно для долгих задач парсинга)
    worker_prefetch_multiplier=1, 
    # Подтверждать выполнение ТОЛЬКО после завершения
    task_acks_late=True, 
)