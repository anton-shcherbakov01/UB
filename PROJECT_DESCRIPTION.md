# Полное описание проекта UB (WB Analytics Platform)

## Общая информация

**UB (WB Analytics Platform)** — это полнофункциональная платформа для анализа и мониторинга товаров маркетплейса Wildberries. Проект представляет собой современное веб-приложение с микросервисной архитектурой, состоящее из:

- **Backend** на Python (FastAPI) с асинхронной архитектурой
- **Frontend** на React для Telegram Web App
- **База данных** PostgreSQL для хранения пользователей, товаров и истории цен
- **Очередь задач** Celery с Redis для асинхронной обработки
- **AI-аналитика** на основе анализа отзывов через внешний AI API

Проект использует Selenium WebDriver для парсинга данных с Wildberries с обходом блокировок через прокси и ротацию сессий.

---

## Архитектура проекта

### Структура директорий

```
UB/
├── backend/              # Backend сервисы (Python/FastAPI)
│   ├── parser_service.py      # Сервис парсинга Wildberries
│   ├── tasks.py              # Celery задачи
│   ├── analysis_service.py   # Сервис анализа и AI
│   ├── main.py              # FastAPI приложение
│   ├── auth_service.py      # Аутентификация Telegram
│   ├── database.py          # Модели базы данных
│   ├── celery_app.py        # Конфигурация Celery
│   ├── requirements.txt     # Python зависимости
│   ├── Dockerfile          # Docker образ для backend
│   ├── msedgedriver       # Edge WebDriver бинарник
│   └── proxy_ext/         # Расширения браузера для прокси
│
├── frontend/             # Frontend приложение (React)
│   ├── src/
│   │   ├── App.jsx          # Главный компонент приложения
│   │   ├── main.jsx         # Точка входа React
│   │   └── index.css        # Глобальные стили
│   ├── index.html           # HTML шаблон
│   ├── package.json         # NPM зависимости
│   ├── tailwind.config.js   # Конфигурация Tailwind CSS
│   ├── postcss.config.js    # Конфигурация PostCSS
│   └── vercel.json          # Конфигурация Vercel
│
├── docker-compose.yml    # Docker Compose конфигурация
└── package.json         # Корневые зависимости (recharts)
```

---

## Детальное описание файлов

### Backend файлы

---

#### 1. `backend/parser_service.py` — Сервис парсинга Wildberries

**Назначение:** Основной сервис для парсинга данных о товарах с сайта Wildberries с использованием Selenium WebDriver и Microsoft Edge.

**Основной класс:** `SeleniumWBParser`

**Методы:**

##### `__init__(self)`
Инициализация парсера с загрузкой конфигурации из переменных окружения:
- `HEADLESS` — режим браузера (True/False)
- `PROXY_USER` — имя пользователя прокси
- `PROXY_PASS` — пароль прокси
- `PROXY_HOST` — хост прокси-сервера
- `PROXY_PORT` — порт прокси-сервера

##### `_create_proxy_auth_extension(self, user, pw, host, port)`
Создает расширение для браузера Edge для авторизации прокси:
- Генерирует уникальный session ID для каждой сессии (ротация IP)
- Формирует manifest.json и background.js для расширения
- Упаковывает расширение в ZIP архив
- Использует динамическую авторизацию с указанием страны (country-ru)

**Особенности:**
- Ротация сессий через уникальные session ID для обхода блокировок Kaspersky
- Поддержка прокси с HTTP авторизацией

##### `_init_driver(self)`
Инициализация Selenium WebDriver:
- Настройка headless режима
- Добавление аргументов для стабильности: `--no-sandbox`, `--disable-dev-shm-usage`, `--disable-gpu`
- Установка расширения для прокси
- Настройка User-Agent для имитации обычного браузера
- Использование предустановленного msedgedriver из `/usr/local/bin/msedgedriver`
- Таймаут загрузки страницы: 120 секунд

##### `_extract_price(self, driver, selector)`
Извлечение цены из элемента страницы:
- Поиск элементов по CSS селектору
- Извлечение текста через JavaScript (`textContent` или `innerText`)
- Очистка от нечисловых символов регулярным выражением
- Возврат целочисленного значения цены

##### `get_product_data(self, sku: int)`
Основной метод получения данных о товаре:

**Алгоритм работы:**
1. До 2 попыток получения данных
2. Инициализация драйвера с прокси
3. Установка cookie `x-city-id=77` (Москва) для корректного отображения цен
4. Переход на страницу товара с параметрами `targetUrl=GP&dest=-1257786`
5. Ожидание 3 секунды и скролл для загрузки контента
6. Проверка на блокировку Kaspersky (если обнаружена — повторная попытка)
7. Динамическое ожидание загрузки цен (до 60 секунд) с проверкой селектора `[class*='priceBlockFinalPrice']`
8. Извлечение цен:
   - `wallet_purple` — цена с оплатой через WB Кошелек
   - `standard_black` — обычная цена
   - `base_crossed` — базовая цена (зачеркнутая)
9. Fallback метод: если цены не найдены через селекторы, используется JavaScript для глубокого сканирования всех элементов с ценами
10. Извлечение бренда и названия товара

**Возвращаемые данные:**
```python
{
    "id": int,              # Артикул товара
    "name": str,            # Название товара
    "brand": str,           # Бренд
    "prices": {
        "wallet_purple": int,    # Цена с кошельком
        "standard_black": int,   # Обычная цена
        "base_crossed": int      # Базовая цена
    },
    "status": str           # "success" или "error"
}
```

##### `get_full_product_info(self, sku: int, limit: int = 50)`
Парсинг полной информации о товаре, включая отзывы:

**Алгоритм:**
1. Открытие страницы отзывов товара
2. Скролл страницы для загрузки контента (2 прохода)
3. Извлечение:
   - URL изображения товара
   - Общий рейтинг
   - Список отзывов из HTML (до `limit` штук)
