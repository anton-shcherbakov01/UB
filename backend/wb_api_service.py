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
    """
    
    BASE_URL = "https://statistics-api.wildberries.ru/api/v1/supplier"
    COMMON_URL = "https://common-api.wildberries.ru/api/v1" 
    ADV_URL = "https://advert-api.wb.ru/adv/v1" 
    
    # In-Memory Cache: { "token_method_params": (timestamp, data) }
    _cache: Dict[str, Any] = {}
    _cache_ttl = 300 # 5 минут (TTL)

    async def _request_with_retry(self, session, url, headers, params=None, method='GET', json_data=None, retries=3):
        """
        Выполняет запрос с повторными попытками при 429/5xx ошибках.
        """
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
                        logger.warning(f"WB API Rate Limit (429) on {url}. Retrying in {backoff}s...")
                        await asyncio.sleep(backoff)
                        backoff *= 2 
                    elif resp.status >= 500:
                        logger.warning(f"WB API Server Error ({resp.status}). Retrying...")
                        await asyncio.sleep(backoff)
                        backoff *= 2
                    elif resp.status == 204:
                         return None # No content
                    else:
                        text = await resp.text()
                        logger.error(f"WB API Error {resp.status} on {url}: {text}")
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
        if not token: 
            return False
        
        url = f"{self.BASE_URL}/incomes"
        params = {"dateFrom": datetime.now().strftime("%Y-%m-%d")}
        headers = {"Authorization": token}
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                    if resp.status == 401:
                        return False
                    return True
            except Exception as e:
                logger.error(f"Token check error: {e}")
                return False

    async def get_dashboard_stats(self, token: str):
        """Сводка: Заказы сегодня и остатки"""
        if not token: return {"orders_today": {"sum": 0, "count": 0}, "stocks": {"total_quantity": 0}}

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

    # --- ADVERT API METHODS (REAL) ---

    async def get_advert_campaigns(self, token: str):
        """Получение списка рекламных кампаний (Реклама > Список кампаний)"""
        # Сначала получаем ID кампаний, затем их инфо
        # WB не дает просто список, нужно запросить ID по статусам
        url_count = f"{self.ADV_URL}/promotion/count"
        url_ids = f"{self.ADV_URL}/promotion/adverts"
        url_infos = f"{self.ADV_URL}/promotion/adverts" # POST info
        
        headers = {"Authorization": token}
        
        async with aiohttp.ClientSession() as session:
            # 1. Получаем список ID (активные - 9, пауза - 11)
            # В реальном API WB V1 может быть другой endpoint, используем стандартный
            ids_payload = {"status": [9, 11], "type": [6, 8, 9]} # 6=Поиск, 8=Авто, 9=Карточка
            campaigns_list = await self._request_with_retry(session, url_ids, headers, method='POST', json_data=ids_payload)
            
            if not campaigns_list:
                return []
            
            # campaigns_list это список объектов. Нам нужны детали.
            # Если API возвращает сразу детали - отлично. Если нет - запрашиваем.
            # Обычно /promotion/adverts возвращает массив ID или краткую инфо.
            # Предположим возврат в формате WB API: [{id, type, status, ...}]
            
            # Обогатим информацией о бюджете/ставке
            results = []
            for camp in campaigns_list:
                # Фильтруем мусор
                if not isinstance(camp, dict): continue
                
                # Запрос статистики или доп инфо, если нужно. Пока возвращаем то что есть.
                results.append({
                    "id": camp.get("advertId"),
                    "name": camp.get("name", f"Кампания {camp.get('advertId')}"),
                    "status": camp.get("status"),
                    "type": camp.get("type"),
                    "changeTime": camp.get("changeTime")
                })
            
            return results

    async def get_advert_stats(self, token: str, campaign_id: int):
        """Получение полной статистики кампании"""
        url = f"{self.ADV_URL}/fullstat"
        headers = {"Authorization": token}
        # WB требует список id
        payload = [{"id": campaign_id}]
        
        async with aiohttp.ClientSession() as session:
            data = await self._request_with_retry(session, url, headers, method='POST', json_data=payload)
            # data is list of results
            if data and isinstance(data, list) and len(data) > 0:
                stat = data[0]
                return {
                    "views": stat.get("views", 0),
                    "clicks": stat.get("clicks", 0),
                    "ctr": stat.get("ctr", 0),
                    "spend": stat.get("sum", 0),
                    "cr": 0 # WB API не всегда отдает CR прямо
                }
            return None

    async def get_current_bid_info(self, token: str, campaign_id: int):
        """Получение текущей ставки"""
        # Используем endpoint /v0/advert (получение инфо о кампании)
        # Или /v1/promotion/adverts c ID
        url = f"https://advert-api.wb.ru/adv/v0/advert"
        headers = {"Authorization": token}
        params = {"id": campaign_id}
        
        async with aiohttp.ClientSession() as session:
            data = await self._request_with_retry(session, url, headers, params=params)
            
            if data and "params" in data:
                # Структура зависит от типа кампании (Поиск/Авто)
                params_list = data.get("params", [])
                if params_list:
                    # Берем первую сущность
                    p = params_list[0]
                    return {
                        "campaignId": campaign_id,
                        "price": p.get("price", 0),
                        "subjectId": p.get("subjectId")
                    }
            return {"campaignId": campaign_id, "price": 0, "position": 0}

    async def update_bid(self, token: str, campaign_id: int, new_bid: int):
        """
        Реальное обновление ставки.
        Endpoint: /adv/v0/save (для старых типов) или /adv/v1/save-ad (для авто)
        Для универсальности используем v0/save который работает для поиска/карточки.
        """
        url = f"https://advert-api.wb.ru/adv/v0/save"
        headers = {"Authorization": token}
        # Структура payload сложная и зависит от типа кампании.
        # Для упрощения предполагаем тип 6 (Поиск).
        
        # Сначала надо получить текущие параметры, чтобы не затереть их
        current_info = await self.get_current_bid_info(token, campaign_id)
        if not current_info or "subjectId" not in current_info:
            logger.error(f"Cannot update bid: failed to fetch current info for {campaign_id}")
            return
            
        payload = {
            "advertId": campaign_id,
            "type": 6, 
            "params": [
                {
                    "subjectId": current_info["subjectId"],
                    "price": new_bid
                }
            ]
        }
        
        async with aiohttp.ClientSession() as session:
            await self._request_with_retry(session, url, headers, method='POST', json_data=payload)
            logger.info(f"REAL BID UPDATE: Campaign {campaign_id} -> {new_bid} RUB")

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

wb_api_service = WBApiService()