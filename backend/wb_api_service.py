# ================
# File: backend/wb_api_service.py
# ================
import logging
import aiohttp
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger("WB-API-Service")

class WBApiService:
    """
    Service for official Wildberries API (Statistics + Common + Advertising).
    Implements Retry logic and In-Memory Caching.
    """
    
    BASE_URL = "https://statistics-api.wildberries.ru/api/v1/supplier"
    COMMON_URL = "https://common-api.wildberries.ru/api/v1" 
    ADV_URL = "https://advert-api.wb.ru/adv/v1" # Advertising API
    
    # In-Memory Cache
    _cache: Dict[str, Any] = {}
    _cache_ttl = 300 # 5 min

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
                        logger.warning(f"Rate Limit (429) on {url}. Sleep {backoff}s...")
                        await asyncio.sleep(backoff)
                        backoff *= 2
                    elif resp.status >= 500:
                        logger.warning(f"Server Error ({resp.status}). Retry...")
                        await asyncio.sleep(backoff)
                        backoff *= 2
                    else:
                        text = await resp.text()
                        logger.error(f"WB API Error {resp.status}: {text}")
                        return None
            except Exception as e:
                logger.error(f"Request failed: {e}")
                await asyncio.sleep(backoff)
        return None

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
                async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                    return resp.status != 401
            except: return False

    # --- ADVERTISING API (RTB) ---

    async def get_advert_list(self, token: str):
        """Fetch list of advertising campaigns."""
        url = f"{self.ADV_URL}/promotion/count"
        headers = {"Authorization": token}
        async with aiohttp.ClientSession() as session:
            return await self._request_with_retry(session, url, headers)

    async def get_advert_info(self, token: str, campaign_id: int):
        """Fetch detailed campaign info (current bid, items)."""
        url = f"{self.ADV_URL}/promotion/adverts"
        headers = {"Authorization": token, "Content-Type": "application/json"}
        # API requires list of IDs
        async with aiohttp.ClientSession() as session:
            data = await self._request_with_retry(session, url, headers, method='POST', params={"id": campaign_id})
            return data[0] if data and isinstance(data, list) else None

    async def get_advert_stats(self, token: str, campaign_id: int):
        """Fetch CTR, CPC, Spend for Target CPA logic."""
        url = f"{self.ADV_URL}/fullstat"
        headers = {"Authorization": token}
        params = {"id": campaign_id}
        async with aiohttp.ClientSession() as session:
             return await self._request_with_retry(session, url, headers, params=params)

    async def set_advert_bid(self, token: str, campaign_id: int, bid: int, item_id: int):
        """Update CPM (Bid)."""
        url = f"{self.ADV_URL}/upd"
        headers = {"Authorization": token}
        # Payload structure depends on campaign type (Search/Catalog)
        # Assuming 'Search' or 'Auto' type for MVP
        payload = {
            "advertId": campaign_id,
            "type": 6, # Type 6 is often used for Search, needs verification for specific campaign type
            "price": bid,
            "param": item_id # Usually subjectId or nmId
        }
        async with aiohttp.ClientSession() as session:
            # WB often returns 200 even on logical fail, need to check body if possible
            # Here we just execute the POST
            return await self._request_with_retry(session, url, headers, method='POST', json_data=payload)

    # --- EXISTING STATS METHODS ---

    async def get_dashboard_stats(self, token: str):
        if not token: return {"error": "Token not provided"}
        async with aiohttp.ClientSession() as session:
            today_str = datetime.now().strftime("%Y-%m-%dT00:00:00")
            orders_task = self._get_orders(session, token, today_str, use_cache=True)
            stocks_task = self._get_stocks(session, token, today_str, use_cache=True)
            orders_res, stocks_res = await asyncio.gather(orders_task, stocks_task)
            return {"orders_today": orders_res, "stocks": stocks_res}

    async def get_new_orders_since(self, token: str, last_check: datetime):
        if not last_check: last_check = datetime.now() - timedelta(hours=1)
        date_from_str = (last_check - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        async with aiohttp.ClientSession() as session:
            orders_data = await self._get_orders(session, token, date_from_str, use_cache=False)
            if not orders_data or "items" not in orders_data: return []
            new_orders = []
            for order in orders_data["items"]:
                try:
                    if datetime.strptime(order["date"], "%Y-%m-%dT%H:%M:%S") > last_check:
                        new_orders.append(order)
                except: continue
            return new_orders

    async def get_my_stocks(self, token: str):
        if not token: return []
        today = datetime.now().strftime("%Y-%m-%dT00:00:00")
        url = f"{self.BASE_URL}/stocks"
        headers = {"Authorization": token}
        async with aiohttp.ClientSession() as session:
             data = await self._get_cached_or_request(session, url, headers, {"dateFrom": today}, use_cache=True)
             return data if isinstance(data, list) else []

    async def get_warehouse_coeffs(self, token: str):
        return [
            {"warehouse": "Коледино", "coefficient": 1, "transit_time": "1 день", "price_per_liter": 30},
            {"warehouse": "Электросталь", "coefficient": 5, "transit_time": "1 день", "price_per_liter": 150},
            {"warehouse": "Казань", "coefficient": 0, "transit_time": "2 дня", "price_per_liter": 20},
        ]

    async def _get_orders(self, session, token, date_from, use_cache=True):
        url = f"{self.BASE_URL}/orders"
        headers = {"Authorization": token}
        data = await self._get_cached_or_request(session, url, headers, {"dateFrom": date_from}, use_cache=use_cache)
        if not data or not isinstance(data, list): return {"count": 0, "sum": 0, "items": []}
        valid_orders = [x for x in data if not x.get("isCancel")]
        return {"count": len(valid_orders), "sum": int(sum(i.get("priceWithDiscount", 0) for i in valid_orders)), "items": valid_orders}

    async def _get_stocks(self, session, token, date_from, use_cache=True):
        url = f"{self.BASE_URL}/stocks"
        headers = {"Authorization": token}
        data = await self._get_cached_or_request(session, url, headers, {"dateFrom": date_from}, use_cache=use_cache)
        return {"total_quantity": sum(i.get("quantity", 0) for i in data) if isinstance(data, list) else 0}

wb_api_service = WBApiService()