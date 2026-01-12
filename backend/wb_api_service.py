import logging
import aiohttp
import asyncio
import json
import socket
import os
from aiohttp import AsyncResolver
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger("WB-API-Service")

class WBApiService:
    """
    Сервис для работы с официальным API Wildberries.
    Использует принудительный резолвинг DNS через Google (8.8.8.8) для стабильной работы в Docker.
    """
    
    BASE_URL = os.getenv("WB_STATS_URL", "https://statistics-api.wildberries.ru/api/v1/supplier")
    COMMON_URL = os.getenv("WB_COMMON_URL", "https://common-api.wildberries.ru/api/v1") 
    ADV_URL = os.getenv("WB_ADV_URL", "https://advert-api.wb.ru/adv/v1") 
    QUESTIONS_URL = os.getenv("WB_QUESTIONS_URL", "https://feedbacks-api.wildberries.ru/api/v1")
    
    _cache: Dict[str, Any] = {}
    _cache_ttl = 300 

    def _get_connector(self):
        """
        Создает TCP коннектор с:
        1. Принудительным IPv4 (socket.AF_INET)
        2. Отключенной проверкой SSL (ssl=False)
        3. Явным резолвером Google DNS (8.8.8.8), чтобы обойти глюки Docker DNS
        """
        resolver = AsyncResolver(nameservers=["8.8.8.8", "1.1.1.1"])
        return aiohttp.TCPConnector(
            family=socket.AF_INET, 
            ssl=False, 
            resolver=resolver
        )

    async def _request_with_retry(self, url, headers, params=None, method='GET', json_data=None, retries=3):
        backoff = 1
        req_headers = headers.copy()
        if "User-Agent" not in req_headers:
            req_headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        for attempt in range(retries):
            try:
                # Важно: создаем коннектор внутри цикла или на каждый запрос, чтобы резолвер работал корректно
                async with aiohttp.ClientSession(connector=self._get_connector()) as session:
                    if method == 'GET':
                        coro = session.get(url, headers=req_headers, params=params, timeout=15)
                    else:
                        coro = session.post(url, headers=req_headers, json=json_data, timeout=15)

                    async with coro as resp:
                        if resp.status == 200:
                            return await resp.json()
                        elif resp.status == 429:
                            logger.warning(f"WB API Rate Limit (429): {url}")
                            await asyncio.sleep(backoff)
                            backoff *= 2
                            continue
                        elif resp.status == 204:
                            return None
                        else:
                            text = await resp.text()
                            # Логируем только серверные ошибки
                            if resp.status >= 500:
                                logger.warning(f"WB API Server Error {resp.status} at {url}: {text[:100]}")
                            elif resp.status != 401:
                                # 401 - это частая ситуация при проверке токена, не засоряем лог уровнем error
                                logger.debug(f"WB API Client Error {resp.status} at {url}: {text[:100]}")
                            
                            if resp.status < 500 and resp.status != 429:
                                return None 
                                
            except aiohttp.ClientConnectorError as e:
                logger.error(f"DNS/Connection Error ({attempt+1}/{retries}) to {url}: {e}")
                await asyncio.sleep(backoff)
                backoff *= 2
            except Exception as e:
                logger.error(f"Request Error ({attempt+1}/{retries}): {e}")
                await asyncio.sleep(backoff)
        
        return None

    async def check_token(self, token: str) -> bool:
        """Простая проверка валидности (для сохранения)"""
        # Проверяем через aiohttp, чтобы работал DNS фикс
        scopes = await self.get_token_scopes(token)
        return any(scopes.values())

    async def get_token_scopes(self, token: str) -> Dict[str, bool]:
        """
        Полная диагностика токена по всем API.
        Переписано на aiohttp для поддержки кастомного DNS резолвера.
        """
        if not token: 
            return {"statistics": False, "standard": False, "promotion": False, "questions": False}

        headers = {
            "Authorization": token,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # Определяем вспомогательную функцию для проверки одного URL
        async def check_url(url, params=None, method='GET', json_data=None):
            try:
                # Используем _request_with_retry, так как он уже содержит DNS фикс
                res = await self._request_with_retry(url, headers, params, method, json_data, retries=1)
                # Если вернулся результат (даже пустой список/словарь) - доступ есть. Если None - ошибка/нет доступа.
                return res is not None
            except:
                return False

        # Запускаем проверки параллельно
        # 1. Статистика (Склады)
        task_stats = check_url(f"{self.BASE_URL}/stocks", {"dateFrom": datetime.now().strftime("%Y-%m-%d")})
        
        # 2. Стандартный (Тарифы)
        task_std = check_url(f"{self.COMMON_URL}/tariffs/box", {"date": datetime.now().strftime("%Y-%m-%d")})
        
        # 3. Реклама (Счетчик кампаний)
        task_promo = check_url(f"{self.ADV_URL}/promotion/count")
        
        # 4. Вопросы
        task_questions = check_url(f"{self.QUESTIONS_URL}/questions", {"isAnswered": "false", "take": 1})

        results = await asyncio.gather(task_stats, task_std, task_promo, task_questions)
        
        return {
            "statistics": results[0],
            "standard": results[1],
            "promotion": results[2],
            "questions": results[3]
        }

    def _get_cache_key(self, token, method, params):
        token_part = token[-10:] if token else "none"
        param_str = json.dumps(params, sort_keys=True)
        return f"{token_part}:{method}:{param_str}"

    async def _get_cached_or_request(self, url, headers, params, use_cache=True):
        if not use_cache:
            return await self._request_with_retry(url, headers, params)

        cache_key = self._get_cache_key(headers.get("Authorization"), url, params)
        
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if (datetime.now() - ts).total_seconds() < self._cache_ttl:
                return data
        
        data = await self._request_with_retry(url, headers, params)
        
        if data is not None:
            self._cache[cache_key] = (datetime.now(), data)
            
        return data

    async def get_dashboard_stats(self, token: str):
        if not token: return {"orders_today": {"sum": 0, "count": 0}, "stocks": {"total_quantity": 0}}
        today_str = datetime.now().strftime("%Y-%m-%dT00:00:00")
        orders_task = self._get_orders(token, today_str, use_cache=True)
        stocks_task = self._get_stocks(token, today_str, use_cache=True)
        orders_res, stocks_res = await asyncio.gather(orders_task, stocks_task)
        return {"orders_today": orders_res, "stocks": stocks_res}

    async def get_new_orders_since(self, token: str, last_check: datetime):
        if not last_check: last_check = datetime.now() - timedelta(hours=1)
        date_from_str = (last_check - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        orders_data = await self._get_orders(token, date_from_str, use_cache=False)
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
        params = {"dateFrom": today}
        headers = {"Authorization": token}
        data = await self._get_cached_or_request(url, headers, params, use_cache=True)
        return data if isinstance(data, list) else []

    async def get_warehouse_coeffs(self, token: str):
        url = f"{self.COMMON_URL}/tariffs/box"
        headers = {"Authorization": token} if token else {}
        today = datetime.now().strftime("%Y-%m-%d")
        params = {"date": today}
        data = await self._get_cached_or_request(url, headers, params, use_cache=True)
        if data and isinstance(data, dict):
             if 'response' in data and 'data' in data['response']:
                 return data['response']['data']
        return []

    async def calculate_transit(self, liters: int, destination: str = "Koledino"):
        direct_base, direct_rate = 1500, 30
        transit_base, transit_rate, transit_log = 500, 10, 1000 
        return {
            "destination": destination,
            "direct": {"rate": direct_rate, "total": direct_base + (liters * direct_rate)},
            "transit_kazan": {"rate": transit_rate, "logistics": transit_log, "total": transit_base + (liters * transit_rate) + transit_log}
        }

    async def get_advert_campaigns(self, token: str):
        url_ids = f"{self.ADV_URL}/promotion/adverts"
        headers = {"Authorization": token}
        ids_payload = {"status": [9, 11], "type": [6, 8, 9]}
        campaigns_list = await self._request_with_retry(url_ids, headers, method='POST', json_data=ids_payload)
        if not campaigns_list: return []
        results = []
        for camp in campaigns_list:
            if isinstance(camp, dict):
                results.append({
                    "id": camp.get("advertId"),
                    "name": camp.get("name", f"Кампания {camp.get('advertId')}"),
                    "status": camp.get("status"),
                    "type": camp.get("type"),
                    "changeTime": camp.get("changeTime")
                })
        return results

    async def get_advert_stats(self, token: str, campaign_id: int):
        url = f"{self.ADV_URL}/fullstat"
        headers = {"Authorization": token}
        payload = [{"id": campaign_id}]
        data = await self._request_with_retry(url, headers, method='POST', json_data=payload)
        if data and isinstance(data, list) and len(data) > 0:
            stat = data[0]
            return {
                "views": stat.get("views", 0),
                "clicks": stat.get("clicks", 0),
                "ctr": stat.get("ctr", 0),
                "spend": stat.get("sum", 0),
                "cr": 0
            }
        return None

    async def get_current_bid_info(self, token: str, campaign_id: int):
        # Используем V0 API, он иногда стабильнее для бидов
        url = "https://advert-api.wb.ru/adv/v0/advert" 
        
        headers = {"Authorization": token}
        params = {"id": campaign_id}
        data = await self._request_with_retry(url, headers, params=params)
        if data and "params" in data:
            params_list = data.get("params", [])
            if params_list:
                p = params_list[0]
                return {
                    "campaignId": campaign_id,
                    "price": p.get("price", 0),
                    "subjectId": p.get("subjectId")
                }
        return {"campaignId": campaign_id, "price": 0, "position": 0}

    async def update_bid(self, token: str, campaign_id: int, new_bid: int):
        url = "https://advert-api.wb.ru/adv/v0/save"
        headers = {"Authorization": token}
        current_info = await self.get_current_bid_info(token, campaign_id)
        if not current_info or "subjectId" not in current_info: return
        payload = {
            "advertId": campaign_id,
            "type": 6, 
            "params": [{"subjectId": current_info["subjectId"], "price": new_bid}]
        }
        await self._request_with_retry(url, headers, method='POST', json_data=payload)

    async def _get_orders(self, token: str, date_from: str, use_cache=True):
        url = f"{self.BASE_URL}/orders"
        params = {"dateFrom": date_from}
        headers = {"Authorization": token}
        data = await self._get_cached_or_request(url, headers, params, use_cache=use_cache)
        if not data: return {"count": 0, "sum": 0, "items": []}
        if isinstance(data, list):
            valid_orders = [x for x in data if not x.get("isCancel")]
            total_sum = sum(item.get("priceWithDiscount", 0) for item in valid_orders)
            return {"count": len(valid_orders), "sum": int(total_sum), "items": valid_orders}
        return {"count": 0, "sum": 0, "items": []}

    async def _get_stocks(self, token: str, date_from: str, use_cache=True):
        url = f"{self.BASE_URL}/stocks"
        params = {"dateFrom": date_from}
        headers = {"Authorization": token}
        data = await self._get_cached_or_request(url, headers, params, use_cache=use_cache)
        if not data: return {"total_quantity": 0}
        if isinstance(data, list):
            total_qty = sum(item.get("quantity", 0) for item in data)
            return {"total_quantity": total_qty}
        return {"total_quantity": 0}

wb_api_service = WBApiService()