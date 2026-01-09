import logging
import aiohttp
import asyncio
from datetime import datetime, timedelta

logger = logging.getLogger("WB-API-Service")

class WBApiService:
    """
    Сервис для работы с официальным API Wildberries (Внутренняя аналитика).
    Документация: https://openapi.wb.ru/
    """
    
    BASE_URL = "https://statistics-api.wildberries.ru/api/v1/supplier"

    async def check_token(self, token: str) -> bool:
        """Проверка валидности токена (делаем легкий запрос)"""
        if not token: 
            return False
        # Запрашиваем поставки (обычно легкий метод) или склады
        url = f"{self.BASE_URL}/incomes"
        params = {
            "dateFrom": datetime.now().strftime("%Y-%m-%d")
        }
        headers = {"Authorization": token}
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                    # 401 - Unauthorized, значит токен неверный
                    if resp.status == 401:
                        return False
                    # 200 или даже 429 (Too many requests) означает, что токен принят системой
                    return True
            except Exception as e:
                logger.error(f"Token check error: {e}")
                return False

    async def get_dashboard_stats(self, token: str):
        """
        Получение сводной статистики для дашборда:
        1. Заказы за сегодня (сумма и количество).
        2. Текущие остатки (общее количество).
        """
        if not token:
            return {"error": "Token not provided"}

        async with aiohttp.ClientSession() as session:
            # Запускаем запросы параллельно для скорости
            today_str = datetime.now().strftime("%Y-%m-%dT00:00:00")
            
            orders_task = self._get_orders(session, token, today_str)
            stocks_task = self._get_stocks(session, token, today_str)
            
            orders_res, stocks_res = await asyncio.gather(orders_task, stocks_task)
            
            return {
                "orders_today": orders_res,
                "stocks": stocks_res
            }

    async def _get_orders(self, session, token: str, date_from: str):
        """Получение заказов с начала дня"""
        url = f"{self.BASE_URL}/orders"
        params = {"dateFrom": date_from}
        headers = {"Authorization": token}
        
        try:
            async with session.get(url, headers=headers, params=params, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # data - это список заказов
                    if not data:
                        return {"count": 0, "sum": 0, "items": []}
                    
                    total_sum = sum(item.get("priceWithDiscount", 0) for item in data if not item.get("isCancel"))
                    count = len(data)
                    
                    # Берем топ-5 последних заказов для отображения
                    last_orders = sorted(data, key=lambda x: x.get("date"), reverse=True)[:5]
                    
                    return {
                        "count": count,
                        "sum": int(total_sum),
                        "last_orders": last_orders
                    }
                elif resp.status == 429:
                    logger.warning("WB API Rate Limit (Orders)")
                    return {"error": "Rate limit", "count": 0, "sum": 0}
                else:
                    logger.error(f"WB API Orders Error: {resp.status}")
                    return {"error": f"API Error {resp.status}", "count": 0, "sum": 0}
        except Exception as e:
            logger.error(f"Fetch orders error: {e}")
            return {"error": str(e), "count": 0, "sum": 0}

    async def _get_stocks(self, session, token: str, date_from: str):
        """Получение остатков"""
        url = f"{self.BASE_URL}/stocks"
        params = {"dateFrom": date_from}
        headers = {"Authorization": token}
        
        try:
            async with session.get(url, headers=headers, params=params, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if not data:
                        return {"total_quantity": 0}
                    
                    total_qty = sum(item.get("quantity", 0) for item in data)
                    return {"total_quantity": total_qty}
                elif resp.status == 429:
                    return {"error": "Rate limit", "total_quantity": 0}
                else:
                    return {"error": f"API Error {resp.status}", "total_quantity": 0}
        except Exception as e:
            logger.error(f"Fetch stocks error: {e}")
            return {"error": str(e), "total_quantity": 0}

wb_api_service = WBApiService()