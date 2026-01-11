import logging
import aiohttp
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger("WB-API-Service")

class WBApiService:
    BASE_URL = "https://statistics-api.wildberries.ru/api/v1/supplier"
    COMMON_URL = "https://common-api.wildberries.ru/api/v1"
    ADV_URL = "https://advert-api.wb.ru/adv/v0"
    
    _cache: Dict[str, Any] = {}
    _cache_ttl = 300 

    async def _request_with_retry(self, session, url, headers, params=None, method='GET', json_data=None, retries=3):
        backoff = 2 
        for attempt in range(retries):
            try:
                if method == 'GET':
                    coro = session.get(url, headers=headers, params=params, timeout=20)
                else:
                    coro = session.post(url, headers=headers, json=json_data, timeout=20)

                async with coro as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 429:
                        await asyncio.sleep(backoff)
                        backoff *= 2 
                    elif resp.status >= 500:
                        await asyncio.sleep(backoff)
                        backoff *= 2
                    else:
                        return None
            except Exception:
                await asyncio.sleep(backoff)
        return None

    # ... (методы кэша, orders, stocks остаются прежними, добавляем рекламу) ...
    def _get_cache_key(self, token, method, params):
        token_part = token[-10:] if token else "none"
        param_str = json.dumps(params, sort_keys=True)
        return f"{token_part}:{method}:{param_str}"

    async def _get_cached_or_request(self, session, url, headers, params, use_cache=True):
        if not use_cache:
            return await self._request_with_retry(session, url, headers, params)
        cache_key = self._get_cache_key(headers.get("Authorization"), url, params)
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if (datetime.now() - ts).total_seconds() < self._cache_ttl:
                return data
        data = await self._request_with_retry(session, url, headers, params)
        if data is not None:
            self._cache[cache_key] = (datetime.now(), data)
        return data

    async def check_token(self, token: str) -> bool:
        if not token: return False
        url = f"{self.BASE_URL}/incomes"
        params = {"dateFrom": datetime.now().strftime("%Y-%m-%d")}
        headers = {"Authorization": token}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, params=params, timeout=5) as resp:
                    return resp.status != 401
            except: return False

    async def get_dashboard_stats(self, token: str):
        if not token: return {"orders_today": {"sum": 0, "count": 0}, "stocks": {"total_quantity": 0}}
        async with aiohttp.ClientSession() as session:
            today_str = datetime.now().strftime("%Y-%m-%dT00:00:00")
            orders_task = self._get_orders(session, token, today_str, use_cache=True)
            stocks_task = self._get_stocks(session, token, today_str, use_cache=True)
            orders_res, stocks_res = await asyncio.gather(orders_task, stocks_task)
            
            # Для дашборда считаем только валидные
            valid_orders_sum = sum(x.get('priceWithDiscount', 0) for x in orders_res.get('items', []) if not x.get('isCancel'))
            valid_orders_count = len([x for x in orders_res.get('items', []) if not x.get('isCancel')])
            
            return {
                "orders_today": {"sum": valid_orders_sum, "count": valid_orders_count},
                "stocks": stocks_res
            }

    async def get_advert_campaigns(self, token: str):
        url = f"{self.ADV_URL}/adverts"
        headers = {"Authorization": token}
        async with aiohttp.ClientSession() as session:
            return (await self._request_with_retry(session, url, headers, params={"status": 9, "type": 9})) or []

    async def get_campaign_info(self, token: str, cid: int):
        url = f"{self.ADV_URL}/advert"
        headers = {"Authorization": token}
        async with aiohttp.ClientSession() as session:
            return await self._request_with_retry(session, url, headers, params={"id": cid})

    async def set_campaign_bid(self, token: str, cid: int, bid: int):
        url = f"{self.ADV_URL}/cpm"
        headers = {"Authorization": token}
        async with aiohttp.ClientSession() as session:
            return await self._request_with_retry(session, url, headers, json_data={"advertId": cid, "type": 6, "cpm": bid}, method='POST')

    async def get_new_orders_since(self, token, last_check):
        return []

    async def get_my_stocks(self, token: str):
        if not token: return []
        today = datetime.now().strftime("%Y-%m-%dT00:00:00")
        url = f"{self.BASE_URL}/stocks"
        params = {"dateFrom": today}
        headers = {"Authorization": token}
        async with aiohttp.ClientSession() as session:
             data = await self._get_cached_or_request(session, url, headers, params, use_cache=True)
             return data if isinstance(data, list) else []

    async def get_sales_history_raw(self, token: str, days: int = 30):
        """
        Возвращает ВСЕ заказы (включая отмены) для точного расчета Unit-экономики.
        """
        if not token: return []
        date_from = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
        async with aiohttp.ClientSession() as session:
            data = await self._get_orders(session, token, date_from, use_cache=True)
            return data.get("items", [])

    async def get_warehouse_coeffs(self, token: str):
        return [{"warehouse": "Коледино", "coefficient": 1, "transit_time": "1 день", "price_per_liter": 30}]

    async def calculate_transit(self, liters: int, destination: str = "Koledino"):
        direct_cost = 1500 + liters * 30
        transit_cost = 1500 + liters * 10
        return {
            "direct": {"total": direct_cost},
            "transit_kazan": {"total": transit_cost},
            "is_profitable": True,
            "recommendation": "Транзит",
            "direct_cost": direct_cost,
            "transit_cost": transit_cost,
            "benefit": 200
        }

    async def _get_orders(self, session, token: str, date_from: str, use_cache=True):
        url = f"{self.BASE_URL}/orders"
        params = {"dateFrom": date_from}
        headers = {"Authorization": token}
        data = await self._get_cached_or_request(session, url, headers, params, use_cache=use_cache)
        if not data: return {"count": 0, "sum": 0, "items": []}
        if isinstance(data, list):
            # Возвращаем ВСЕ заказы, фильтрация будет на уровне бизнес-логики
            return {"count": len(data), "items": data}
        return {"count": 0, "items": []}

    async def _get_stocks(self, session, token: str, date_from: str, use_cache=True):
        url = f"{self.BASE_URL}/stocks"
        params = {"dateFrom": date_from}
        headers = {"Authorization": token}
        data = await self._get_cached_or_request(session, url, headers, params, use_cache=use_cache)
        if isinstance(data, list):
            total_qty = sum(item.get("quantity", 0) for item in data)
            return {"total_quantity": total_qty}
        return {"total_quantity": 0}

wb_api_service = WBApiService()