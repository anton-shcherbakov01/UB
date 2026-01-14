# ================
# File: backend/wb_api/statistics.py
# ================
import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import HTTPException

# Попытка импорта базы. Если запускаем изолированно - создаем заглушку, 
# чтобы код не падал при проверке синтаксиса.
try:
    from .base import WBApiBase
except ImportError:
    class WBApiBase:
        BASE_URL = "https://statistics-api.wildberries.ru/api/v1"
        COMMON_URL = "https://common-api.wildberries.ru/api/v1"
        ADV_URL = "https://advert-api.wildberries.ru/adv/v1"
        async def _get_cached_or_request(self, *args, **kwargs): pass 
        async def _request_with_retry(self, *args, **kwargs): pass

logger = logging.getLogger("WB-API-Stats")

class WBStatisticsMixin(WBApiBase):
    """
    Mixin containing business logic for Statistics API.
    Used by the main WBApiService (Legacy & General features).
    """
    
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
                async with session.get(f"{self.BASE_URL}/supplier/orders", 
                                     params={"dateFrom": datetime.now().strftime("%Y-%m-%d")}, 
                                     headers=headers, timeout=5) as r:
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
            
            # Используем внутренние методы с кэшированием
            orders_task = self._get_orders_mixin(session, token, today_str, use_cache=True)
            stocks_task = self._get_stocks_mixin(session, token, today_str, use_cache=True)
            
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
            orders_data = await self._get_orders_mixin(session, token, date_from_str, use_cache=False)
            
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
        url = "https://statistics-api.wildberries.ru/api/v1/supplier/stocks"
        params = {"dateFrom": today}
        headers = {"Authorization": token}
        
        async with aiohttp.ClientSession() as session:
             if hasattr(self, '_get_cached_or_request'):
                 data = await self._get_cached_or_request(session, url, headers, params, use_cache=True)
             else:
                 async with session.get(url, headers=headers, params=params) as resp:
                     data = await resp.json() if resp.status == 200 else []

             return data if isinstance(data, list) else []

    async def get_warehouse_coeffs(self, token: str):
        """Получение реальных коэффициентов приемки."""
        url = "https://common-api.wildberries.ru/api/v1/tariffs/box"
        headers = {"Authorization": token} if token else {}
        today = datetime.now().strftime("%Y-%m-%d")
        params = {"date": today}

        async with aiohttp.ClientSession() as session:
            if hasattr(self, '_get_cached_or_request'):
                data = await self._get_cached_or_request(session, url, headers, params, use_cache=True)
            else:
                async with session.get(url, headers=headers, params=params) as resp:
                    data = await resp.json() if resp.status == 200 else {}

            if data and 'response' in data and 'data' in data['response']:
                return data['response']['data']
            return []

    async def calculate_transit(self, liters: int, destination: str = "Koledino"):
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
    
    async def get_all_commissions(self, token: str) -> Dict[str, float]:
        """Получает тарифы комиссий по всем категориям."""
        url = "https://common-api.wildberries.ru/api/v1/tariffs/commission"
        headers = {"Authorization": token}
        
        if hasattr(self, '_request_with_retry'):
            data = await self._request_with_retry(None, url, headers, method='GET')
        else:
             return {}
        
        if not data or 'report' not in data:
            return {}
            
        commissions = {}
        for item in data['report']:
            sub_id = str(item.get('subjectID'))
            pct = item.get('kgvpMarketplace', 25.0) 
            commissions[sub_id] = float(pct)
            
        return commissions

    async def get_box_tariffs(self, token: str, date_str: str) -> Dict[str, Dict]:
        """Получает коэффициенты и базовые ставки логистики коробов."""
        url = "https://common-api.wildberries.ru/api/v1/tariffs/box"
        params = {"date": date_str}
        headers = {"Authorization": token}
        
        if hasattr(self, '_request_with_retry'):
            data = await self._request_with_retry(None, url, headers, params=params)
        else:
            return {}
        
        if not data or 'response' not in data:
            return {}

        tariffs = {}
        warehouse_list = data['response'].get('data', {}).get('warehouseList', [])
        
        for w in warehouse_list:
            name = w.get('warehouseName')
            if not name: continue
            
            try:
                base_s = w.get('boxDeliveryBase', '0').replace(',', '.')
                liter_s = w.get('boxDeliveryLiter', '0').replace(',', '.')
                tariffs[name] = {"base": float(base_s), "liter": float(liter_s)}
            except ValueError:
                continue
        return tariffs

    # --- Internal Helpers for Mixin ---
    async def _get_orders_mixin(self, session, token: str, date_from: str, use_cache=True):
        url = "https://statistics-api.wildberries.ru/api/v1/supplier/orders"
        params = {"dateFrom": date_from}
        headers = {"Authorization": token}
        
        if hasattr(self, '_get_cached_or_request'):
            data = await self._get_cached_or_request(session, url, headers, params, use_cache=use_cache)
        else:
             async with session.get(url, headers=headers, params=params) as resp:
                data = await resp.json() if resp.status == 200 else []
        
        if not data:
            return {"count": 0, "sum": 0, "items": []}
        
        if isinstance(data, list):
            valid_orders = [x for x in data if not x.get("isCancel")]
            total_sum = sum(item.get("priceWithDiscount", 0) for item in valid_orders)
            return {"count": len(valid_orders), "sum": int(total_sum), "items": valid_orders}
        return {"count": 0, "sum": 0, "items": []}

    async def _get_stocks_mixin(self, session, token: str, date_from: str, use_cache=True):
        url = "https://statistics-api.wildberries.ru/api/v1/supplier/stocks"
        params = {"dateFrom": date_from}
        headers = {"Authorization": token}
        
        if hasattr(self, '_get_cached_or_request'):
            data = await self._get_cached_or_request(session, url, headers, params, use_cache=use_cache)
        else:
            async with session.get(url, headers=headers, params=params) as resp:
                data = await resp.json() if resp.status == 200 else []
        
        if not data: return {"total_quantity": 0}
        if isinstance(data, list):
            total_qty = sum(item.get("quantity", 0) for item in data)
            return {"total_quantity": total_qty}
        return {"total_quantity": 0}