4. **Fallback через API** (если HTML пустой):
   - Получение `rootId` (imtId) товара через внутренний API WB
   - Запрос отзывов через `https://feedbacks1.wb.ru/feedbacks/v1/{root_id}`
   - Парсинг JSON ответа и извлечение данных

**Возвращаемые данные:**
```python
{
    "sku": int,
    "image": str,           # URL изображения
    "rating": float,        # Общий рейтинг
    "reviews": [            # Список отзывов
        {
            "text": str,    # Текст отзыва
            "rating": int   # Рейтинг (1-5)
        }
    ],
    "reviews_count": int,
    "status": "success"
}
```

---

#### 2. `backend/tasks.py` — Celery задачи

**Назначение:** Определение асинхронных задач для Celery, которые выполняются в фоновом режиме.

**Зависимости:**
- `celery_app` — экземпляр Celery приложения
- `parser_service` — сервис парсинга
- `analysis_service` — сервис анализа
- `database` — модели и сессии БД

##### `save_price_to_db(sku: int, data: dict)` (async)
Вспомогательная асинхронная функция для сохранения данных о цене в БД:
- Поиск или создание записи `MonitoredItem` по SKU
- Создание записи `PriceHistory` с тремя типами цен
- Коммит изменений в базу данных

##### `parse_and_save_sku` (Celery task)
Задача для парсинга товара и сохранения в БД:

**Статусы задачи:**
- `PROGRESS` — "Запуск браузера..." / "Анализ и сохранение..."
- `SUCCESS` — возврат результата с метриками
- `FAILURE` — возврат ошибки

**Алгоритм:**
1. Обновление статуса задачи
2. Вызов `parser_service.get_product_data(sku)`
3. Если успешно — сохранение в БД через `save_price_to_db`
4. Вызов `analysis_service.calculate_metrics` для расчета метрик
5. Возврат результата

**Примечание:** Использует создание нового event loop для выполнения асинхронных операций, так как Celery задачи синхронные.

##### `update_all_monitored_items` (Celery task)
Периодическая задача для обновления всех товаров в мониторинге:

**Алгоритм:**
1. Получение всех SKU из таблицы `MonitoredItem`
2. Запуск задачи `parse_and_save_sku` для каждого SKU
3. Логирование количества обновляемых товаров

**Использование:** Запускается автоматически через Celery Beat каждые 4 часа (см. `celery_app.py`)

##### `analyze_reviews_task` (Celery task)
Задача для AI-анализа отзывов товара:

**Статусы:**
- `PROGRESS` — "Сбор отзывов с WB..." / "Нейросеть думает..."

**Алгоритм:**
1. Вызов `parser_service.get_full_product_info(sku, limit)` для получения отзывов
2. Если отзывы найдены — вызов `analysis_service.analyze_reviews_with_ai`
3. Возврат результата с анализом

**Возвращаемые данные:**
```python
{
    "status": "success",
    "sku": int,
    "image": str,
    "rating": float,
    "reviews_count": int,
    "ai_analysis": {
        "flaws": [str],      # Список минусов
        "strategy": [str]    # Стратегия победы
    }
}
```

---

#### 3. `backend/analysis_service.py` — Сервис анализа и AI

**Назначение:** Расчет метрик товаров и AI-анализ отзывов.

**Основной класс:** `AnalysisService`

##### `__init__(self)`
Инициализация с загрузкой AI API ключа:
- `AI_API_KEY` — ключ для API искусственного интеллекта
- `AI_URL` — URL API (по умолчанию: `https://api.artemox.com/v1/chat/completions`)

##### `calculate_metrics(raw_data: dict)` (static method)
Расчет метрик на основе данных о ценах:

**Рассчитываемые метрики:**
- `wallet_benefit` — выгода при оплате кошельком (разница между обычной и кошельковой ценой)
- `total_discount_percent` — общий процент скидки: `(base - wallet) / base * 100`
- `is_favorable` — флаг выгодности (true, если скидка > 45%)

**Возвращает:** Обогащенные данные с полем `metrics`

