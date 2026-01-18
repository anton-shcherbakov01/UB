# ================
# File: backend/wb_api/statistics.py
# ================
import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import HTTPException

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
    Used by the main WBApiService.
    """

    URLS = {
        "common": "https://common-api.wildberries.ru",
        "content": "https://content-api.wildberries.ru",
        "statistics": "https://statistics-api.wildberries.ru",
        "advert": "https://advert-api.wildberries.ru",
        "marketplace": "https://marketplace-api.wildberries.ru",
        "feedbacks": "https://feedbacks-api.wildberries.ru",
        "analytics": "https://seller-analytics-api.wildberries.ru"
    }

    def __init__(self):
        self.timeout = aiohttp.ClientTimeout(total=10)
    
    async def get_token_scopes(self, token: str) -> Dict[str, bool]:
        """
        Параллельный опрос всех шлюзов WB для построения карты доступов.
        """
        headers = {"Authorization": token}
        
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            tasks = {
                "content": self._probe(session, "GET", f"{self.URLS['content']}/content/v2/cards/limits", headers),
                "marketplace": self._probe(session, "GET", f"{self.URLS['marketplace']}/api/v3/warehouses", headers),
                "stats": self._probe(session, "GET", f"{self.URLS['statistics']}/api/v1/supplier/incomes", headers, params={"dateFrom": "2024-01-01"}),
                "advert": self._probe(session, "GET", f"{self.URLS['advert']}/adv/v1/promotion/count", headers),
                "feedbacks": self._probe(session, "GET", f"{self.URLS['feedbacks']}/api/v1/questions/count", headers, params={"isAnswered": "false"}),
                "prices": self._probe(session, "GET", f"{self.URLS['common']}/public/api/v1/info", headers)
            }
            
            results_list = await asyncio.gather(*tasks.values(), return_exceptions=True)
            
            keys = list(tasks.keys())
            raw_res = {}
            for i, key in enumerate(keys):
                res = results_list[i]
                if isinstance(res, Exception):
                    raw_res[key] = False
                else:
                    raw_res[key] = res if isinstance(res, bool) else False

        promotion_scope = raw_res.get("advert", False)
        users_scope = False
        
        return {
            "content": raw_res.get("content", False),
            "marketplace": raw_res.get("marketplace", False),
            "analytics": raw_res.get("stats", False),
            "promotion": promotion_scope,
            "returns": raw_res.get("marketplace", False),
            "documents": raw_res.get("content", False),
            "statistics": raw_res.get("stats", False),
            "finance": raw_res.get("stats", False),
            "supplies": raw_res.get("marketplace", False) or raw_res.get("content", False),
            "chat": raw_res.get("feedbacks", False),
            "questions": raw_res.get("feedbacks", False),
            "prices": raw_res.get("prices", False) or raw_res.get("content", False),
            "users": users_scope
        }

    async def _probe(self, session, method, url, headers, params=None) -> bool:
        try:
            async with session.request(method, url, headers=headers, params=params) as resp:
                if resp.status in [401, 403]: return False
                return True
        except:
            return False
    
    async def get_api_mode(self, token: str) -> str:
        if not token:
            return "read_only"
        
        headers = {"Authorization": token}
        
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            test_urls = [
                f"{self.URLS['content']}/content/v2/cards/limits",
                f"{self.URLS['marketplace']}/api/v3/warehouses",
            ]
            
            read_works = False
            for url in test_urls:
                try:
                    async with session.get(url, headers=headers) as resp:
                        if resp.status not in [401, 403]:
                            read_works = True
                            break
                except:
                    continue
            
            if not read_works:
                return "read_only"
            
            write_test_url = f"{self.URLS['content']}/content/v2/cards/limits"
            try:
                async with session.post(write_test_url, headers=headers, json={}) as resp:
                    if resp.status in [401, 403]:
                        return "read_only"
                    return "read_write"
            except:
                return "read_only"

    async def get_dashboard_stats(self, token: str):
        """Сводка: Заказы сегодня и остатки"""
        if not token: 
            return {"orders_today": {"sum": 0, "count": 0}, "stocks": {"total_quantity": 0}}

        async with aiohttp.ClientSession() as session:
            today_str = datetime.now().strftime("%Y-%m-%dT00:00:00")
            
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
                    order_date = datetime.strptime(order["date"][:19], "%Y-%m-%dT%H:%M:%S")
                    last_check_normalized = last_check.replace(tzinfo=None) if last_check.tzinfo else last_check
                    if order_date > last_check_normalized:
                        new_orders.append(order)
                except: continue
                
            return new_orders
    
    # --- НОВЫЕ МЕТОДЫ ДЛЯ МОНИТОРИНГА ---

    async def get_sales_since(self, token: str, date_from: str) -> List[Dict]:
        """Получение выкупов (продаж) через миксин (Использует старый API)"""
        url = f"{self.URLS['statistics']}/api/v1/supplier/sales"
        params = {"dateFrom": date_from, "flag": 0}
        headers = {"Authorization": token}
        
        data = await self._request_with_retry(None, url, headers, params=params)
        return data if isinstance(data, list) else []

    async def get_sales_funnel_full(self, token: str, date_from: str, date_to: str) -> Dict[str, Any]:
        """
        Получение ПОЛНОЙ воронки (Просмотры -> Корзины -> Заказы -> Выкупы) 
        через Analytics API. Добавлена пагинация для получения данных по всем карточкам.
        """
        url = f"{self.URLS['analytics']}/api/v2/nm-report/detail"
        headers = {"Authorization": token}
        
        res = {
            "visitors": 0,
            "addToCart": 0,
            "ordersCount": 0,
            "ordersSum": 0,
            "buyoutsCount": 0,
            "buyoutsSum": 0
        }

        page = 1
        is_more = True
        
        try:
            while is_more:
                payload = {
                    "brandNames": [],
                    "objectIDs": [],
                    "tagIDs": [],
                    "nmIDs": [],
                    "timezone": "Europe/Moscow",
                    "period": {
                        "begin": date_from,
                        "end": date_to
                    },
                    "orderBy": {
                        "field": "openCardCount",
                        "mode": "desc"
                    },
                    "page": page
                }
                
                data = await self._request_with_retry(
                    session=None,
                    url=url,
                    headers=headers,
                    method="POST",
                    json_data=payload,
                    retries=4
                )
                
                if not data or not isinstance(data, dict):
                    break
                
                cards = data.get("data", {}).get("cards", [])
                
                if not cards:
                    is_more = False
                    break
                
                for c in cards:
                    stats = c.get("statistics", {}).get("selectedPeriod", {})
                    res["visitors"] += stats.get("openCardCount", 0)
                    res["addToCart"] += stats.get("addToCartCount", 0)
                    res["ordersCount"] += stats.get("ordersCount", 0)
                    res["ordersSum"] += stats.get("ordersSumRub", 0)
                    res["buyoutsCount"] += stats.get("buyoutsCount", 0)
                    res["buyoutsSum"] += stats.get("buyoutsSumRub", 0)
                
                page += 1
                # Безопасный лимит страниц, чтобы не зациклиться
                if page > 100:
                    break

            return res
            
        except Exception as e:
            logger.error(f"Failed to fetch full sales funnel: {e}")
            return {}

    async def get_statistics_today(self, token: str) -> Dict[str, Any]:
        """
        Сводная статистика за сегодня для уведомлений.
        """
        today_date = datetime.now()
        # Analytics API требует формат YYYY-MM-DD HH:mm:ss
        funnel_start = today_date.strftime("%Y-%m-%d 00:00:00")
        funnel_end = today_date.strftime("%Y-%m-%d 23:59:59")
        
        try:
            # Используем один мощный запрос вместо трех слабых
            funnel_data = await self.get_sales_funnel_full(token, funnel_start, funnel_end)
            
            if not funnel_data:
                return {
                    "orders_sum": 0, "orders_count": 0,
                    "sales_sum": 0, "sales_count": 0,
                    "visitors": 0, "addToCart": 0
                }

            logger.info(f"Statistics today (Analytics API): {funnel_data}")
            
            return {
                "orders_sum": int(funnel_data.get("ordersSum", 0)),
                "orders_count": funnel_data.get("ordersCount", 0),
                "sales_sum": int(funnel_data.get("buyoutsSum", 0)),
                "sales_count": funnel_data.get("buyoutsCount", 0),
                "visitors": funnel_data.get("visitors", 0),
                "addToCart": funnel_data.get("addToCart", 0)
            }
        except Exception as e:
            logger.error(f"Error getting statistics today: {e}", exc_info=True)
            return {
                "orders_sum": 0, "orders_count": 0,
                "sales_sum": 0, "sales_count": 0,
                "visitors": 0, "addToCart": 0
            }

    async def get_my_stocks(self, token: str):
        if not token: return []
        
        url = "https://statistics-api.wildberries.ru/api/v1/supplier/stocks"
        date_from = "2023-01-01T00:00:00"
        params = {"dateFrom": date_from}
        headers = {"Authorization": token}
        
        async with aiohttp.ClientSession() as session:
             if hasattr(self, '_get_cached_or_request'):
                 data = await self._get_cached_or_request(session, url, headers, params, use_cache=True)
             else:
                 async with session.get(url, headers=headers, params=params) as resp:
                     data = await resp.json() if resp.status == 200 else []

             return data if isinstance(data, list) else []

    async def get_warehouse_coeffs(self, token: str):
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
    
    async def get_all_commissions(self, token: str) -> Dict[str, float]:
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
        """
        date_from = "2023-01-01T00:00:00"
        return await self._request("/api/v1/supplier/stocks", params={"dateFrom": date_from})

    async def get_orders(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Метод «Заказы». Возвращает заказы.
        """
        date_from = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        return await self._request("/api/v1/supplier/orders", params={"dateFrom": date_from, "flag": 0})

    async def get_sales(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Метод «Продажи». Возвращает продажи (факты выкупа).
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
    
    async def calculate_transit(self, liters: int, origin: str, destination: str, custom_transit_rate: float = None):
        """
        Умный калькулятор транзита.
        """
        # --- 1. Тарифы на прямую доставку ---
        direct_tariffs = {
            "Коледино": 15.0, "Электросталь": 14.0, "Казань": 8.0, 
            "Краснодар": 10.0, "Тула": 12.0
        }
        
        direct_base_freight = 3000.0 
        
        if origin.lower() in destination.lower() or destination.lower() in origin.lower():
            direct_base_freight = 1500.0
            direct_rate = 2.0 
        else:
            direct_rate = direct_tariffs.get(destination, 12.0)

        direct_cost = int(direct_base_freight + (liters * direct_rate))

        # --- 2. Тарифы на Транзит WB ---
        # Если пользователь задал свой тариф, используем его. Иначе дефолт 4.5
        transit_rate = custom_transit_rate if custom_transit_rate is not None else 4.5
        
        if origin == destination:
            transit_rate = 0
            
        transit_cost = int(liters * transit_rate)
        
        benefit = direct_cost - transit_cost
        is_profitable = benefit > 0 and origin != destination

        return {
            "origin": origin,
            "destination": destination,
            "volume": liters,
            "custom_rate": transit_rate,
            "direct": {
                "total": direct_cost,
                "rate": direct_rate,
                "base": direct_base_freight,
                "description": "Своя машина / ТК"
            },
            "transit": {
                "total": transit_cost,
                "rate": transit_rate,
                "description": "Транзит силами WB"
            },
            "is_profitable": is_profitable,
            "benefit": benefit
        }