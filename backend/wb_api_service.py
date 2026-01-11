import logging
import aiohttp
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger("WB-API-Service")

class WBApiService:
    """
    Сервис для работы с официальным API Wildberries (Statistics API + Common API + Advert API).
    Внедрен механизм повторных запросов (Retry) и кэширования (In-Memory).
    """
    
    BASE_URL = "https://statistics-api.wildberries.ru/api/v1/supplier"
    COMMON_URL = "https://common-api.wildberries.ru/api/v1" # Тарифы, коэффициенты
    ADV_URL = "https://advert-api.wb.ru/adv/v1" # Реклама
    
    # In-Memory Cache: { "token_method_params": (timestamp, data) }
    _cache: Dict[str, Any] = {}
    _cache_ttl = 300 # 5 минут (TTL)

    async def _request_with_retry(self, session, url, headers, params=None, method='GET', json_data=None, retries=3):
        """
        Выполняет запрос с повторными попытками при 429/5xx ошибках.
        """
        backoff = 2 # Начальная задержка 2 секунды
        
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
                        logger.warning(f"WB API Rate Limit (429) on {url}. Retrying in {backoff}s...")
                        await asyncio.sleep(backoff)
                        backoff *= 2 # Экспоненциальная задержка
                    elif resp.status >= 500:
                        logger.warning(f"WB API Server Error ({resp.status}). Retrying...")
                        await asyncio.sleep(backoff)
                        backoff *= 2
                    else:
                        text = await resp.text()
                        # 401, 400 и т.д. - нет смысла повторять, логируем ошибку
                        logger.error(f"WB API Error {resp.status}: {text}")
                        return None
            except Exception as e:
                logger.error(f"Request failed: {e}")
                await asyncio.sleep(backoff)
        
        logger.error(f"Failed to fetch {url} after {retries} attempts.")
        return None

    def _get_cache_key(self, token, method, params):
        """Генерация уникального ключа для кэша"""
        token_part = token[-10:] if token else "none"
        param_str = json.dumps(params, sort_keys=True)
        return f"{token_part}:{method}:{param_str}"

    async def _get_cached_or_request(self, session, url, headers, params, use_cache=True):
        """
        Прослойка кэширования перед запросом.
        """
        if not use_cache:
            return await self._request_with_retry(session, url, headers, params)

        cache_key = self._get_cache_key(headers.get("Authorization"), url, params)
        
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if (datetime.now() - ts).total_seconds() < self._cache_ttl:
                # logger.info(f"Returning cached data for {url}")
                return data
        
        # Если в кэше нет или он протух - делаем реальный запрос
        data = await self._request_with_retry(session, url, headers, params)
        
        if data is not None:
            self._cache[cache_key] = (datetime.now(), data)
            
        return data

    async def check_token(self, token: str) -> bool:
        """Проверка валидности токена"""
        if not token: 
            return False
        
        url = f"{self.BASE_URL}/incomes"
        params = {"dateFrom": datetime.now().strftime("%Y-%m-%d")}
        headers = {"Authorization": token}
        
        async with aiohttp.ClientSession() as session:
            try:
                # Для проверки токена кэш отключаем, нужен актуальный статус
                async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                    if resp.status == 401:
                        return False
                    return True
            except Exception as e:
                logger.error(f"Token check error: {e}")
                return False

    async def get_dashboard_stats(self, token: str):
        """Сводка: Заказы сегодня и остатки"""
        if not token: return {"error": "Token not provided"}

        async with aiohttp.ClientSession() as session:
            today_str = datetime.now().strftime("%Y-%m-%dT00:00:00")
            
            # Используем кэш для дашборда, чтобы не нагружать API при частом обновлении UI
            orders_task = self._get_orders(session, token, today_str, use_cache=True)
            stocks_task = self._get_stocks(session, token, today_str, use_cache=True)
            
            orders_res, stocks_res = await asyncio.gather(orders_task, stocks_task)
            
            return {
                "orders_today": orders_res,
                "stocks": stocks_res
            }

    async def get_new_orders_since(self, token: str, last_check: datetime):
        """Получение новых заказов (без кэша, для уведомлений)"""
        if not last_check:
            last_check = datetime.now() - timedelta(hours=1)
        
        date_from_str = (last_check - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        
        async with aiohttp.ClientSession() as session:
            # Для "Дзынь!" кэш отключаем, нужны самые свежие данные
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
        """
        Получение списка остатков для Unit-экономики.
        Кэшируем агрессивно (на 5 минут), так как список большой и меняется медленно.
        """
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
        Получение коэффициентов приемки (для Supply Chain).
        """
        # URL для будущего использования
        url = f"{self.COMMON_URL}/tariffs/box"
        headers = {"Authorization": token} if token else {}
        
        # В данный момент возвращаем расширенную симуляцию для MVP
        return [
            {"warehouse": "Коледино", "coefficient": 1, "transit_time": "1 день", "price_per_liter": 30},
            {"warehouse": "Электросталь", "coefficient": 5, "transit_time": "1 день", "price_per_liter": 150},
            {"warehouse": "Казань", "coefficient": 0, "transit_time": "2 дня", "price_per_liter": 20},
            {"warehouse": "Тула", "coefficient": 2, "transit_time": "1 день", "price_per_liter": 60},
            {"warehouse": "Краснодар", "coefficient": 0, "transit_time": "3 дня", "price_per_liter": 25},
            {"warehouse": "Санкт-Петербург", "coefficient": 1, "transit_time": "2 дня", "price_per_liter": 35},
        ]

    async def calculate_transit(self, liters: int, destination: str = "Koledino"):
        """
        [NEW] Калькулятор транзита (Supply Chain).
        """
        # Базовые тарифы
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

    # --- ADVERT API METHODS (NEW) ---

    async def get_advert_campaigns(self, token: str):
        """Получение списка рекламных кампаний"""
        url = f"{self.ADV_URL}/promotion/count"
        headers = {"Authorization": token}
        
        # Mocking for MVP until real endpoint is fully accessible/documented in context
        # In prod: use self._request_with_retry
        return [
            {"id": 123456, "name": "Платья Лето", "status": 9, "type": 6},
            {"id": 123457, "name": "Блузки Офис", "status": 9, "type": 6},
            {"id": 123458, "name": "Брюки", "status": 11, "type": 6} # Paused
        ]

    async def get_advert_stats(self, token: str, campaign_id: int):
        """Получение статистики кампании (CTR, CR, Spend)"""
        # url = f"{self.ADV_URL}/fullstat"
        # Mock data based on real WB logic
        return {
            "views": 1000,
            "clicks": 50,
            "ctr": 5.0, # 5%
            "spend": 500,
            "cr": 2.1 # Conversion Rate
        }

    async def get_current_bid_info(self, token: str, campaign_id: int):
        """Получение текущей ставки и места"""
        # Mock data
        return {
            "campaignId": campaign_id,
            "price": 150, # Current Bid
            "position": 5 # Current Position
        }

    async def update_bid(self, token: str, campaign_id: int, new_bid: int):
        """Обновление ставки"""
        url = f"{self.ADV_URL}/save"
        headers = {"Authorization": token}
        logger.info(f"API: Updating bid for {campaign_id} to {new_bid}")
        # async with aiohttp.ClientSession() as session:
        #     return await self._request_with_retry(session, url, headers, method='POST', json_data={"id": campaign_id, "price": new_bid})
        return {"status": "ok"}


    async def _get_orders(self, session, token: str, date_from: str, use_cache=True):
        url = f"{self.BASE_URL}/orders"
        params = {"dateFrom": date_from}
        headers = {"Authorization": token}
        
        data = await self._get_cached_or_request(session, url, headers, params, use_cache=use_cache)
        
        if not data:
            return {"count": 0, "sum": 0, "items": []}
        
        # Агрегация данных
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

wb_api_service = WBApiService()