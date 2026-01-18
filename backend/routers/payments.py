import os
import json
import logging
import uuid
import base64
import httpx
import random
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from database import get_db, User, Payment
from dependencies import get_current_user
from bot_service import bot_service
from services.robokassa_service import RobokassaService
from config.plans import TIERS, ADDONS, get_plan_config
from dependencies.quota import increment_usage

logger = logging.getLogger("Payments")
router = APIRouter(prefix="/api", tags=["Payments"])

# === CONFIGURATION ===
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")  # Обязательно добавьте в .env!
BOT_APP_URL = "https://t.me/juicystat_bot/app/juicystat"  # Ваша ссылка на приложение

# === MODELS ===
class StarsPaymentRequest(BaseModel):
    plan_id: str
    amount: int

class YooPaymentRequest(BaseModel):
    plan_id: str

class RobokassaSubscriptionRequest(BaseModel):
    plan_id: str  # start, analyst, strategist

class RobokassaAddonRequest(BaseModel):
    addon_id: str  # extra_ai_100, history_audit

# === STARS PAYMENTS ===

@router.post("/payment/stars_link")
async def create_stars_link(req: StarsPaymentRequest, user: User = Depends(get_current_user)):
    if not req.amount or req.amount <= 0:
        logger.error(f"Invalid amount for Stars payment: {req.amount} (plan: {req.plan_id})")
        raise HTTPException(400, detail=f"Неверная сумма для оплаты: {req.amount}")
    
    title = f"Подписка {req.plan_id.upper()}"
    desc = f"Активация тарифа {req.plan_id} на 1 месяц"
    payload = json.dumps({"user_id": user.id, "plan": req.plan_id})
    
    logger.info(f"Creating Stars payment link for user {user.id}, plan {req.plan_id}, amount {req.amount} stars")
    
    link = await bot_service.create_invoice_link(title, desc, payload, req.amount)
    if not link:
        logger.error(f"Failed to create invoice link for user {user.id}, plan {req.plan_id}, amount {req.amount}")
        raise HTTPException(500, "Ошибка создания ссылки на оплату")
    
    logger.info(f"Successfully created Stars payment link for user {user.id}: {link[:50]}...")
    return {"invoice_link": link}

@router.post("/webhook/telegram")
async def telegram_webhook(
    request: Request, 
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
):
    # 1. Проверка безопасности (Secret Token)
    if TELEGRAM_WEBHOOK_SECRET and x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET:
        logger.warning("Unauthorized access to Telegram webhook (invalid token)")
        raise HTTPException(status_code=403, detail="Unauthorized")

    data = await request.json()
    
    if "message" in data and "successful_payment" in data["message"]:
        pay = data["message"]["successful_payment"]
        payload_str = pay.get("invoice_payload")
        
        try:
            payload = json.loads(payload_str)
        except (json.JSONDecodeError, TypeError):
            logger.error(f"Failed to decode payload: {payload_str}")
            return {"ok": True}
        
        user_id = payload.get("user_id")
        plan = payload.get("plan")
        
        if user_id and plan:
            user = await db.get(User, user_id)
            if user:
                now = datetime.utcnow()
                user.subscription_plan = plan
                
                # Продление или установка даты
                if user.subscription_expires_at and user.subscription_expires_at > now:
                    user.subscription_expires_at += timedelta(days=30)
                else:
                    user.subscription_expires_at = now + timedelta(days=30)

                # Принудительно сбрасываем квоты при любой успешной оплате
                user.usage_reset_date = now + timedelta(days=30)
                user.ai_requests_used = 0
                user.extra_ai_balance = 0
                user.cluster_requests_used = 0
                
                db.add(user)
                await db.commit()
                logger.info(f"User {user.telegram_id} upgraded to {plan} via Stars (quotas reset)")
                
    return {"ok": True}

# === YOOKASSA PAYMENTS ===

