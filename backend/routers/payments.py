import os
import json
import logging
import uuid
import base64
import httpx
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from database import get_db, User, Payment
from dependencies import get_current_user
from bot_service import bot_service

logger = logging.getLogger("Payments")
router = APIRouter(prefix="/api", tags=["Payments"])

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

class StarsPaymentRequest(BaseModel):
    plan_id: str
    amount: int

class YooPaymentRequest(BaseModel):
    plan_id: str

@router.post("/payment/stars_link")
async def create_stars_link(req: StarsPaymentRequest, user: User = Depends(get_current_user)):
    title = f"Подписка {req.plan_id.upper()}"
    desc = f"Активация тарифа {req.plan_id} на 1 месяц"
    payload = json.dumps({"user_id": user.id, "plan": req.plan_id})
    
    link = await bot_service.create_invoice_link(title, desc, payload, req.amount)
    if not link:
        raise HTTPException(500, "Ошибка создания ссылки")
        
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
                user.subscription_plan = plan
                user.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
                db.add(user)
                await db.commit()
                logger.info(f"User {user.telegram_id} upgraded to {plan} via Stars")
                
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
            user.subscription_plan = plan_id
            now = datetime.utcnow()
            if user.subscription_expires_at and user.subscription_expires_at > now:
                user.subscription_expires_at += timedelta(days=30)
            else:
                user.subscription_expires_at = now + timedelta(days=30)
            user.is_recurring = False 
            db.add(user)
            await db.commit()
            logger.info(f"User {user.telegram_id} subscription extended (YooKassa).")
        
    return {"status": "ok"}