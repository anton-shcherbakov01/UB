# Настройка Robokassa

## Переменные окружения

Добавьте следующие переменные в `backend/.env`:

```env
# Robokassa Configuration
ROBOKASSA_MERCHANT_LOGIN=your_merchant_login
ROBOKASSA_PASSWORD1=your_password1
ROBOKASSA_PASSWORD2=your_password2
ROBOKASSA_TEST_MODE=true  # или false для продакшена
ROBOKASSA_SUCCESS_URL=https://your-domain.com/api/payment/robokassa/success
ROBOKASSA_FAIL_URL=https://your-domain.com/api/payment/robokassa/fail
ROBOKASSA_RESULT_URL=https://your-domain.com/api/payment/robokassa/result
```

## Настройка в личном кабинете Robokassa

1. Войдите в личный кабинет Robokassa
2. Перейдите в раздел "Настройки" → "Технические настройки"
3. Укажите следующие URL и методы HTTP:
   - **Result URL**: `https://your-domain.com/api/payment/robokassa/result` — **POST** (webhook для уведомлений)
   - **Success URL**: `https://your-domain.com/api/payment/robokassa/success` — **GET** (перенаправление после успешной оплаты)
   - **Fail URL**: `https://your-domain.com/api/payment/robokassa/fail` — **GET** (перенаправление после неудачной оплаты)

### Важно про методы HTTP:

- **Result URL (POST)**: Robokassa отправляет уведомление о статусе платежа через POST с form data. Это сервер-сервер запрос, пользователь его не видит.
- **Success URL (GET)**: После успешной оплаты браузер пользователя перенаправляется через GET с параметрами `InvId` и `OutSum` в query string.
- **Fail URL (GET)**: После неудачной оплаты браузер пользователя перенаправляется через GET с параметрами `InvId` и `OutSum` в query string.

## API Endpoints

### Создание платежа за подписку
```
POST /api/payment/robokassa/subscription
Body: {"plan_id": "analyst"}  // или "strategist"
```

### Создание платежа за аддон
```
POST /api/payment/robokassa/addon
Body: {"addon_id": "extra_ai_100"}  // или "history_audit"
```

### Webhook (ResultURL)
```
POST /api/payment/robokassa/result
(Вызывается автоматически Robokassa)
```

## Тестирование

В тестовом режиме (`ROBOKASSA_TEST_MODE=true`) используйте тестовые данные:
- Тестовый MerchantLogin (обычно "demo" или предоставляется Robokassa)
- Тестовые пароли Password1 и Password2 (отдельные для тестового режима)
- Тестовые карты для оплаты:
  - **Успешная оплата**: 4111 1111 1111 1111, CVV: любое, срок: любая будущая дата
  - **Отклоненная оплата**: 4111 1111 1111 1112
  - **3D Secure**: 4111 1111 1111 1113 (потребует ввод кода)

### Что происходит в тестовом режиме:

1. **Создание платежа**: 
   - Генерируется URL с параметром `IsTest=1`
   - Переход на страницу оплаты Robokassa (тестовую)

2. **Оплата**:
   - Используйте тестовые карты выше
   - Деньги НЕ списываются реально
   - Оплата проходит мгновенно

3. **Webhook (ResultURL)**:
   - Robokassa отправляет POST запрос на ваш `ROBOKASSA_RESULT_URL`
   - Подпись проверяется с помощью `Password2`
   - Подписка активируется автоматически

4. **Success/Fail URL**:
   - После оплаты пользователь перенаправляется на `SuccessURL` или `FailURL`
   - В URL передается `InvId` (ID платежа)

### Важно:
- В тестовом режиме реальные деньги НЕ списываются
- Тестовые платежи не видны в реальном кабинете Robokassa
- Для продакшена установите `ROBOKASSA_TEST_MODE=false`

## Безопасность

- **Password1** используется для генерации подписи при создании ссылки на оплату
- **Password2** используется для проверки подписи в webhook (ResultURL)
- Никогда не передавайте пароли в клиентский код
- Используйте HTTPS для всех URL

