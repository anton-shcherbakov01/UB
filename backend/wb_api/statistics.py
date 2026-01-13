import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from .base import WBApiBase

class WBStatisticsMixin(WBApiBase):
    
    async def get_token_scopes(self, token: str) -> dict:
        """
        Диагностика доступных разделов API для данного токена.
        Возвращает словарь с флагами доступа.
        """
        headers = {"Authorization": token}
        results = {
            "statistics": False,
            "standard": False,
            "promotion": False,
            "questions": False
        }

        async with aiohttp.ClientSession() as session:
            # 1. Проверка Статистики (Используем /orders как маркер)
            try:
                # Тайм-аут короткий, нам нужен только статус код
                async with session.get(f"{self.BASE_URL}/orders", 
                                       params={"dateFrom": datetime.now().strftime("%Y-%m-%d")}, 
                                       headers=headers, timeout=5) as r:
                    # 401 = Unauthorized, 200/429 = OK (доступ есть)
                    results["statistics"] = r.status != 401
            except: 
                pass

            # 2. Проверка Контента/Общих (Standard) - тарифы
            try:
                async with session.get(f"{self.COMMON_URL}/tariffs/box", 
                                       params={"date": datetime.now().strftime("%Y-%m-%d")}, 
                                       headers=headers, timeout=5) as r:
                    results["standard"] = r.status != 401
            except: 
                pass

            # 3. Проверка Рекламы (Promotion)
            try:
                async with session.get(f"{self.ADV_URL}/promotion/count", 
                                       headers=headers, timeout=5) as r:
                    results["promotion"] = r.status != 401
            except: 
                pass

        return results

    async def get_dashboard_stats(self, token: str):
        """Сводка: Заказы сегодня и остатки"""
        if not token: 
            return {"orders_today": {"sum": 0, "count": 0}, "stocks": {"total_quantity": 0}}

        async with aiohttp.ClientSession() as session:
            today_str = datetime.now().strftime("%Y-%m-%dT00:00:00")
            
            orders_task = self._get_orders(session, token, today_str, use_cache=True)
            stocks_task = self._get_stocks(session, token, today_str, use_cache=True)
            
            orders_res, stocks_res = await asyncio.gather(orders_task, stocks_task)
            
            return {
                "orders_today": orders_res,
                "stocks": stocks_res
            }

    async def get_new_orders_since(self, token: str, last_check: datetime):
        if not last_check:
            last_check = datetime.now() - timedelta(hours=1)
        
        date_from_str = (last_check - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        
        async with aiohttp.ClientSession() as session:
            orders_data = await self._get_orders(session, token, date_from_str, use_cache=False)
            
            if not orders_data or "items" not in orders_data:
                return []
            
            new_orders = []
            for order in orders_data["items"]:
                try:
                    order_date = datetime.strptime(order["date"], "%Y-%m-%dT%H:%M:%S")
                    if order_date > last_check:
                        new_orders.append(order)
                except: continue
                
            return new_orders

    async def get_my_stocks(self, token: str):
        if not token: return []
        
        today = datetime.now().strftime("%Y-%m-%dT00:00:00")
        url = f"{self.BASE_URL}/stocks"
        params = {"dateFrom": today}
        headers = {"Authorization": token}
        
        async with aiohttp.ClientSession() as session:
             data = await self._get_cached_or_request(session, url, headers, params, use_cache=True)
             return data if isinstance(data, list) else []

    async def get_warehouse_coeffs(self, token: str):
        """
        Получение реальных коэффициентов приемки.
        """
        url = f"{self.COMMON_URL}/tariffs/box"
        headers = {"Authorization": token} if token else {}
        today = datetime.now().strftime("%Y-%m-%d")
        params = {"date": today}

        async with aiohttp.ClientSession() as session:
            data = await self._get_cached_or_request(session, url, headers, params, use_cache=True)
            if data and 'response' in data and 'data' in data['response']:
                return data['response']['data']
            return []

    async def calculate_transit(self, liters: int, destination: str = "Koledino"):
        # Логика калькулятора остается на бэкенде, но коэффициенты можно брать из get_warehouse_coeffs
        # Для простоты оставляем расчет, но убираем заглушку рандома
        direct_base = 1500
        direct_rate = 30
        
        transit_base = 500 
        transit_rate = 10 
        transit_logistics = 1000 
        
        return {
            "destination": destination,
            "direct": {
                "rate": direct_rate,
                "total": direct_base + (liters * direct_rate)
            },
            "transit_kazan": {
                "rate": transit_rate,
                "logistics": transit_logistics,
                "total": transit_base + (liters * transit_rate) + transit_logistics
            }
        }

    async def _get_orders(self, session, token: str, date_from: str, use_cache=True):
        url = f"{self.BASE_URL}/orders"
        params = {"dateFrom": date_from}
        headers = {"Authorization": token}
        
        data = await self._get_cached_or_request(session, url, headers, params, use_cache=use_cache)
        
        if not data:
            return {"count": 0, "sum": 0, "items": []}
        
        if isinstance(data, list):
            valid_orders = [x for x in data if not x.get("isCancel")]
            total_sum = sum(item.get("priceWithDiscount", 0) for item in valid_orders)
            return {
                "count": len(valid_orders),
                "sum": int(total_sum),
                "items": valid_orders
            }
        return {"count": 0, "sum": 0, "items": []}

    async def _get_stocks(self, session, token: str, date_from: str, use_cache=True):
        url = f"{self.BASE_URL}/stocks"
        params = {"dateFrom": date_from}
        headers = {"Authorization": token}
        
        data = await self._get_cached_or_request(session, url, headers, params, use_cache=use_cache)
        
        if not data:
            return {"total_quantity": 0}
            
        if isinstance(data, list):
            total_qty = sum(item.get("quantity", 0) for item in data)
            return {"total_quantity": total_qty}
            
        return {"total_quantity": 0}