@router.post("/payment/yookassa/create")
async def create_yookassa_payment(req: YooPaymentRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        raise HTTPException(500, "YooKassa config missing")

    # Исправлено: берем цены из конфига, а не хардкодим
    plan_config = get_plan_config(req.plan_id)
    if not plan_config:
         raise HTTPException(400, "Invalid plan ID")

    amount_val = plan_config.get("price")
    if not amount_val:
        raise HTTPException(400, "Plan price not found or free")

    idempotence_key = str(uuid.uuid4())
    auth_str = f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()

    headers = {
        "Idempotence-Key": idempotence_key,
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/json"
    }

    # Используем константу с правильным URL
    return_url = BOT_APP_URL

    payload = {
        "amount": {"value": f"{amount_val}.00", "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": return_url},
        "description": f"Подписка {req.plan_id.upper()} (30 дней)",
        "metadata": {"user_id": user.id, "telegram_id": user.telegram_id, "plan_id": req.plan_id},
        "receipt": {
            "customer": {"email": "user@example.com"},
            "items": [{"description": f"Тариф {req.plan_id}", "quantity": "1.00", "amount": {"value": f"{amount_val}.00", "currency": "RUB"}, "vat_code": "1"}]
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post("https://api.yookassa.ru/v3/payments", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            
            new_payment = Payment(
                user_id=user.id,
                amount=amount_val,
                currency="RUB",
                provider_payment_id=data['id'],
                status=data['status'],
                plan_id=req.plan_id
            )
            db.add(new_payment)
            await db.commit()
            
            return {"payment_url": data['confirmation']['confirmation_url'], "payment_id": data['id']}
        except Exception as e:
            logger.error(f"YooKassa Connection Error: {e}")
            raise HTTPException(500, "Internal payment error")

@router.post("/payment/yookassa/webhook")
async def yookassa_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        data = await request.json()
    except:
        raise HTTPException(400, "Invalid JSON")

    event = data.get("event")
    obj = data.get("object", {})

    if event == "payment.succeeded" and obj.get("status") == "succeeded":
        payment_id = obj.get("id")
        metadata = obj.get("metadata", {})
        user_id = metadata.get("user_id")
        plan_id = metadata.get("plan_id")

        if not user_id or not plan_id:
            return {"status": "ignored"}

        stmt = select(Payment).where(Payment.provider_payment_id == payment_id)
        payment_record = (await db.execute(stmt)).scalars().first()
        
        if payment_record:
            payment_record.status = "succeeded"
            payment_record.confirmed_at = datetime.utcnow()
            db.add(payment_record)
        else:
            payment_record = Payment(
                user_id=int(user_id),
                provider_payment_id=payment_id,
                amount=int(float(obj['amount']['value'])),
                currency="RUB",
                status="succeeded",
                plan_id=plan_id,
                confirmed_at=datetime.utcnow()
            )
            db.add(payment_record)

        user = await db.get(User, int(user_id))
        if user:
            now = datetime.utcnow()
            user.subscription_plan = plan_id
            if user.subscription_expires_at and user.subscription_expires_at > now:
                user.subscription_expires_at += timedelta(days=30)
            else:
                user.subscription_expires_at = now + timedelta(days=30)
            # Принудительно сбрасываем квоты при любой успешной оплате
            user.usage_reset_date = now + timedelta(days=30)
            user.ai_requests_used = 0
            user.extra_ai_balance = 0
            user.is_recurring = False 
            db.add(user)
            await db.commit()
            logger.info(f"User {user.telegram_id} subscription extended (YooKassa, quotas reset).")
        
    return {"status": "ok"}

# ==================== ROBOKASSA PAYMENTS ====================

@router.post("/payment/robokassa/subscription")
async def create_robokassa_subscription(
    req: RobokassaSubscriptionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create Robokassa payment for subscription plan.
    """
    # Get plan config
    plan_config = get_plan_config(req.plan_id)
    if not plan_config:
        raise HTTPException(status_code=400, detail="Invalid plan ID")
    
    # Check if plan is free
    if plan_config.get("price", 0) == 0:
        raise HTTPException(status_code=400, detail="This plan is free, no payment required")
    
    amount = plan_config.get("price", 0)
    plan_name = plan_config.get("name", req.plan_id)
    
    # Create payment record first to get its ID
    payment = Payment(
        user_id=user.id,
        provider_payment_id="",  # Will be updated after we get the payment ID
        amount=amount,
        currency="RUB",
        status="pending",
        plan_id=req.plan_id
    )
    db.add(payment)
    await db.flush()  # Flush to get the payment ID without committing
    await db.refresh(payment)  # Refresh to get the auto-generated ID
    
    # Use payment.id as InvId (must be integer < 2,147,483,647)
    inv_id = payment.id
    
    # Update provider_payment_id with the actual InvId
    payment.provider_payment_id = str(inv_id)
    await db.commit()
    
    # Create Robokassa service
    robokassa = RobokassaService()
    
    # Generate payment URL
    description = f"Подписка {plan_name} на 1 месяц"
    payment_url = robokassa.create_payment_url(
        inv_id=inv_id,
        amount=amount,
        description=description,
        user_id=user.id
    )
    
    logger.info(f"Created Robokassa payment for user {user.id}, plan {req.plan_id}, amount {amount}")
    
    return {
        "payment_url": payment_url,
        "payment_id": str(inv_id),
        "amount": amount,
        "plan": plan_name
    }

@router.post("/payment/robokassa/addon")
async def create_robokassa_addon(
    req: RobokassaAddonRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create Robokassa payment for addon purchase.
    """
    # Get addon config
    addon_config = ADDONS.get(req.addon_id)
    if not addon_config:
        raise HTTPException(status_code=400, detail="Invalid addon ID")
    
    amount = addon_config.get("price", 0)
    if amount == 0:
        raise HTTPException(status_code=400, detail="This addon is free")
    
    # Create payment record first to get its ID
    payment = Payment(
        user_id=user.id,
        provider_payment_id="",  # Will be updated after we get the payment ID
        amount=amount,
        currency="RUB",
        status="pending",
        plan_id=f"addon_{req.addon_id}"  # Store addon ID in plan_id field
    )
    db.add(payment)
    await db.flush()  # Flush to get the payment ID without committing
    await db.refresh(payment)  # Refresh to get the auto-generated ID
    
    # Use payment.id as InvId (must be integer < 2,147,483,647)
    inv_id = payment.id
    
    # Update provider_payment_id with the actual InvId
    payment.provider_payment_id = str(inv_id)
    await db.commit()
    
    # Create Robokassa service
    robokassa = RobokassaService()
    
    # Generate payment URL
    addon_name = req.addon_id.replace("_", " ").title()
    description = f"Дополнение: {addon_name}"
    payment_url = robokassa.create_payment_url(
        inv_id=inv_id,
        amount=amount,
        description=description,
        user_id=user.id
    )
    
    logger.info(f"Created Robokassa payment for user {user.id}, addon {req.addon_id}, amount {amount}")
    
    return {
        "payment_url": payment_url,
        "payment_id": str(inv_id),
        "amount": amount,
        "addon": addon_name
    }

@router.post("/payment/robokassa/result")
async def robokassa_result_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Robokassa ResultURL webhook handler.
    """
    try:
        # Robokassa sends form data
        form_data = await request.form()
        data = dict(form_data)
    except Exception as e:
        logger.error(f"Error parsing Robokassa callback: {e}")
        return "ERROR"
    
    # Extract required fields
    out_sum = data.get("OutSum", "")
    inv_id_str = data.get("InvId", "")
    signature_value = data.get("SignatureValue", "")
    
    # Get additional parameters (Shp_*)
    # user_id = data.get("Shp_user_id") # Not strictly needed if we look up by payment ID
    
    # Collect all Shp_ parameters for signature verification
    shp_params = {}
    for key, value in data.items():
        if key.startswith("Shp_"):
            shp_params[key] = value
    
    if not out_sum or not inv_id_str or not signature_value:
        logger.error("Missing required fields in Robokassa callback")
        return "ERROR"
    
    try:
        inv_id = int(inv_id_str)
        # amount = float(out_sum) # Used inside verification
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid amount or InvId in callback: {e}")
        return "ERROR"
    
    # Verify signature WITH shp_params
    robokassa = RobokassaService()
    if not robokassa.verify_callback_signature(out_sum, inv_id_str, signature_value, shp_params if shp_params else None):
        logger.error(f"Invalid signature for payment {inv_id}")
        return "ERROR"
    
    # Find payment record
    stmt = select(Payment).where(Payment.provider_payment_id == str(inv_id))
    payment = (await db.execute(stmt)).scalars().first()
    
    if not payment:
        logger.error(f"Payment {inv_id} not found in database")
        return robokassa.get_payment_status_response(inv_id, success=False)
    
    # Check if already processed
    if payment.status == "succeeded":
        logger.info(f"Payment {inv_id} already processed")
        return robokassa.get_payment_status_response(inv_id, success=True)
    
    # Update payment status
    payment.status = "succeeded"
    payment.confirmed_at = datetime.utcnow()
    db.add(payment)
    
    # Get user
    user = await db.get(User, payment.user_id)
    if not user:
        logger.error(f"User {payment.user_id} not found for payment {inv_id}")
        await db.rollback()
        return robokassa.get_payment_status_response(inv_id, success=False)
    
    # Process payment based on type
    plan_id = payment.plan_id
    
    if plan_id.startswith("addon_"):
        # Process addon purchase
        addon_id = plan_id.replace("addon_", "")
        addon_config = ADDONS.get(addon_id)
        
        if addon_config:
            if addon_config.get("resource") == "ai_requests":
                # Add to extra_ai_balance
                amount_to_add = addon_config.get("amount", 0)
                user.extra_ai_balance = (user.extra_ai_balance or 0) + amount_to_add
                logger.info(f"User {user.id} purchased {amount_to_add} AI requests addon")
            elif addon_config.get("feature"):
                # Feature addon
                logger.info(f"User {user.id} purchased feature addon: {addon_id}")
    else:
        # Process subscription purchase
        plan_config = get_plan_config(plan_id)
        if plan_config:
            # Update subscription
            now = datetime.utcnow()
            user.subscription_plan = plan_id
            
            # Extend subscription (30 days)
            if user.subscription_expires_at and user.subscription_expires_at > now:
                user.subscription_expires_at += timedelta(days=30)
            else:
                user.subscription_expires_at = now + timedelta(days=30)
            
            # Принудительно сбрасываем квоты при любой успешной оплате
            user.usage_reset_date = now + timedelta(days=30)
            user.ai_requests_used = 0
            user.extra_ai_balance = 0
            user.cluster_requests_used = 0
            
            logger.info(f"User {user.id} subscription updated to {plan_id} via Robokassa (quotas reset)")
    
    db.add(user)
    await db.commit()
    
    logger.info(f"Successfully processed Robokassa payment {inv_id} for user {user.id}")
    return robokassa.get_payment_status_response(inv_id, success=True)

@router.get("/payment/robokassa/success", response_class=HTMLResponse)
async def robokassa_success(user_id: int = None):
    """
    Success URL redirect handler.
    """
    # Ссылка на корень твоего веб-приложения (где фронтенд)
    # Если фронт лежит там же где и апи, то просто "/"
    # Если фронт отдельно, например на vercel, то "https://my-front.com/"
    # Для Telegram WebApp часто лучше просто перегрузить страницу.
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Оплата успешна</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                background-color: #f3f4f6;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                padding: 20px;
            }}
            .card {{
                background: white;
                border-radius: 20px;
                padding: 30px;
                text-align: center;
                max-width: 350px;
                width: 100%;
                box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            }}
            .icon-box {{
                width: 70px; height: 70px; background: #dcfce7; color: #16a34a;
                border-radius: 50%; display: flex; align-items: center; justify-content: center;
                margin: 0 auto 20px; font-size: 32px;
            }}
            h1 {{ color: #111827; font-size: 22px; font-weight: 700; margin-bottom: 10px; }}
            p {{ color: #6b7280; font-size: 15px; line-height: 1.5; margin-bottom: 25px; }}
            .btn {{
                background: #2563eb; color: white; border: none;
                padding: 12px 20px; border-radius: 12px; font-size: 16px; font-weight: 600;
                cursor: pointer; width: 100%; transition: opacity 0.2s;
                text-decoration: none; display: inline-block;
            }}
            .btn:hover {{ opacity: 0.9; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="icon-box">✓</div>
            <h1>Оплата прошла успешно!</h1>
            <p>Ваш тариф активирован, а лимиты обновлены. Нажмите кнопку ниже, чтобы вернуться к работе.</p>
            
            <button class="btn" onclick="goBack()">Вернуться в приложение</button>
        </div>

        <script>
            // Сообщаем Телеграму, что мы готовы (на всякий случай)
            if (window.Telegram && window.Telegram.WebApp) {{
                window.Telegram.WebApp.ready();
            }}

            function goBack() {{
                // Логика:
                // 1. Если это попап - пытаемся его закрыть.
                // 2. Если мы в главном окне - перезагружаем его, направляя на главную страницу приложения.
                
                if (window.Telegram && window.Telegram.WebApp) {{
                    // Попытка закрыть окно (работает, если оплата открывалась через openLink или popup)
                    try {{
                        window.Telegram.WebApp.close();
                    }} catch (e) {{
                        console.log("Cannot close", e);
                    }}
                }}
                
                // Если окно не закрылось (мы в том же окне), делаем редирект
                // Вместо t.me ссылки используем window.location.href на корень твоего сайта
                // Это перезагрузит приложение и обновит данные (лимиты)
                
                // ВАЖНО: Укажи здесь URL твоего веб-приложения (фронтенда)
                // Если бот открывает https://api.juicystat.ru/app, то пиши сюда этот путь
                window.location.href = "https://api.juicystat.ru/"; 
                // Или просто window.location.href = "/"; если корень там же.
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@router.get("/payment/robokassa/fail", response_class=HTMLResponse)
async def robokassa_fail(user_id: int = None):
    """
    Fail URL redirect handler.
    """
    # Используем константу URL
    telegram_app_url = BOT_APP_URL
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Оплата не завершена</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }}
            .container {{
                background: white;
                border-radius: 24px;
                padding: 40px;
                max-width: 400px;
                width: 100%;
                text-align: center;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            }}
            .icon {{
                width: 80px; height: 80px; background: #ef4444;
                border-radius: 50%; display: flex; align-items: center; justify-content: center;
                margin: 0 auto 24px; font-size: 48px;
            }}
            h1 {{ color: #1f2937; font-size: 24px; font-weight: 700; margin-bottom: 12px; }}
            p {{ color: #6b7280; font-size: 16px; line-height: 1.5; margin-bottom: 24px; }}
            .timer {{ color: #f5576c; font-size: 14px; font-weight: 600; margin-bottom: 24px; }}
            .button {{
                background: #f5576c; color: white; border: none;
                padding: 14px 28px; border-radius: 12px; font-size: 16px;
                font-weight: 600; cursor: pointer; width: 100%;
                transition: background 0.2s; margin-bottom: 12px;
            }}
            .button:hover {{ background: #e44855; }}
            .button-secondary {{ background: #e5e7eb; color: #374151; }}
            .button-secondary:hover {{ background: #d1d5db; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="icon">✕</div>
            <h1>Оплата не завершена</h1>
            <p>Похоже, оплата не была завершена. Вы можете попробовать снова или выбрать другой метод оплаты.</p>
            <div class="timer">Вы будете перенаправлены через <span id="countdown">5</span> секунд</div>
            <button class="button" onclick="redirectToApp()">Вернуться в приложение</button>
            <button class="button button-secondary" onclick="redirectToApp()">Попробовать снова</button>
        </div>
        <script>
            let countdown = 5;
            const countdownEl = document.getElementById('countdown');
            
            const timer = setInterval(() => {{
                countdown--;
                countdownEl.textContent = countdown;
                if (countdown <= 0) {{
                    clearInterval(timer);
                    redirectToApp();
                }}
            }}, 1000);
            
            function redirectToApp() {{
                if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.openLink) {{
                    window.Telegram.WebApp.openLink('{telegram_app_url}');
                }} else {{
                    window.location.href = '{telegram_app_url}';
                }}
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)