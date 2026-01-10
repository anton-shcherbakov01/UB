import logging
import aiohttp
import asyncio
from datetime import datetime, timedelta

logger = logging.getLogger("WB-API-Service")

class WBApiService:
    """
    Сервис для работы с официальным API Wildberries (Statistics API).
    """
    
    BASE_URL = "https://statistics-api.wildberries.ru/api/v1/supplier"

    async def check_token(self, token: str) -> bool:
        """Проверка валидности токена"""
        if not token: 
            return False
        # Используем метод incomes как легкий способ проверить доступ
        url = f"{self.BASE_URL}/incomes"
        params = {"dateFrom": datetime.now().strftime("%Y-%m-%d")}
        headers = {"Authorization": token}
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                    # 401 - Unauthorized, значит токен неверный
                    if resp.status == 401:
                        return False
                    # 200 или 429 (Rate limit) считаем валидным токеном
                    return True
            except Exception as e:
                logger.error(f"Token check error: {e}")
                return False

    async def get_dashboard_stats(self, token: str):
        """
        Получение сводной статистики для дашборда:
        1. Заказы за сегодня.
        2. Текущие остатки.
        """
        if not token:
            return {"error": "Token not provided"}

        async with aiohttp.ClientSession() as session:
            today_str = datetime.now().strftime("%Y-%m-%dT00:00:00")
            
            orders_task = self._get_orders(session, token, today_str)
            stocks_task = self._get_stocks(session, token, today_str)
            
            orders_res, stocks_res = await asyncio.gather(orders_task, stocks_task)
            
            return {
                "orders_today": orders_res,
                "stocks": stocks_res
            }

    async def get_new_orders_since(self, token: str, last_check: datetime):
        """
        Получение новых заказов с момента последней проверки.
        Для уведомлений.
        """
        if not last_check:
            last_check = datetime.now() - timedelta(hours=1)
        
        # WB API требует dateFrom. Берем с запасом 1 день, фильтруем в коде
        date_from_str = (last_check - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        
        async with aiohttp.ClientSession() as session:
            orders_data = await self._get_orders(session, token, date_from_str)
            
            if "items" not in orders_data:
                return []
            
            new_orders = []
            for order in orders_data["items"]:
                try:
                    # Формат даты WB: 2023-10-25T12:00:00
                    order_date = datetime.strptime(order["date"], "%Y-%m-%dT%H:%M:%S")
                    if order_date > last_check:
                        new_orders.append(order)
                except: continue
                
            return new_orders

    async def get_my_stocks(self, token: str):
        """
        Получение детального списка остатков (склад, SKU, цена).
        Используется для построения таблицы Unit-экономики.
        """
        if not token: return []
        
        today = datetime.now().strftime("%Y-%m-%dT00:00:00")
        url = f"{self.BASE_URL}/stocks"
        params = {"dateFrom": today}
        headers = {"Authorization": token}
        
        async with aiohttp.ClientSession() as session:
             try:
                async with session.get(url, headers=headers, params=params, timeout=20) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        logger.error(f"Stocks API error: {resp.status}")
                        return []
             except Exception as e:
                 logger.error(f"Stocks fetch error: {e}")
                 return []

    async def _get_orders(self, session, token: str, date_from: str):
        url = f"{self.BASE_URL}/orders"
        params = {"dateFrom": date_from}
        headers = {"Authorization": token}
        
        try:
            async with session.get(url, headers=headers, params=params, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if not data:
                        return {"count": 0, "sum": 0, "items": []}
                    
                    # Фильтруем отмены
                    valid_orders = [x for x in data if not x.get("isCancel")]
                    total_sum = sum(item.get("priceWithDiscount", 0) for item in valid_orders)
                    
                    return {
                        "count": len(valid_orders),
                        "sum": int(total_sum),
                        "items": valid_orders
                    }
                return {"count": 0, "sum": 0, "items": []}
        except Exception as e:
            logger.error(f"Fetch orders error: {e}")
            return {"count": 0, "sum": 0, "items": []}

    async def _get_stocks(self, session, token: str, date_from: str):
        """Агрегированные остатки (всего штук)"""
        url = f"{self.BASE_URL}/stocks"
        params = {"dateFrom": date_from}
        headers = {"Authorization": token}
        
        try:
            async with session.get(url, headers=headers, params=params, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    total_qty = sum(item.get("quantity", 0) for item in data) if data else 0
                    return {"total_quantity": total_qty}
                return {"total_quantity": 0}
        except Exception as e:
            logger.error(f"Fetch stocks error: {e}")
            return {"total_quantity": 0}

wb_api_service = WBApiService()