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
3. Укажите следующие URL:
   - **Result URL**: `https://your-domain.com/api/payment/robokassa/result`
   - **Success URL**: `https://your-domain.com/api/payment/robokassa/success`
   - **Fail URL**: `https://your-domain.com/api/payment/robokassa/fail`

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
- Тестовый MerchantLogin
- Тестовые пароли Password1 и Password2
- Тестовые карты для оплаты (см. документацию Robokassa)

## Безопасность

- **Password1** используется для генерации подписи при создании ссылки на оплату
- **Password2** используется для проверки подписи в webhook (ResultURL)
- Никогда не передавайте пароли в клиентский код
- Используйте HTTPS для всех URL