##### `clean_ai_text(self, text: str) -> str`
Очистка текста от форматирования Markdown:
- Удаление `**bold**` синтаксиса
- Удаление заголовков `#`
- Удаление backticks `` ` ``

##### `analyze_reviews_with_ai(self, reviews: list, product_name: str)` (async)
AI-анализ отзывов через внешний API:

**Промпт для AI:**
- Анализ товара по названию
- Отзывы (первые 20) с рейтингами
- Задача: определить 3 главных минуса и 5 советов для конкурента

**Формат ответа (JSON):**
```json
{
    "flaws": ["минус 1", "минус 2", "минус 3"],
    "strategy": ["совет 1", "совет 2", "совет 3", "совет 4", "совет 5"]
}
```

**Алгоритм:**
1. Формирование промпта с отзывами
2. POST запрос к AI API с моделью `deepseek-chat`
3. Парсинг JSON из ответа AI (поиск JSON в тексте через regex)
4. Очистка текста от форматирования
5. Обработка ошибок (формат ответа, сетевая ошибка)

**Параметры запроса:**
- `temperature: 0.5` — баланс между креативностью и точностью

---

#### 4. `backend/main.py` — FastAPI приложение

**Назначение:** Главный файл backend приложения, содержит все API endpoints и бизнес-логику.

**Инициализация:**
- Создание FastAPI приложения с заголовком "WB Analytics Platform"
- Настройка CORS для всех источников
- Инициализация `AuthService` с токеном бота
- Определение `ADMIN_USERNAME = "AAntonShch"` для администраторских прав
- Инициализация БД при старте приложения

##### Зависимости (Dependencies)

###### `get_current_user(x_tg_data: str = Header(None), db: AsyncSession = Depends(get_db))`
Определение текущего пользователя по данным Telegram:

**Алгоритм:**
1. Валидация данных Telegram через `auth_manager.validate_init_data`
2. Парсинг данных пользователя из query string
3. Режим отладки: если `DEBUG_MODE=True`, создается тестовый пользователь
4. Поиск пользователя в БД по `telegram_id`
5. Если пользователь не найден — создание нового:
   - Определение администраторских прав по `username == ADMIN_USERNAME`
   - Установка плана `subscription_plan="free"`
6. Возврат пользователя с жадной загрузкой связанных `items` (selectinload)

**Возвращает:** Объект `User` из БД

##### Пользовательские endpoints

###### `GET /api/user/me`
Получение профиля текущего пользователя:
- Требует аутентификации
- Возвращает: id, username, name, plan, is_admin, items_count

###### `GET /api/user/tariffs`
Получение списка доступных тарифов:
- Требует аутентификации
- Возвращает массив тарифов с их характеристиками:
  - `free` — Старт (3 товара, AI анализ 30 отзывов, история цен)
  - `pro` — PRO Seller (50 товаров, AI анализ 100 отзывов, приоритет, экспорт)

##### Мониторинг endpoints

###### `POST /api/monitor/add/{sku}`
Добавление товара в мониторинг:
- Проверка лимита тарифа (3 для free, 50 для pro)
- Проверка на существование товара у пользователя
- Создание записи `MonitoredItem`
- Запуск задачи `parse_and_save_sku` через Celery
- Возврат `task_id` для отслеживания статуса

###### `GET /api/monitor/list`
Получение списка товаров пользователя:
- Возвращает все `MonitoredItem` пользователя, отсортированные по ID (новые первые)

###### `DELETE /api/monitor/delete/{sku}`
Удаление товара из мониторинга:
- Удаление `MonitoredItem` и всех связанных записей `PriceHistory` (каскадное удаление)

###### `GET /api/monitor/history/{sku}`
Получение истории цен товара:
- Проверка принадлежности товара пользователю
- Возврат истории цен с датами в формате "дд.мм чч:мм"
- Формат: `{"sku": int, "name": str, "history": [{"date": str, "wallet": int}]}`

###### `GET /api/monitor/status/{task_id}`
Получение статуса задачи парсинга:
- Использует `AsyncResult` из Celery
- Возвращает статус: `SUCCESS`, `FAILURE`, `PROGRESS`
- В статусе `PROGRESS` возвращает информацию о текущем этапе

##### AI endpoints

###### `POST /api/ai/analyze/{sku}`
Запуск AI-анализа отзывов:
- Определение лимита отзывов по тарифу (30 для free, 100 для pro)
- Запуск задачи `analyze_reviews_task` через Celery
- Возврат `task_id`

###### `GET /api/ai/result/{task_id}`
Получение результата AI-анализа:
- Использует `AsyncResult` для получения результата задачи
- Возвращает полные данные анализа или ошибку

##### Админ endpoints

###### `GET /api/admin/stats`
Статистика платформы (только для администраторов):
- Проверка `is_admin`
- Возврат: общее количество пользователей, товаров в мониторинге, статус сервера

---

#### 5. `backend/auth_service.py` — Сервис аутентификации

**Назначение:** Валидация данных инициализации Telegram Web App.

**Основной класс:** `AuthService`

##### `__init__(self, bot_token: str)`
Инициализация с токеном Telegram бота.

##### `validate_init_data(self, init_data: str) -> bool`
Валидация подписи данных Telegram Web App:

**Алгоритм (официальный протокол Telegram):**
1. Парсинг query string параметров
2. Извлечение и удаление `hash` из данных
3. Создание строки проверки: `key1=value1\nkey2=value2\n...` (сортировка по ключам)
4. Генерация секретного ключа: `HMAC-SHA256("WebAppData", bot_token)`
5. Вычисление хеша: `HMAC-SHA256(secret_key, check_string)`
6. Сравнение вычисленного хеша с полученным

**Безопасность:** Использует HMAC-SHA256 для защиты от подделки данных

**Возвращает:** `True` если данные валидны, `False` иначе

---

#### 6. `backend/database.py` — Модели базы данных

**Назначение:** Определение моделей SQLAlchemy и настройка подключения к БД.

**Технологии:**
- SQLAlchemy (async) с asyncpg драйвером
- PostgreSQL база данных

##### Конфигурация

**Переменная окружения:** `DATABASE_URL`
- Формат: `postgresql+asyncpg://user:password@host:port/database`
- По умолчанию: `postgresql+asyncpg://wb_user:wb_secret_password@db:5432/wb_monitor`

##### Модели данных

###### `User` — Пользователи
```python
- id: Integer (PK)
- telegram_id: BigInteger (unique, indexed)  # ID в Telegram
- username: String (nullable)
- first_name: String (nullable)
- is_admin: Boolean (default=False)
- subscription_plan: String (default="free")  # free, pro, enterprise
- subscription_end_date: DateTime (nullable)
- created_at: DateTime (default=utcnow)
- items: relationship("MonitoredItem")  # Связанные товары
```

**Связи:**
- `items` — один ко многим с `MonitoredItem` (каскадное удаление)

###### `MonitoredItem` — Отслеживаемые товары
```python
- id: Integer (PK)
- user_id: Integer (FK -> users.id)  # Владелец товара
- sku: Integer (indexed)  # Артикул WB
- name: String (nullable)  # Название товара
- brand: String (nullable)  # Бренд
- created_at: DateTime (default=utcnow)
- owner: relationship("User")  # Обратная связь
- prices: relationship("PriceHistory")  # История цен
```

**Связи:**
- `owner` — многие к одному с `User`
- `prices` — один ко многим с `PriceHistory` (каскадное удаление)

###### `PriceHistory` — История цен
```python
- id: Integer (PK)
- item_id: Integer (FK -> monitored_items.id)
- wallet_price: Integer  # Цена с кошельком
- standard_price: Integer  # Обычная цена
- base_price: Integer  # Базовая цена
- recorded_at: DateTime (default=utcnow)
- item: relationship("MonitoredItem")  # Обратная связь
```

**Связи:**
- `item` — многие к одному с `MonitoredItem`

##### Функции

###### `init_db()` (async)
Инициализация базы данных:
- Создание всех таблиц через `Base.metadata.create_all`
- Выполняется при старте приложения

