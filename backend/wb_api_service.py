import logging
import aiohttp
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger("WB-API-Service")

class WBApiService:
    """
    Сервис для работы с официальным API Wildberries (Statistics API).
    Добавлено: Retry-механизм и простое In-Memory кэширование.
    """
    
    BASE_URL = "https://statistics-api.wildberries.ru/api/v1/supplier"
    ADV_URL = "https://advert-api.wb.ru/adv/v1" # Для рекламы
    
    # Простой кэш в памяти: { "token_method_params": (timestamp, data) }
    _cache: Dict[str, Any] = {}
    _cache_ttl = 300 # 5 минут жизни кэша

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
                        # 401, 400 и т.д. - нет смысла повторять
                        logger.error(f"WB API Error {resp.status}: {await resp.text()}")
                        return None
            except Exception as e:
                logger.error(f"Request failed: {e}")
                await asyncio.sleep(backoff)
                
        logger.error(f"Failed to fetch {url} after {retries} attempts.")
        return None

    def _get_cache_key(self, token, method, params):
        """Генерация ключа кэша"""
        # Используем только последние символы токена для ключа, чтобы не хранить его целиком в логах если что
        token_part = token[-10:] if token else "none"
        param_str = json.dumps(params, sort_keys=True)
        return f"{token_part}:{method}:{param_str}"

    async def _get_cached_or_request(self, session, url, headers, params, use_cache=True):
        """
        Проверяет кэш перед запросом.
        """
        if not use_cache:
            return await self._request_with_retry(session, url, headers, params)

        cache_key = self._get_cache_key(headers.get("Authorization"), url, params)
        
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if (datetime.now() - ts).total_seconds() < self._cache_ttl:
                # logger.info(f"Returning cached data for {url}")
                return data
        
        # Если в кэше нет или протух - делаем запрос
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
                # Для проверки токена кэш не используем, нужен свежий статус
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
            
            # Используем кэш для дашборда, чтобы не долбить при каждом обновлении страницы
            orders_task = self._get_orders(session, token, today_str, use_cache=True)
            stocks_task = self._get_stocks(session, token, today_str, use_cache=True)
            
            orders_res, stocks_res = await asyncio.gather(orders_task, stocks_task)
            
            return {
                "orders_today": orders_res,
                "stocks": stocks_res
            }

    async def get_new_orders_since(self, token: str, last_check: datetime):
        """Получение новых заказов (без кэша, т.к. это воркер уведомлений)"""
        if not last_check:
            last_check = datetime.now() - timedelta(hours=1)
        
        date_from_str = (last_check - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        
        async with aiohttp.ClientSession() as session:
            # Для "Дзынь!" кэш отключаем, нужны свежие данные
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
        Кэшируем агрессивно (на 5-10 минут), так как список большой и меняется не часто.
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
        Используем метод /api/v1/supplier/incomes (Приемка) как прокси, 
        либо просто возвращаем моковые данные, если API не дает (официальный метод coeffs закрыт под ключ).
        Для MVP сделаем симуляцию на основе реальных складов.
        """
        # Note: Реальный API коэффициентов требует отдельного метода. 
        # Здесь мы возвращаем структуру для Supply Chain.
        
        return [
            {"warehouse": "Коледино", "coefficient": 1, "transit_time": "1-2 дня"},
            {"warehouse": "Электросталь", "coefficient": 5, "transit_time": "1-2 дня"},
            {"warehouse": "Казань", "coefficient": 0, "transit_time": "2-3 дня"},
            {"warehouse": "Тула", "coefficient": 2, "transit_time": "1-2 дня"},
        ]

    async def _get_orders(self, session, token: str, date_from: str, use_cache=True):
        url = f"{self.BASE_URL}/orders"
        params = {"dateFrom": date_from}
        headers = {"Authorization": token}
        
        data = await self._get_cached_or_request(session, url, headers, params, use_cache=use_cache)
        
        if not data:
            return {"count": 0, "sum": 0, "items": []}
        
        # Данные приходят списком, нам нужно агрегировать
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