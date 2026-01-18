import os
import json
import logging
import uuid
import base64
import httpx
import random
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
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

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

class StarsPaymentRequest(BaseModel):
    plan_id: str
    amount: int

class YooPaymentRequest(BaseModel):
    plan_id: str

class RobokassaSubscriptionRequest(BaseModel):
    plan_id: str  # start, analyst, strategist

class RobokassaAddonRequest(BaseModel):
    addon_id: str  # extra_ai_100, history_audit

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
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    data = await request.json()
    
    if "message" in data and "successful_payment" in data["message"]:
        pay = data["message"]["successful_payment"]
        payload = json.loads(pay["invoice_payload"])
        
        user_id = payload.get("user_id")
        plan = payload.get("plan")
        
        if user_id and plan:
            user = await db.get(User, user_id)
            if user:
                now = datetime.utcnow()
                user.subscription_plan = plan
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

@router.post("/payment/yookassa/create")
async def create_yookassa_payment(req: YooPaymentRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        raise HTTPException(500, "YooKassa config missing")

    prices = {"pro": 2990, "business": 6990}
    amount_val = prices.get(req.plan_id)
    if not amount_val:
        raise HTTPException(400, "Invalid plan")

    idempotence_key = str(uuid.uuid4())
    auth_str = f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}"
    b64_auth = base64.b64encode(auth_str.encode()).decode()

    headers = {
        "Idempotence-Key": idempotence_key,
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/json"
    }

    return_url = "https://t.me/WbAnalyticsBot/app" 

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
    This endpoint receives payment notifications from Robokassa.
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
    user_id = data.get("Shp_user_id")
    
    if not out_sum or not inv_id_str or not signature_value:
        logger.error("Missing required fields in Robokassa callback")
        return "ERROR"
    
    try:
        inv_id = int(inv_id_str)
        amount = float(out_sum)
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid amount or InvId in callback: {e}")
        return "ERROR"
    
    # Verify signature
    robokassa = RobokassaService()
    if not robokassa.verify_callback_signature(out_sum, inv_id_str, signature_value):
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
                # Feature addon - could be stored in user preferences or activated
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
    User is redirected here after successful payment.
    Returns HTML page with auto-redirect to Telegram app.
    """
    telegram_app_url = "https://t.me/WbAnalyticsBot/app"
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Оплата успешна</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
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
                width: 80px;
                height: 80px;
                background: #10b981;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 24px;
                font-size: 48px;
            }}
            h1 {{
                color: #1f2937;
                font-size: 24px;
                font-weight: 700;
                margin-bottom: 12px;
            }}
            p {{
                color: #6b7280;
                font-size: 16px;
                line-height: 1.5;
                margin-bottom: 24px;
            }}
            .timer {{
                color: #667eea;
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 24px;
            }}
            .button {{
                background: #667eea;
                color: white;
                border: none;
                padding: 14px 28px;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                width: 100%;
                transition: background 0.2s;
            }}
            .button:hover {{
                background: #5568d3;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="icon">✓</div>
            <h1>Оплата успешна!</h1>
            <p>Ваша подписка активирована. Вы будете перенаправлены в приложение через <span id="countdown">5</span> секунд.</p>
            <div class="timer">Перенаправление...</div>
            <button class="button" onclick="redirectToApp()">Вернуться в приложение</button>
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

@router.get("/payment/robokassa/fail", response_class=HTMLResponse)
async def robokassa_fail(user_id: int = None):
    """
    Fail URL redirect handler.
    User is redirected here if payment failed or was cancelled.
    Returns HTML page with auto-redirect to Telegram app.
    """
    telegram_app_url = "https://t.me/WbAnalyticsBot/app"
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Оплата не завершена</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
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
                width: 80px;
                height: 80px;
                background: #ef4444;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 24px;
                font-size: 48px;
            }}
            h1 {{
                color: #1f2937;
                font-size: 24px;
                font-weight: 700;
                margin-bottom: 12px;
            }}
            p {{
                color: #6b7280;
                font-size: 16px;
                line-height: 1.5;
                margin-bottom: 24px;
            }}
            .timer {{
                color: #f5576c;
                font-size: 14px;
                font-weight: 600;
                margin-bottom: 24px;
            }}
            .button {{
                background: #f5576c;
                color: white;
                border: none;
                padding: 14px 28px;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                width: 100%;
                transition: background 0.2s;
                margin-bottom: 12px;
            }}
            .button:hover {{
                background: #e44855;
            }}
            .button-secondary {{
                background: #e5e7eb;
                color: #374151;
            }}
            .button-secondary:hover {{
                background: #d1d5db;
            }}
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