###### `get_db()` (async generator)
Dependency для получения сессии БД:
- Создает `AsyncSession`
- Yield сессии для использования в endpoints
- Автоматическое закрытие после использования

---

#### 7. `backend/celery_app.py` — Конфигурация Celery

**Назначение:** Настройка Celery для асинхронной обработки задач.

**Технологии:**
- Celery — распределенная очередь задач
- Redis — брокер сообщений и бэкенд результатов

##### Конфигурация

**Переменная окружения:** `REDIS_URL`
- Формат: `redis://host:port/database`
- По умолчанию: `redis://localhost:6379/0`

##### Настройки Celery

**Базовые настройки:**
- `task_serializer`: `"json"` — сериализация задач в JSON
- `accept_content`: `["json"]` — прием только JSON
- `result_serializer`: `"json"` — сериализация результатов
- `timezone`: `"Europe/Moscow"` — часовой пояс
- `enable_utc`: `True` — использование UTC

**Настройки воркера:**
- `worker_max_tasks_per_child: 10` — перезагрузка воркера каждые 10 задач (очистка памяти)
- `task_acks_late: True` — подтверждение задач после выполнения
- `worker_prefetch_multiplier: 1` — без префетча (равномерное распределение задач)

**Включаемые модули:**
- `include=['tasks']` — автоматический импорт задач из модуля `tasks`

##### Периодические задачи (Beat Schedule)

**Задача:** `update-all-prices-every-4-hours`
- **Задача:** `update_all_monitored_items`
- **Расписание:** Каждые 4 часа (`crontab(minute=0, hour='*/4')`)
- **Назначение:** Автоматическое обновление цен всех товаров в мониторинге

---

#### 8. `backend/requirements.txt` — Python зависимости

**Список зависимостей:**

```
fastapi              # Веб-фреймворк для API
uvicorn              # ASGI сервер
selenium             # Автоматизация браузера
webdriver-manager    # Управление драйверами (не используется, драйвер статичный)
python-dotenv        # Загрузка переменных окружения
celery               # Очередь задач
redis                # Клиент Redis
sqlalchemy           # ORM для работы с БД
asyncpg              # Асинхронный драйвер PostgreSQL
psycopg2-binary      # Синхронный драйвер PostgreSQL (для совместимости)
aiohttp              # Асинхронный HTTP клиент (для AI API)
```

---

#### 9. `backend/Dockerfile` — Docker образ для backend

**Назначение:** Создание Docker образа для backend сервиса.

**Базовый образ:** `python:3.9-slim`

**Установка системных зависимостей:**
1. Обновление пакетов и установка утилит: `wget`, `gnupg`, `unzip`, `curl`
2. Установка Microsoft Edge:
   - Добавление ключа Microsoft GPG
   - Добавление репозитория Edge
   - Установка `microsoft-edge-stable`

**Настройка WebDriver:**
- Копирование `msedgedriver` в `/usr/local/bin/msedgedriver`
- Установка прав на выполнение (`chmod +x`)

**Установка Python зависимостей:**
- Копирование `requirements.txt`
- Установка всех зависимостей через `pip`

**Копирование кода:**
- Копирование всех файлов backend в `/app`

**Экспорт порта:** `8000`

**Команда запуска:** `uvicorn main:app --host 0.0.0.0 --port 8000`

---

### Frontend файлы

---

#### 10. `frontend/src/App.jsx` — Главный компонент приложения

**Назначение:** Главный React компонент с полным функционалом приложения.

**Технологии:**
- React 18 с хуками
- Lucide React — иконки
- Recharts — графики

**Константы:**
- `API_URL = "https://api.ulike-bot.ru"` — адрес backend API

##### Вспомогательные компоненты

###### `TabNav` — Нижняя навигация
Компонент нижней панели навигации с 5 вкладками:
- **Главная** (`home`) — иконка `LayoutGrid`
- **Цены** (`monitor`) — иконка `BarChart3`
- **Добавить** (`scanner`) — центральная кнопка-флоатер (круглая с `Plus`)
- **ИИ** (`ai`) — иконка `Brain`
- **Профиль** (`profile`) — иконка `User`

**Особенности:**
- Фиксированная позиция внизу экрана
- Поддержка safe area для устройств с вырезом
- Активное состояние с изменением цвета и толщины иконки
- Центральная кнопка-флоатер с тенью

###### `TariffCard` — Карточка тарифа
Компонент для отображения тарифного плана:
- Заголовок и цена
- Список возможностей (`features`)
- Кнопка перехода (или "Ваш текущий план" если активен)
- Выделение лучшего тарифа (`is_best`) с индикатором "ХИТ"

##### Страницы

###### `HomePage` — Главная страница
Страница приветствия и быстрого доступа:
- Баннер с градиентом (индиго → фиолетовый)
- Описание платформы
- Кнопка "Добавить товар"
- Быстрые действия:
  - Мониторинг — переход к списку товаров
  - AI Аналитик — переход к анализу отзывов

###### `ScannerPage` — Страница добавления товара
Страница для сканирования и добавления товара:
- Поле ввода артикула (SKU)
- Кнопка "Начать отслеживание"
- Polling статуса задачи:
  1. POST запрос на `/api/monitor/add/{sku}`
  2. Получение `task_id`
  3. Polling `/api/monitor/status/{task_id}` каждые 3 секунды
  4. Отображение статуса: "Запуск задачи...", "Парсинг WB...", и т.д.
  5. При успехе — переход на страницу мониторинга
  6. При ошибке — показ алерта
- Обработка ошибки 403 (лимит тарифа)

###### `MonitorPage` — Страница мониторинга
Страница со списком отслеживаемых товаров:
- Загрузка списка через `/api/monitor/list`
- Отображение товаров в виде карточек:
  - Иконка мониторинга
  - Название товара
  - Бренд
  - Кнопка просмотра графика
  - Кнопка удаления
