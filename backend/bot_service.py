import os
import logging
import aiohttp
import json

logger = logging.getLogger("BotService")

class BotService:
    def __init__(self):
        self.token = os.getenv("BOT_TOKEN")
        self.api_url = f"https://api.telegram.org/bot{self.token}"

    async def send_message(self, chat_id: int, text: str):
        """Отправка простого текстового сообщения"""
        if not self.token: return
        
        url = f"{self.api_url}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        
        async with aiohttp.ClientSession() as session:
            try:
                await session.post(url, json=payload)
            except Exception as e:
                logger.error(f"Failed to send message to {chat_id}: {e}")

    async def create_invoice_link(self, title: str, description: str, payload: str, amount_stars: int):
        """
        Создание ссылки на оплату в Telegram Stars.
        amount_stars: количество звезд (XTR).
        """
        if not self.token: return None
        
        url = f"{self.api_url}/createInvoiceLink"
        data = {
            "title": title,
            "description": description,
            "payload": payload,
            "provider_token": "", # Для Stars это поле должно быть пустым
            "currency": "XTR",
            "prices": [{"label": "Report", "amount": amount_stars}] # Amount в минимальных единицах, для Stars 1 = 1 Star
        }
        
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