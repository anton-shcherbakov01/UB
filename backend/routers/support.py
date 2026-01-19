import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from dependencies import get_current_user, get_db, SUPER_ADMIN_IDS
from database import User
from bot_service import bot_service

logger = logging.getLogger("SupportRouter")
router = APIRouter(prefix="/api/support", tags=["Support"])

class SupportRequest(BaseModel):
    subject: str
    message: str
    email: Optional[str] = None  # Optional email for contact

@router.post("/contact")
async def send_support_message(
    request: SupportRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Отправка сообщения в поддержку через Telegram бота администратору.
    """
    try:
        # Формируем сообщение для администратора
        user_info = f"👤 <b>Пользователь:</b> {user.first_name or 'Unknown'}"
        if user.username:
            user_info += f" (@{user.username})"
        user_info += f"\n🆔 <b>ID:</b> {user.id} ({user.telegram_id})"
        
        if request.email:
            user_info += f"\n📧 <b>Email:</b> {request.email}"
        
        message_text = f"📬 <b>Новое обращение в поддержку</b>\n\n{user_info}\n\n<b>Тема:</b> {request.subject}\n\n<b>Сообщение:</b>\n{request.message}"
        
        # Отправляем сообщение всем супер-администраторам
        sent_count = 0
        for admin_id in SUPER_ADMIN_IDS:
            try:
                await bot_service.send_message(admin_id, message_text)
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send support message to admin {admin_id}: {e}")
        
        if sent_count == 0:
            logger.error("Failed to send support message to any admin")
            raise HTTPException(status_code=500, detail="Не удалось отправить сообщение в поддержку. Попробуйте позже.")
        
        logger.info(f"Support message sent from user {user.id} to {sent_count} admin(s)")
        return {"status": "sent", "message": "Сообщение отправлено в поддержку. Мы свяжемся с вами в ближайшее время."}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending support message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ошибка при отправке сообщения")