- Модальное окно с графиком истории цен:
  - График на основе библиотеки Recharts (AreaChart)
  - Градиентная заливка
  - Tooltip с ценами
  - Данные загружаются через `/api/monitor/history/{sku}`
- Кнопка обновления списка

###### `AIAnalysisPage` — Страница AI анализа
Страница для запуска анализа отзывов через AI:
- Поле ввода артикула конкурента
- Кнопка "Запустить анализ"
- Polling результата:
  1. POST запрос на `/api/ai/analyze/{sku}`
  2. Получение `task_id`
  3. Polling `/api/ai/result/{task_id}` каждые 4 секунды
  4. Отображение статуса: "Анализ отзывов...", "Нейросеть думает..."
- Отображение результата:
  - Карточка товара с изображением, рейтингом и количеством отзывов
  - Блок "Жалобы клиентов" — список минусов (красный)
  - Блок "Стратегия победы" — список советов (индиго)

###### `ProfilePage` — Страница профиля
Страница профиля пользователя:
- Карточка пользователя с аватаром, именем, username и планом
- Список тарифов через `/api/user/tariffs`
- Отображение всех тарифов через `TariffCard`
- Админ-панель (если `user.is_admin === true`):
  - Кнопка "Открыть статистику"

###### `AdminPage` — Админ-панель
Страница статистики платформы (только для администраторов):
- Загрузка статистики через `/api/admin/stats`
- Отображение метрик:
  - Общее количество пользователей
  - Общее количество товаров в мониторинге
  - Статус сервера

##### Главный компонент `App`

**Состояние:**
- `activeTab` — текущая активная вкладка
- `user` — данные текущего пользователя

**Эффекты:**
- При монтировании: загрузка данных пользователя через `/api/user/me`
- Инициализация Telegram WebApp (если доступен)

**Рендеринг:**
- Условный рендеринг страниц по `activeTab`
- Отображение `TabNav` внизу
- Фон приложения: `#F4F4F9`

---

#### 11. `frontend/src/main.jsx` — Точка входа React

**Назначение:** Инициализация React приложения и монтирование главного компонента.

**Структура:**
- Импорт React и ReactDOM
- Импорт `App` компонента
- Импорт глобальных стилей `index.css`
- Создание root через `ReactDOM.createRoot`
- Рендеринг `App` в `StrictMode`

**StrictMode:** Включает дополнительные проверки React в режиме разработки

---

#### 12. `frontend/index.html` — HTML шаблон

**Назначение:** Основной HTML файл приложения.

**Мета-теги:**
- `charset="UTF-8"` — кодировка
- `viewport` — настройки для мобильных устройств:
  - `maximum-scale=1.0` — запрет масштабирования
  - `user-scalable=no` — отключение зума

**Важные элементы:**
- Подключение Telegram WebApp SDK: `<script src="https://telegram.org/js/telegram-web-app.js"></script>`
  - Без этого скрипта API Telegram не будет работать
- Контейнер `<div id="root">` — точка монтирования React
- Скрипт `<script type="module" src="/src/main.jsx">` — загрузка главного JS модуля

**Заголовок:** "UB Monitor - Анализ WB"

---

#### 13. `frontend/src/index.css` — Глобальные стили

**Назначение:** Глобальные CSS стили и интеграция Tailwind CSS.

**Содержимое:**
- `@tailwind base` — базовые стили Tailwind
- `@tailwind components` — компонентные классы
- `@tailwind utilities` — утилитарные классы

**Кастомные стили:**
- Стилизация `body`:
  - Сброс margin и padding
  - Использование CSS переменных Telegram: `--tg-theme-bg-color`, `--tg-theme-text-color`
  - Отключение подсветки при тапе (`-webkit-tap-highlight-color: transparent`)

**Интеграция с Telegram:** Использует темы Telegram для адаптации под темный/светлый режим

---

#### 14. `frontend/package.json` — NPM зависимости

**Назначение:** Конфигурация Node.js проекта и управление зависимостями.

**Основная информация:**
- `name`: "ub-frontend"
- `version`: "0.1.0"
- `type`: "module" — использование ES модулей

**Скрипты:**
- `dev`: `vite` — запуск dev сервера
- `build`: `vite build` — сборка для продакшена
- `preview`: `vite preview` — предпросмотр production сборки

**Зависимости (dependencies):**
- `react: ^18.2.0` — библиотека React
- `react-dom: ^18.2.0` — React DOM рендерер
- `lucide-react: ^0.284.0` — библиотека иконок
- `recharts: ^2.10.3` — библиотека графиков

**Зависимости для разработки (devDependencies):**
- `@vitejs/plugin-react: ^4.0.0` — плагин Vite для React
- `vite: ^4.3.9` — сборщик и dev сервер
- `autoprefixer: ^10.4.14` — автоматические префиксы CSS
- `postcss: ^8.4.24` — пост-процессор CSS
- `tailwindcss: ^3.3.2` — utility-first CSS фреймворк

---

#### 15. `frontend/tailwind.config.js` — Конфигурация Tailwind CSS

**Назначение:** Настройка Tailwind CSS для проекта.

**Конфигурация:**
- `content` — пути для сканирования классов Tailwind:
  - `./index.html`
  - `./src/**/*.{js,ts,jsx,tsx}`
- `theme.extend` — расширение темы (пустое, используется по умолчанию)
- `plugins` — список плагинов (пусто)

**Важно:** Tailwind работает только с классами, найденными в указанных файлах (tree-shaking)

---

#### 16. `frontend/postcss.config.js` — Конфигурация PostCSS

**Назначение:** Настройка PostCSS для обработки CSS.

**Плагины:**
- `tailwindcss` — обработка Tailwind директив
- `autoprefixer` — автоматическое добавление вендорных префиксов

**Использование:** Vite автоматически использует PostCSS для обработки CSS файлов

---

#### 17. `frontend/vercel.json` — Конфигурация Vercel

**Назначение:** Конфигурация деплоя на Vercel (хостинг фронтенда).

