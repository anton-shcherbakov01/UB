# ================
# File: backend/wb_api/statistics.py
# ================
import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import HTTPException

# Попытка импорта базового класса
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
        if token == "DEMO":
            return {
                "content": True, "marketplace": True, "analytics": True, "promotion": True,
                "returns": True, "documents": True, "statistics": True, "finance": True,
                "supplies": True, "chat": True, "questions": True, "prices": True, "users": True,
                "api_mode": "read_only"
            }

        headers = {"Authorization": token}
        
        # Payload для проверки v3 API
        analytics_payload = {
            "selectedPeriod": {
                "start": datetime.now().strftime("%Y-%m-%d"),
                "end": datetime.now().strftime("%Y-%m-%d")
            },
            "nmIds": [],
            "limit": 1
        }

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            tasks = {
                "content": self._probe(session, "GET", f"{self.URLS['content']}/content/v2/cards/limits", headers),
                "marketplace": self._probe(session, "GET", f"{self.URLS['marketplace']}/api/v3/warehouses", headers),
                "analytics": self._probe(session, "POST", f"{self.URLS['analytics']}/api/analytics/v3/sales-funnel/products", headers, json_data=analytics_payload),
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
        analytics_access = raw_res.get("analytics", False)
        
        return {
            "content": raw_res.get("content", False),
            "marketplace": raw_res.get("marketplace", False),
            "analytics": analytics_access,
            "promotion": promotion_scope,
            "returns": raw_res.get("marketplace", False),
            "documents": raw_res.get("content", False),
            "statistics": analytics_access, 
            "finance": analytics_access,
            "supplies": raw_res.get("marketplace", False) or raw_res.get("content", False),
            "chat": raw_res.get("feedbacks", False),
            "questions": raw_res.get("feedbacks", False),
            "prices": raw_res.get("prices", False) or raw_res.get("content", False),
            "users": users_scope
        }

    async def _probe(self, session, method, url, headers, params=None, json_data=None) -> bool:
        try:
            async with session.request(method, url, headers=headers, params=params, json=json_data) as resp:
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
        """Сводка с жестким фильтром 'Сегодня'"""
        if not token: 
            return {"orders_today": {"sum": 0, "count": 0}, "stocks": {"total_quantity": 0}}

        async with aiohttp.ClientSession() as session:
            # Берем начало текущего дня строго 00:00:00
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_str = today_start.strftime("%Y-%m-%dT%H:%M:%S")
            
            # use_cache=True допустимо для дашборда
            orders_res = await self._get_orders_mixin(session, token, today_str, use_cache=True)
            await asyncio.sleep(0.3) 
            stocks_res = await self._get_stocks_mixin(session, token, today_str, use_cache=True)
            
            return {
                "orders_today": orders_res,
                "stocks": stocks_res
            }

    async def get_new_orders_since(self, token: str, last_check: datetime):
        """Получение новых заказов с защитой от дублей и нулей"""
        if not last_check:
            last_check = datetime.now() - timedelta(hours=1)
        
        # Берем с запасом, фильтруем в коде
        date_from_str = (last_check - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        
        async with aiohttp.ClientSession() as session:
            orders_data = await self._get_orders_mixin(session, token, date_from_str, use_cache=False)
            
            if not orders_data or "items" not in orders_data:
                return []
            
            new_orders = []
            for order in orders_data["items"]:
                try:
                    # Дата в WB формате может быть с Z или без
                    d_str = order["date"][:19]
                    order_date = datetime.strptime(d_str, "%Y-%m-%dT%H:%M:%S")
                    
                    last_check_normalized = last_check.replace(tzinfo=None) if last_check.tzinfo else last_check
                    
                    # Проверяем что заказ свежий
                    if order_date > last_check_normalized:
                        # FIX ЦЕНЫ: Если priceWithDiscount пришел 0, считаем сами
                        if order.get('priceWithDiscount', 0) == 0:
                            total = order.get('totalPrice', 0)
                            disc = order.get('discountPercent', 0)
                            order['priceWithDiscount'] = int(total * (1 - disc/100))
                        
                        new_orders.append(order)
                except Exception as e:
                    continue
                
            return new_orders

    async def get_sales_since(self, token: str, date_from: str) -> List[Dict]:
        """Получение выкупов (продаж) с исправлением цен"""
        url = f"{self.URLS['statistics']}/api/v1/supplier/sales"
        params = {"dateFrom": date_from, "flag": 0}
        headers = {"Authorization": token}
        
        data = await self._request_with_retry(None, url, headers, params=params)
        
        result = []
        if isinstance(data, list):
            for sale in data:
                # FIX: Если цена 0, пересчитываем
                if sale.get('priceWithDiscount', 0) == 0:
                    total = sale.get('totalPrice', 0)
                    disc = sale.get('discountPercent', 0)
                    sale['priceWithDiscount'] = int(total * (1 - disc/100))
                result.append(sale)
                
        return result

    async def get_sales_funnel_full(self, token: str, date_from: str, date_to: str, nm_ids: List[int] = None) -> Dict[str, Any]:
        """
        Получение ПОЛНОЙ воронки (Просмотры -> Корзины -> Заказы -> Выкупы) 
        через Analytics API v3.
        """
        # Analytics API URL (V3 Standard replacement)
        url = "https://seller-analytics-api.wildberries.ru/api/analytics/v3/sales-funnel/products"
        
        # FIX: API v3 требует формат YYYY-MM-DD. Обрезаем время, если оно есть.
        if len(date_from) > 10: date_from = date_from[:10]
        if len(date_to) > 10: date_to = date_to[:10]

        # Используем токен из self, если переданный пустой (хотя обычно они совпадают)
        headers = {"Authorization": token}
        
        res = {
            "visitors": 0,
            "addToCart": 0,
            "ordersCount": 0,
            "ordersSum": 0,
            "buyoutsCount": 0,
            "buyoutsSum": 0
        }

        # v3 uses limit/offset instead of page
        offset = 0
        limit = 100 
        is_more = True
        
        async with aiohttp.ClientSession() as session:
            try:
                while is_more:
                    payload = {
                        "selectedPeriod": {
                            "start": date_from,
                            "end": date_to
                        },
                        "nmIds": nm_ids if nm_ids else [], 
                        "limit": limit,
                        "offset": offset
                    }
                    
                    # Manual request logic (mixin lacks _request)
                    data = None
                    for attempt in range(5):
                        try:
                            async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    break
                                elif resp.status == 429:
                                    wait_time = 3 ** (attempt + 1)
                                    logger.warning(f"Rate limit 429 in Mixin Funnel. Waiting {wait_time}s...")
                                    await asyncio.sleep(wait_time)
                                    continue
                                else:
                                    logger.warning(f"Funnel API Error {resp.status}")
                                    break
                        except Exception as req_err:
                            logger.error(f"Funnel request error attempt {attempt}: {req_err}")
                            await asyncio.sleep(1)
                    
                    if not data or not isinstance(data, dict):
                        logger.warning(f"Empty or invalid data received from Funnel API v3. Data: {data}")
                        break
                    
                    # Check for error in response body structure
                    if "error" in data:
                          logger.error(f"Funnel API v3 Error Body: {data}")
                          break

                    # Response structure check: { "data": { "cards": [] } } OR { "data": { "products": [] } }
                    response_data = data.get("data", {})
                    if not response_data:
                          # Some APIs return cards directly or in a different wrapper on error/empty
                          logger.warning(f"No 'data' field in response. Full response: {data}")
                          break

                    # Try to get items from 'products' (new v3) or 'cards' (old v3/docs)
                    items = response_data.get("products", [])
                    if not items:
                        items = response_data.get("cards", [])
                    
                    if not items:
                        # Log only if really no items found to avoid spam if it's just end of list
                        if offset == 0:
                              logger.info(f"No products/cards found in Funnel API v3 response. Offset: {offset}. Payload: {payload}. Response keys: {data.keys()}. Data keys: {response_data.keys()}")
                        is_more = False
                        break
                    
                    for c in items:
                        # UPDATED MAPPING FOR V3 BASED ON LOGS
                        # 'statistic' (singular) -> 'selected'
                        stats = c.get("statistic", {}).get("selected", {})
                        
                        res["visitors"] += stats.get("openCount", 0)       # V3: openCount
                        res["addToCart"] += stats.get("cartCount", 0)      # V3: cartCount
                        res["ordersCount"] += stats.get("orderCount", 0)   # V3: orderCount
                        res["ordersSum"] += stats.get("orderSum", 0)       # V3: orderSum
                        res["buyoutsCount"] += stats.get("buyoutCount", 0) # V3: buyoutCount
                        res["buyoutsSum"] += stats.get("buyoutSum", 0)     # V3: buyoutSum
                    
                    offset += limit
                    if offset > 5000: break # Safety break
                    
                    # Safety sleep to respect rate limits between pages (3 req/min = 1 req / 20s ideally, but let's try 5s)
                    await asyncio.sleep(5) 

                return res
                
            except Exception as e:
                logger.error(f"Failed to fetch full sales funnel in API class: {e}")
                return {}

    async def get_statistics_today(self, token: str) -> Dict[str, Any]:
        """
        Сводная статистика за сегодня (ИСПРАВЛЕННАЯ).
        """
        today_date = datetime.now()
        # Для V1 API (Заказы/Продажи) нужно точное время начала дня
        today_start = today_date.replace(hour=0, minute=0, second=0, microsecond=0)
        today_str_v1 = today_start.strftime("%Y-%m-%dT%H:%M:%S")
        
        # Для V3 API (Воронка) нужна дата YYYY-MM-DD
        funnel_date = today_date.strftime("%Y-%m-%d")
        
        try:
            async with aiohttp.ClientSession() as session:
                # 1. Заказы и Продажи (V1)
                # use_cache=False чтобы получать актуальные данные при каждом запросе бота
                orders_task = self._get_orders_mixin(session, token, today_str_v1, use_cache=False)
                sales_task = self._get_sales_mixin(session, token, today_str_v1, use_cache=False)
                
                # 2. Воронка (V3)
                funnel_task = self.get_sales_funnel_full(token, funnel_date, funnel_date)
                
                results = await asyncio.gather(orders_task, sales_task, funnel_task, return_exceptions=True)
                
                orders_res = results[0] if not isinstance(results[0], Exception) else {}
                sales_res = results[1] if not isinstance(results[1], Exception) else {}
                funnel_res = results[2] if not isinstance(results[2], Exception) else {}

                # Извлекаем данные с защитой от None
                orders_sum = orders_res.get("sum", 0) if isinstance(orders_res, dict) else 0
                orders_count = orders_res.get("count", 0) if isinstance(orders_res, dict) else 0
                
                sales_sum = sales_res.get("sum", 0) if isinstance(sales_res, dict) else 0
                sales_count = sales_res.get("count", 0) if isinstance(sales_res, dict) else 0
                
                visitors = 0
                addToCart = 0
                if isinstance(funnel_res, dict):
                    visitors = funnel_res.get("visitors", 0)
                    addToCart = funnel_res.get("addToCart", 0)
            
            return {
                "orders_sum": orders_sum,
                "orders_count": orders_count,
                "sales_sum": sales_sum,
                "sales_count": sales_count,
                "visitors": visitors,
                "addToCart": addToCart
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
                     if resp.status == 200:
                         data = await resp.json()
                     else:
                         data = []

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

    # --- ИСПРАВЛЕННЫЕ MIXIN МЕТОДЫ (С ФИКСОМ ЦЕНЫ И ДАТ) ---

    async def _get_orders_mixin(self, session, token: str, date_from: str, use_cache=True):
        url = "https://statistics-api.wildberries.ru/api/v1/supplier/orders"
        params = {"dateFrom": date_from, "flag": 0} 
        headers = {"Authorization": token}
        
        if hasattr(self, '_get_cached_or_request'):
            data = await self._get_cached_or_request(session, url, headers, params, use_cache=use_cache)
        else:
             async with session.get(url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json() 
                else: 
                    data = []
        
        if not data:
            return {"count": 0, "sum": 0, "items": []}
        
        if isinstance(data, list):
            valid_orders = []
            total_sum = 0.0
            
            # Фильтруем заказы именно по дате
            try:
                check_date = datetime.strptime(date_from[:10], "%Y-%m-%d").date()
            except:
                check_date = datetime.now().date()
            
            for x in data:
                if x.get("isCancel"): continue
                
                # Проверка даты
                try:
                    order_dt = datetime.strptime(x["date"][:10], "%Y-%m-%d").date()
                    if order_dt < check_date: continue
                except: pass

                # --- FIX: РАСЧЕТ ЦЕНЫ ---
                price = x.get("priceWithDiscount", 0)
                if price == 0:
                    base = x.get("totalPrice", 0)
                    disc = x.get("discountPercent", 0)
                    price = int(base * (1 - disc/100))
                
                total_sum += price
                x["priceWithDiscount"] = price # Update inplace just in case
                valid_orders.append(x)
                
            return {"count": len(valid_orders), "sum": int(total_sum), "items": valid_orders}
        return {"count": 0, "sum": 0, "items": []}

    async def _get_sales_mixin(self, session, token: str, date_from: str, use_cache=True):
        """Внутренний метод для получения продаж (v1/supplier/sales)"""
        url = "https://statistics-api.wildberries.ru/api/v1/supplier/sales"
        params = {"dateFrom": date_from, "flag": 0}
        headers = {"Authorization": token}
        
        if hasattr(self, '_get_cached_or_request'):
            data = await self._get_cached_or_request(session, url, headers, params, use_cache=use_cache)
        else:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                else:
                    data = []
        
        if not data:
            return {"count": 0, "sum": 0, "items": []}
        
        if isinstance(data, list):
            valid_sales = []
            total_sum = 0.0
            
            try:
                check_date = datetime.strptime(date_from[:10], "%Y-%m-%d").date()
            except:
                check_date = datetime.now().date()

            for x in data:
                if x.get("isStorno"): continue
                if str(x.get("saleID", "")).startswith("R"): continue
                
                try:
                    sale_dt = datetime.strptime(x["date"][:10], "%Y-%m-%d").date()
                    if sale_dt < check_date: continue
                except: pass

                # --- FIX: РАСЧЕТ ЦЕНЫ ---
                price = x.get("priceWithDiscount", 0)
                if price == 0:
                    base = x.get("totalPrice", 0)
                    disc = x.get("discountPercent", 0)
                    price = int(base * (1 - disc/100))
                
                total_sum += price
                x["priceWithDiscount"] = price
                valid_sales.append(x)

            return {"count": len(valid_sales), "sum": int(total_sum), "items": valid_sales}
        return {"count": 0, "sum": 0, "items": []}


class WBStatisticsAPI(WBStatisticsMixin):
    """
    Standalone Client for Wildberries Statistics API.
    Used by Supply Service (New Logic) and Analytics Service.
    """
    BASE_URL = "https://statistics-api.wildberries.ru"

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def _request(self, endpoint: str, params: Dict[str, Any] = None, method: str = "GET", json_data: Any = None, retries: int = 5) -> Any:
        """
        Универсальный метод запроса. Поддерживает полные URL и POST.
        """
        # Если endpoint начинается с http, используем его как полный URL, иначе добавляем BASE_URL
        if endpoint.startswith("http"):
            url = endpoint
        else:
            url = f"{self.BASE_URL}{endpoint}"

        async with aiohttp.ClientSession() as session:
            for attempt in range(retries):
                try:
                    async with session.request(method, url, headers=self.headers, params=params, json=json_data, timeout=60) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        elif resp.status == 429:
                            # Aggressive backoff: 3s, 9s, 27s, 81s, 243s
                            wait_time = 3 ** (attempt + 1)
                            logger.warning(f"Rate limit 429. Waiting {wait_time}s...")
                            await asyncio.sleep(wait_time)
                            continue
                        elif resp.status == 401:
                            logger.error("WB API Unauthorized.")
                            raise HTTPException(status_code=401, detail="Invalid WB Token")
                        elif resp.status == 404:
                            # Log the body to understand why it is 404
                            error_text = await resp.text()
                            logger.warning(f"WB API 404 (Deprecated/Not Found) at {url}. Response: {error_text}")
                            return []
                        elif resp.status == 400:
                             error_text = await resp.text()
                             logger.error(f"WB API Error 400: {error_text}")
                             return []
                        else:
                            text = await resp.text()
                            logger.error(f"WB API Error {resp.status}: {text}")
                            return []
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout on {url}. Retrying...")
                except Exception as e:
                    logger.error(f"Request failed: {e}")
                    
        return []

    async def get_stocks(self) -> List[Dict[str, Any]]:
        date_from = "2023-01-01T00:00:00"
        return await self._request("/api/v1/supplier/stocks", params={"dateFrom": date_from})

    async def get_orders(self, days: int = 30) -> List[Dict[str, Any]]:
        date_from = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        return await self._request("/api/v1/supplier/orders", params={"dateFrom": date_from, "flag": 0})

    async def get_sales(self, days: int = 30) -> List[Dict[str, Any]]:
        date_from = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
        return await self._request("/api/v1/supplier/sales", params={"dateFrom": date_from, "flag": 0})

    async def get_turnover_data(self) -> Dict[str, Any]:
        stocks, orders = await asyncio.gather(
            self.get_stocks(),
            self.get_orders(days=30)
        )
        return {"stocks": stocks, "orders": orders}

    # --- Метод для воронки (перенесен из Mixin для использования в WBStatisticsAPI) ---
    async def get_sales_funnel_full(self, token: str, date_from: str, date_to: str, nm_ids: List[int] = None) -> Dict[str, Any]:
        """
        Получение ПОЛНОЙ воронки (Просмотры -> Корзины -> Заказы -> Выкупы) 
        через Analytics API v3.
        Аргумент token здесь для совместимости, используется self.token.
        """
        # Analytics API URL (V3 Standard replacement)
        url = "https://seller-analytics-api.wildberries.ru/api/analytics/v3/sales-funnel/products"
        
        # FIX: API v3 требует формат YYYY-MM-DD. Обрезаем время, если оно есть.
        if len(date_from) > 10: date_from = date_from[:10]
        if len(date_to) > 10: date_to = date_to[:10]

        # Используем токен из self, если переданный пустой (хотя обычно они совпадают)
        headers = self.headers 
        
        res = {
            "visitors": 0,
            "addToCart": 0,
            "ordersCount": 0,
            "ordersSum": 0,
            "buyoutsCount": 0,
            "buyoutsSum": 0
        }

        # v3 uses limit/offset instead of page
        offset = 0
        limit = 100 
        is_more = True
        
        try:
            while is_more:
                payload = {
                    "selectedPeriod": {
                        "start": date_from,
                        "end": date_to
                    },
                    "nmIds": nm_ids if nm_ids else [], 
                    "limit": limit,
                    "offset": offset
                }
                
                data = await self._request(
                    endpoint=url,
                    method="POST",
                    json_data=payload,
                    retries=4
                )
                
                if not data or not isinstance(data, dict):
                    logger.warning(f"Empty or invalid data received from Funnel API v3. Data: {data}")
                    break
                
                # Check for error in response body structure
                if "error" in data:
                      logger.error(f"Funnel API v3 Error Body: {data}")
                      break

                # Response structure check: { "data": { "cards": [] } } OR { "data": { "products": [] } }
                response_data = data.get("data", {})
                if not response_data:
                      # Some APIs return cards directly or in a different wrapper on error/empty
                      logger.warning(f"No 'data' field in response. Full response: {data}")
                      break

                # Try to get items from 'products' (new v3) or 'cards' (old v3/docs)
                items = response_data.get("products", [])
                if not items:
                    items = response_data.get("cards", [])
                
                if not items:
                    # Log only if really no items found to avoid spam if it's just end of list
                    if offset == 0:
                          logger.info(f"No products/cards found in Funnel API v3 response. Offset: {offset}. Payload: {payload}. Response keys: {data.keys()}. Data keys: {response_data.keys()}")
                    is_more = False
                    break
                
                # --- DEBUG LOGGING START ---
                if offset == 0:
                    logger.info(f"V3 Funnel Item Structure Sample: {items[0]}")
                # --- DEBUG LOGGING END ---

                for c in items:
                    # UPDATED MAPPING FOR V3 BASED ON LOGS
                    # 'statistic' (singular) -> 'selected'
                    stats = c.get("statistic", {}).get("selected", {})
                    
                    res["visitors"] += stats.get("openCount", 0)       # V3: openCount
                    res["addToCart"] += stats.get("cartCount", 0)      # V3: cartCount
                    res["ordersCount"] += stats.get("orderCount", 0)   # V3: orderCount
                    res["ordersSum"] += stats.get("orderSum", 0)       # V3: orderSum
                    res["buyoutsCount"] += stats.get("buyoutCount", 0) # V3: buyoutCount
                    res["buyoutsSum"] += stats.get("buyoutSum", 0)     # V3: buyoutSum
                
                offset += limit
                if offset > 5000: break # Safety break
                
                # Safety sleep to respect rate limits between pages (3 req/min = 1 req / 20s ideally, but let's try 5s)
                await asyncio.sleep(5) 

            return res
            
        except Exception as e:
            logger.error(f"Failed to fetch full sales funnel in API class: {e}")
            return {}

    # --- НОВЫЙ МЕТОД ДЛЯ P&L: Реализация ---
    async def get_realization_reports(self, date_from: datetime, date_to: datetime) -> List[Dict[str, Any]]:
        """
        Получение финансового отчета (реализации).
        Используем V5 API, т.к. V1 deprecated.
        """
        # ИСПРАВЛЕНИЕ: V1 -> V5
        url = "/api/v5/supplier/reportDetailByPeriod"
        all_reports = []
        rrdid = 0
        
        # Защита от вечного цикла
        max_pages = 500 
        page = 0
        
        while page < max_pages:
            params = {
                "dateFrom": date_from.strftime("%Y-%m-%d"),
                "dateTo": date_to.strftime("%Y-%m-%d"),
                "limit": 10000,
                "rrdid": rrdid
            }
            
            # Используем _request который уже имеет ретраи
            data = await self._request(url, params=params)
            
            if not data:
                break
                
            # API может вернуть None вместо списка
            if not isinstance(data, list):
                logger.warning(f"Realization report API returned non-list: {type(data)}")
                break
                
            all_reports.extend(data)
            
            if len(data) < 10000:
                break
                
            # Берем rrd_id последнего элемента для пагинации
            last_item = data[-1]
            rrdid = last_item.get("rrd_id")
            
            if not rrdid:
                break
            
            page += 1
            # Пауза, чтобы не душить API
            await asyncio.sleep(0.5)
            
        return all_reports

    # --- ДОБАВЛЕННЫЙ МЕТОД ДЛЯ CALCULATE_TRANSIT ---
    async def calculate_transit(self, volume: int, origin: str = "Казань", destination: str = "Коледино", transit_rate: float = None):
        """
        Калькулятор транзита.
        volume: объем в литрах
        origin: откуда везем (не используется в расчете, справочно)
        destination: куда везем (для поиска тарифа)
        transit_rate: ставка транзита за литр
        """
        # Default transit rate if not provided (approx 4.5 rub/liter is common for transit)
        if transit_rate is None:
            transit_rate = 4.5

        # 1. Calculate Transit Cost (Your warehouse -> Transit Warehouse -> End Warehouse)
        # Usually: Delivery to transit point (user cost) + WB Transit Fee
        # WB Transit Fee = Volume * Rate
        transit_cost = volume * transit_rate

        # 2. Calculate Direct Cost (Your warehouse -> End Warehouse)
        # We need real tariffs for the Destination (e.g., Koledino)
        # URL: https://common-api.wildberries.ru/api/v1/tariffs/box
        
        direct_cost = 0
        dest_tariff = None
        
        try:
            # Fetch tariffs
            url = "https://common-api.wildberries.ru/api/v1/tariffs/box"
            today = datetime.now().strftime("%Y-%m-%d")
            params = {"date": today}
            
            data = await self._request(url, params=params) # _request handles full URLs now
            
            if data and 'response' in data and 'data' in data['response']:
                wh_list = data['response']['data'].get('warehouseList', [])
                for w in wh_list:
                    if w.get('warehouseName') == destination:
                        dest_tariff = w
                        break
                
                # Fallback to Koledino if destination not found
                if not dest_tariff:
                    for w in wh_list:
                        if w.get('warehouseName') == "Коледино":
                            dest_tariff = w
                            break
        except Exception as e:
            logger.error(f"Failed to fetch tariffs for calc: {e}")

        # Calculate Direct Cost based on tariff
        if dest_tariff:
            try:
                base = float(str(dest_tariff.get('boxDeliveryBase', '0')).replace(',', '.'))
                liter = float(str(dest_tariff.get('boxDeliveryLiter', '0')).replace(',', '.'))
                
                if volume <= 5:
                    direct_cost = base
                else:
                    direct_cost = base + (volume - 5) * liter
            except:
                direct_cost = volume * 15 # Fallback rough estimate
        else:
             direct_cost = volume * 15 # Fallback

        # 3. Formulate Result
        benefit = direct_cost - transit_cost
        
        return {
            "volume": volume,
            "transit": {
                "origin": origin,
                "rate": transit_rate,
                "total": round(transit_cost, 2)
            },
            "direct": {
                "destination": destination,
                "base": dest_tariff.get('boxDeliveryBase') if dest_tariff else "?",
                "rate": dest_tariff.get('boxDeliveryLiter') if dest_tariff else "?",
                "total": round(direct_cost, 2)
            },
            "benefit": round(benefit, 2),
            "is_profitable": benefit > 0,
            "recommendation": "Транзит выгоднее" if benefit > 0 else "Прямая поставка выгоднее"
        }