class WBStatisticsAPI:
    """
    Standalone Client for Wildberries Statistics API.
    Used by Supply Service (New Logic).
    """
    BASE_URL = "https://statistics-api.wildberries.ru"

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def _request(self, endpoint: str, params: Dict[str, Any] = None, retries: int = 3) -> List[Dict[str, Any]]:
        url = f"{self.BASE_URL}{endpoint}"
        async with aiohttp.ClientSession() as session:
            for attempt in range(retries):
                try:
                    async with session.get(url, headers=self.headers, params=params, timeout=30) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        elif resp.status == 429:
                            wait_time = 2 ** attempt
                            logger.warning(f"Rate limit 429. Waiting {wait_time}s...")
                            await asyncio.sleep(wait_time)
                            continue
                        elif resp.status == 401:
                            logger.error("WB API Unauthorized.")
                            raise HTTPException(status_code=401, detail="Invalid WB Token")
                        else:
                            text = await resp.text()
                            logger.error(f"WB API Error {resp.status}: {text}")
                            return []
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout on {endpoint}. Retrying...")
                except Exception as e:
                    logger.error(f"Request failed: {e}")
                    
        return []

    async def get_stocks(self) -> List[Dict[str, Any]]:
        """
        Метод «Склад». Возвращает остатки товаров на складах.
        Endpoint: /api/v1/supplier/stocks
        """
        date_from = datetime.utcnow().strftime("%Y-%m-%d")
        return await self._request("/api/v1/supplier/stocks", params={"dateFrom": date_from})

    async def get_orders(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Метод «Заказы». Возвращает заказы.
        Endpoint: /api/v1/supplier/orders
        """
        date_from = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        return await self._request("/api/v1/supplier/orders", params={"dateFrom": date_from, "flag": 0})

    async def get_sales(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Метод «Продажи». Возвращает продажи (факты выкупа).
        Endpoint: /api/v1/supplier/sales
        """
        date_from = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        return await self._request("/api/v1/supplier/sales", params={"dateFrom": date_from, "flag": 0})

    async def get_turnover_data(self) -> Dict[str, Any]:
        """
        Aggregates data for supply analysis.
        """
        stocks, orders = await asyncio.gather(
            self.get_stocks(),
            self.get_orders(days=30)
        )
        return {"stocks": stocks, "orders": orders}