**Настройки:**
- `version: 2` — версия конфигурации Vercel
- `cleanUrls: true` — чистые URLs без расширений
- `rewrites` — правила переписывания URL:
  - Все запросы (`/(.*)`) перенаправляются на `/index.html`
  - Это необходимо для SPA (Single Page Application), чтобы React Router работал корректно

**Примечание:** Vercel используется для хостинга фронтенда, backend разворачивается отдельно

---

### Инфраструктура

---

#### 18. `docker-compose.yml` — Docker Compose конфигурация

**Назначение:** Оркестрация всех сервисов проекта через Docker Compose.

**Версия:** `3.8`

##### Сервисы

###### `redis` — Redis сервер
- **Образ:** `redis:alpine`
- **Контейнер:** `wb_redis`
- **Назначение:** Брокер сообщений и бэкенд результатов для Celery
- **Рестарт:** `always`

###### `db` — PostgreSQL база данных
- **Образ:** `postgres:15-alpine`
- **Контейнер:** `wb_postgres`
- **Переменные окружения:**
  - `POSTGRES_USER: wb_user`
  - `POSTGRES_PASSWORD: wb_secret_password`
  - `POSTGRES_DB: wb_monitor`
- **Volumes:** `postgres_data:/var/lib/postgresql/data` — персистентное хранилище
- **Порты:** `5432:5432`
- **Рестарт:** `always`

###### `api` — FastAPI сервер
- **Билд:** `./backend` (использует Dockerfile)
- **Контейнер:** `wb_api`
- **Команда:** `uvicorn main:app --host 0.0.0.0 --port 8000`
- **Volumes:** `./backend:/app` — монтирование кода для hot-reload
- **Порты:** `8000:8000`
- **Переменные окружения:**
  - `REDIS_URL: redis://redis:6379/0`
  - `DATABASE_URL: postgresql+asyncpg://wb_user:wb_secret_password@db:5432/wb_monitor`
  - `PROXY_USER`, `PROXY_PASS`, `PROXY_HOST`, `PROXY_PORT` — из `.env` файла
  - `HEADLESS: True`
- **Зависимости:** `redis`, `db`

###### `worker` — Celery Worker
- **Билд:** `./backend`
- **Контейнер:** `wb_worker`
- **Команда:** `celery -A celery_app worker --loglevel=warning --concurrency=1`
- **Переменные окружения:** Аналогичны `api` + `C_FORCE_ROOT=1` (убирает предупреждения)
- **Volumes:** `./backend:/app`
- **Зависимости:** `redis`, `db`
- **Примечание:** `--concurrency=1` — один воркер для экономии ресурсов (Selenium тяжелый)

###### `beat` — Celery Beat (планировщик)
- **Билд:** `./backend`
- **Контейнер:** `wb_beat`
- **Команда:** `celery -A celery_app beat --loglevel=info`
- **Переменные окружения:** `REDIS_URL`
- **Volumes:** `./backend:/app`
- **Зависимости:** `redis`
- **Назначение:** Запуск периодических задач по расписанию

##### Volumes

- `postgres_data` — именованный том для хранения данных PostgreSQL

---

#### 19. `package.json` (корневой) — Корневые зависимости

**Назначение:** Зависимости проекта на корневом уровне.

**Содержимое:**
```json
{
  "dependencies": {
    "recharts": "^3.6.0"
  }
}
```

**Примечание:** Вероятно, используется для глобальной установки recharts, но основная конфигурация в `frontend/package.json`

---

## Переменные окружения

Проект использует файл `.env` (не включен в репозиторий) со следующими переменными:

### Backend (.env в директории backend или корне проекта):

```env
# Telegram Bot
BOT_TOKEN=your_telegram_bot_token

# Прокси настройки
PROXY_USER=your_proxy_username
PROXY_PASS=your_proxy_password
PROXY_HOST=your_proxy_host
PROXY_PORT=your_proxy_port

# Режим браузера
HEADLESS=True

# База данных (опционально, есть значения по умолчанию)
DATABASE_URL=postgresql+asyncpg://wb_user:wb_secret_password@db:5432/wb_monitor

# Redis (опционально, есть значения по умолчанию)
REDIS_URL=redis://localhost:6379/0

# AI API
AI_API_KEY=your_ai_api_key

# Режим отладки (опционально)
DEBUG_MODE=False
```

---

## Технологический стек

### Backend:
- **Python 3.9+** — основной язык
- **FastAPI** — современный асинхронный веб-фреймворк
- **Uvicorn** — ASGI сервер
- **SQLAlchemy (async)** — асинхронная ORM
- **PostgreSQL** — реляционная база данных
- **Celery** — распределенная очередь задач
- **Redis** — брокер сообщений и кеш
- **Selenium** — автоматизация браузера
- **Microsoft Edge WebDriver** — драйвер для Edge
- **aiohttp** — асинхронный HTTP клиент
- **python-dotenv** — управление переменными окружения

### Frontend:
- **React 18** — библиотека для создания UI
- **Vite** — сборщик и dev сервер
- **Tailwind CSS** — utility-first CSS фреймворк
- **Lucide React** — библиотека иконок
- **Recharts** — библиотека графиков
- **PostCSS** — пост-процессор CSS
- **Autoprefixer** — автоматические CSS префиксы

### Инфраструктура:
- **Docker** — контейнеризация
- **Docker Compose** — оркестрация контейнеров
- **PostgreSQL** — база данных
- **Redis** — очередь и кеш
- **Vercel** — хостинг фронтенда
- **Telegram Web App** — платформа для запуска приложения

### Интеграции:
- **Telegram Bot API** — аутентификация пользователей
- **Wildberries** — парсинг данных (через Selenium)
- **AI API (artemox.com)** — анализ отзывов через ИИ

---

## Особенности реализации

### Обход блокировок Wildberries:

1. **Ротация прокси сессий:**
   - Каждый запрос использует уникальный session ID
   - Формат: `{user}-session-{random_id};country-ru`
   - Позволяет обходить блокировки Kaspersky

