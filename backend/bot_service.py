import os
import logging
import aiohttp
import json

logger = logging.getLogger("BotService")

class BotService:
    def __init__(self):
        self.token = os.getenv("BOT_TOKEN")
        if not self.token:
            logger.warning("⚠️ BOT_TOKEN не установлен! Уведомления не будут отправляться.")
            self.api_url = None
        else:
            self.api_url = f"https://api.telegram.org/bot{self.token}"

    async def send_message(self, chat_id: int, text: str):
        """Отправка простого текстового сообщения"""
        if not self.token:
            logger.warning(f"⚠️ Пропуск отправки сообщения в chat_id={chat_id}: BOT_TOKEN не установлен")
            return
        
        url = f"{self.api_url}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload) as resp:
                    result = await resp.json()
                    if result.get("ok"):
                        logger.info(f"✅ Сообщение отправлено в chat_id={chat_id}")
                    else:
                        error_code = result.get("error_code")
                        error_desc = result.get("description", "Unknown error")
                        logger.error(f"❌ Telegram API Error для chat_id={chat_id}: [{error_code}] {error_desc}")
            except aiohttp.ClientError as e:
                logger.error(f"❌ Network error при отправке в chat_id={chat_id}: {e}")
            except Exception as e:
                logger.error(f"❌ Failed to send message to {chat_id}: {e}", exc_info=True)

    async def create_invoice_link(self, title: str, description: str, payload: str, amount_stars: int):
        """
        Создание ссылки на оплату в Telegram Stars.
        amount_stars: количество звезд (XTR).
        """
        if not self.token: return None
        
        url = f"{self.api_url}/createInvoiceLink"
        # Для XTR (Telegram Stars) amount указывается напрямую в звездах
        # По документации Telegram Bot API: для XTR amount указывается как целое число звезд
        # НЕ нужно умножать на 100, в отличие от обычных валют
        
        data = {
            "title": title,
            "description": description,
            "payload": payload,
            "provider_token": "", # Для Stars это поле должно быть пустым
            "currency": "XTR",
            "prices": [{"label": "Subscription", "amount": amount_stars}]
        }
        
        logger.info(f"Creating invoice with amount_stars={amount_stars} (XTR currency, direct value)")
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=data) as resp:
                    res = await resp.json()
                    if res.get("ok"):
                        return res["result"]
                    else:
                        logger.error(f"Invoice error: {res}")
                        return None
            except Exception as e:
                logger.error(f"Create invoice error: {e}")
                return None

bot_service = BotService()