2. **Динамическое ожидание:**
   - Адаптивное ожидание загрузки контента (до 60 секунд)
   - Проверка наличия элементов через селекторы
   - Скролл для инициализации ленивой загрузки

3. **Множественные методы извлечения:**
   - Приоритетные CSS селекторы
   - Fallback через JavaScript глубокое сканирование
   - API fallback для отзывов

4. **Настройки браузера:**
   - Headless режим
   - Подавление признаков автоматизации
   - Реалистичный User-Agent
   - Установка cookie для региона

### Архитектурные решения:

1. **Асинхронная обработка:**
   - Все длительные операции выполняются через Celery
   - Неблокирующие запросы к API
   - Параллельная обработка задач

2. **Масштабируемость:**
   - Микросервисная архитектура
   - Разделение на API, Worker, Beat
   - Горизонтальное масштабирование через Docker

3. **Надежность:**
   - Повторные попытки при ошибках
   - Обработка различных типов ошибок
   - Логирование всех операций
   - Graceful degradation

4. **Безопасность:**
   - Валидация данных Telegram через HMAC
   - CORS настройки
   - Обработка ошибок без утечки информации
   - Проверка прав доступа на уровне endpoints

5. **Многопользовательская архитектура:**
   - Изоляция данных пользователей
   - Лимиты по тарифам
   - Администраторские права

---

## Поток данных в приложении

### Сценарий 1: Добавление товара в мониторинг

```
1. Пользователь вводит артикул в Telegram Web App (ScannerPage)
   ↓
2. POST /api/monitor/add/{sku} с заголовком X-TG-Data
   ↓
3. FastAPI (main.py):
   - get_current_user() валидирует данные Telegram
   - Проверка лимита тарифа
   - Создание MonitoredItem в БД
   - Запуск задачи parse_and_save_sku.delay() через Celery
   ↓
4. Возврат task_id клиенту
   ↓
5. Клиент начинает polling GET /api/monitor/status/{task_id}
   ↓
6. Celery Worker (tasks.py) выполняет задачу:
   - Обновление статуса: "Запуск браузера..."
   - parser_service.get_product_data(sku) — парсинг через Selenium
   - Обновление статуса: "Анализ и сохранение..."
   - save_price_to_db() — сохранение в PostgreSQL
   - analysis_service.calculate_metrics() — расчет метрик
   ↓
7. При SUCCESS клиент получает результат и переходит на MonitorPage
```

### Сценарий 2: AI анализ отзывов

```
1. Пользователь вводит артикул на AIAnalysisPage
   ↓
2. POST /api/ai/analyze/{sku}
   ↓
3. Запуск задачи analyze_reviews_task.delay() через Celery
   ↓
4. Клиент начинает polling GET /api/ai/result/{task_id}
   ↓
5. Celery Worker выполняет:
   - parser_service.get_full_product_info(sku) — парсинг отзывов
     - Открытие страницы отзывов через Selenium
     - Извлечение отзывов из HTML
     - Fallback через API WB если HTML пустой
   - analysis_service.analyze_reviews_with_ai() — AI анализ
     - Формирование промпта с отзывами
     - POST запрос к AI API
     - Парсинг JSON ответа
     - Очистка текста от форматирования
   ↓
6. При SUCCESS клиент получает анализ и отображает результат
```

### Сценарий 3: Автоматическое обновление цен

```
1. Celery Beat запускает задачу по расписанию (каждые 4 часа)
   ↓
2. update_all_monitored_items():
   - Получение всех SKU из MonitoredItem
   - Запуск parse_and_save_sku.delay() для каждого SKU
   ↓
3. Celery Workers обрабатывают задачи параллельно
   ↓
4. Цены обновляются в PriceHistory
```

---

## API Endpoints

### Пользовательские endpoints

#### `GET /api/user/me`
Получение профиля текущего пользователя.

**Требует:** Аутентификация (X-TG-Data)

**Ответ (200 OK):**
```json
{
    "id": 123456789,
    "username": "username",
    "name": "Имя",
    "plan": "free",
    "is_admin": false,
    "items_count": 2
}
```

#### `GET /api/user/tariffs`
Получение списка тарифов.

**Требует:** Аутентификация

**Ответ (200 OK):**
```json
[
    {
        "id": "free",
        "name": "Старт",
        "price": "0 ₽",
        "features": ["3 товара в мониторинге", "AI Анализ (30 отзывов)", "История цен"],
        "current": true,
        "color": "slate"
    },
    {
        "id": "pro",
        "name": "PRO Seller",
        "price": "990 ₽",
        "features": ["50 товаров в мониторинге", "AI Анализ (100 отзывов)", "Приоритетная очередь", "Экспорт отчетов"],
        "current": false,
        "color": "indigo",
        "is_best": true
    }
]
```

### Мониторинг endpoints

#### `POST /api/monitor/add/{sku}`
Добавление товара в мониторинг.

**Требует:** Аутентификация

**Параметры:**
- `sku` (path) — артикул товара

**Ответ (200 OK):**
```json
{
    "status": "accepted",
    "task_id": "abc123-def456-...",
    "message": "Добавлено в очередь"
}
```

**Ошибки:**
- `403 Forbidden` — лимит тарифа исчерпан
- `401 Unauthorized` — не авторизован

#### `GET /api/monitor/list`
Получение списка товаров пользователя.

**Требует:** Аутентификация

**Ответ (200 OK):**
```json
[
    {
        "id": 1,
        "user_id": 1,
        "sku": 12345678,
        "name": "Название товара",
        "brand": "Бренд",
        "created_at": "2024-01-01T12:00:00"
    }
]
```

#### `DELETE /api/monitor/delete/{sku}`
Удаление товара из мониторинга.

**Требует:** Аутентификация

**Ответ (200 OK):**
```json
{
    "status": "deleted"
}
```

#### `GET /api/monitor/history/{sku}`
Получение истории цен товара.

**Требует:** Аутентификация

**Ответ (200 OK):**
```json
{
    "sku": 12345678,
    "name": "Название товара",
    "history": [
        {
            "date": "01.01 12:00",
            "wallet": 1500
        },
        {
            "date": "02.01 12:00",
            "wallet": 1450
        }
    ]
}
```

#### `GET /api/monitor/status/{task_id}`
Получение статуса задачи парсинга.

**Параметры:**
- `task_id` (path) — ID задачи Celery

**Ответ (200 OK):**
```json
{
    "task_id": "abc123-def456-...",
    "status": "SUCCESS",
    "result": {
        "id": 12345678,
        "name": "Товар",
        "brand": "Бренд",
        "prices": {...},
        "metrics": {...}
    }
}
```

**Статусы:**
- `PENDING` — ожидает выполнения
- `PROGRESS` — выполняется (с полем `info`)
- `SUCCESS` — успешно (с полем `result`)
- `FAILURE` — ошибка (с полем `error`)

### AI endpoints

#### `POST /api/ai/analyze/{sku}`
Запуск AI-анализа отзывов.

**Требует:** Аутентификация

**Параметры:**
- `sku` (path) — артикул товара

**Ответ (200 OK):**
```json
{
    "status": "accepted",
    "task_id": "abc123-def456-...",
    "message": "Анализ запущен"
}
```

#### `GET /api/ai/result/{task_id}`
Получение результата AI-анализа.

**Параметры:**
- `task_id` (path) — ID задачи Celery

**Ответ (200 OK):**
```json
{
    "task_id": "abc123-def456-...",
    "status": "SUCCESS",
    "data": {
        "status": "success",
        "sku": 12345678,
        "image": "https://...",
        "rating": 4.5,
        "reviews_count": 50,
        "ai_analysis": {
            "flaws": ["Минус 1", "Минус 2", "Минус 3"],
            "strategy": ["Совет 1", "Совет 2", "Совет 3", "Совет 4", "Совет 5"]
        }
    }
}
```

### Админ endpoints

#### `GET /api/admin/stats`
Статистика платформы.

**Требует:** Аутентификация + права администратора

**Ответ (200 OK):**
```json
{
    "total_users": 100,
    "total_items_monitored": 250,
    "server_status": "OK"
}
```

**Ошибки:**
- `403 Forbidden` — нет прав администратора

---

## Запуск проекта

### Локальная разработка

#### Backend:

```bash
# Переход в директорию backend
cd backend

# Создание виртуального окружения
python -m venv venv

# Активация (Windows)
venv\Scripts\activate

# Активация (Linux/Mac)
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt

# Создание .env файла с переменными окружения
# (см. раздел "Переменные окружения")

# Запуск Redis (Docker)
docker run -d -p 6379:6379 redis:alpine

# Запуск PostgreSQL (Docker)
docker run -d -p 5432:5432 \
  -e POSTGRES_USER=wb_user \
  -e POSTGRES_PASSWORD=wb_secret_password \
  -e POSTGRES_DB=wb_monitor \
  postgres:15-alpine

# Запуск FastAPI сервера
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# В отдельном терминале: Запуск Celery Worker
celery -A celery_app worker --loglevel=info

# В отдельном терминале: Запуск Celery Beat
celery -A celery_app beat --loglevel=info
```

#### Frontend:

```bash
# Переход в директорию frontend
cd frontend

# Установка зависимостей
npm install

# Запуск dev сервера
npm run dev

# Сборка для продакшена
npm run build

# Предпросмотр production сборки
npm run preview
```

### Docker Compose (рекомендуется)

```bash
# Создание .env файла в корне проекта
# (см. раздел "Переменные окружения")

# Запуск всех сервисов
docker-compose up -d

# Просмотр логов
docker-compose logs -f

# Остановка всех сервисов
docker-compose down

# Остановка с удалением volumes
docker-compose down -v
```

**Сервисы будут доступны:**
- API: `http://localhost:8000`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

---

## Дополнительные файлы и директории

### `backend/proxy_ext/`
Директория для хранения временных файлов расширений браузера:
- `proxy_auth_plugin.zip` — автоматически генерируемое расширение для авторизации прокси

### `backend/msedgedriver`
Бинарный файл Edge WebDriver:
- Используется для запуска Selenium
- Должен быть совместим с версией Edge в Docker контейнере
- Установлен в `/usr/local/bin/msedgedriver` в Docker образе

### `frontend/node_modules/`
Директория зависимостей Node.js (автоматически генерируется, не включена в репозиторий)

### `backend/__pycache__/`
Кеш скомпилированных Python файлов (автоматически генерируется)

### `venv/`
Виртуальное окружение Python (не должно попадать в репозиторий)

---

## Примечания и особенности

1. **Зависимость от структуры Wildberries:**
   - CSS селекторы могут измениться при обновлении сайта
   - Требуется периодическое обновление селекторов
   - Fallback методы помогают снизить зависимость

2. **Производительность Selenium:**
   - Парсинг одного товара занимает 10-60 секунд
   - Использование headless режима ускоряет работу
   - Concurrency=1 в Celery Worker из-за ресурсоемкости Selenium

3. **Масштабирование:**
   - Для увеличения пропускной способности можно:
     - Увеличить количество Celery Workers
     - Использовать несколько прокси-серверов
     - Оптимизировать селекторы

4. **Безопасность:**
   - Токен бота хранится в переменных окружения
   - Прокси-данные не должны попадать в репозиторий
   - Валидация всех входных данных

5. **Telegram Web App:**
   - Приложение оптимизировано для работы в Telegram
   - Использует нативные стили Telegram через CSS переменные
   - Поддержка темного/светлого режима

6. **База данных:**
   - Используется каскадное удаление для связанных записей
   - Индексы на `telegram_id` и `sku` для быстрого поиска
   - Асинхронные операции для производительности

---

## Версия документа

Этот документ описывает проект UB (WB Analytics Platform) по состоянию на момент создания. Проект активно развивается, структура может изменяться.

**Дата создания:** 2024
**Последнее обновление:** 2024

