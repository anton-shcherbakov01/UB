import logging
import asyncio
import aiohttp
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union

logger = logging.getLogger("WB-API-Base")

URLS = {
        "common": "https://common-api.wildberries.ru",
        "content": "https://content-api.wildberries.ru",
        "statistics": "https://statistics-api.wildberries.ru",
        "advert": "https://advert-api.wb.ru",
        "marketplace": "https://marketplace-api.wildberries.ru",
        "feedbacks": "https://feedbacks-api.wildberries.ru"
    }

class WBApiBase:
    """
    Базовый класс для работы с API WB.
    Содержит общие настройки, кэширование и метод отправки запросов.
    """
    
    BASE_URL = "https://statistics-api.wildberries.ru/api/v1/supplier"
    COMMON_URL = "https://common-api.wildberries.ru/api/v1" 
    ADV_URL = "https://advert-api.wb.ru/adv/v1" 
    # Добавили для Content API
    CONTENT_URL = "https://content-api.wildberries.ru/content/v2" 
    STATISTICS_URL = "https://statistics-api.wildberries.ru"
    
    # In-Memory Cache: { "token_method_params": (timestamp, data) }
    _cache: Dict[str, Any] = {}
    _cache_ttl = 300 # 5 минут (TTL)

    def __init__(self):
        # Короткий таймаут, чтобы проверка профиля не висела долго
        self.timeout = aiohttp.ClientTimeout(total=8)

    async def _request_with_retry(
        self, 
        session: Optional[aiohttp.ClientSession], 
        url: str, 
        headers: Dict[str, Any], 
        params: Optional[Dict] = None, 
        method: str = 'GET', 
        json_data: Optional[Dict] = None, 
        retries: int = 3
    ) -> Any:
        """
        Обертка: если сессии нет, создает временную.
        """
        if session is None:
            # Создаем новую сессию, если не передали (Context Manager)
            async with aiohttp.ClientSession() as new_session:
                return await self._execute_request(
                    new_session, url, headers, params, method, json_data, retries
                )
        else:
            # Используем переданную сессию
            return await self._execute_request(
                session, url, headers, params, method, json_data, retries
            )

    async def _execute_request(
        self, 
        session: aiohttp.ClientSession, 
        url: str, 
        headers: Dict[str, Any], 
        params: Optional[Dict], 
        method: str, 
        json_data: Optional[Dict], 
        retries: int
    ) -> Any:
        """
        Внутренняя логика запроса с ретраями.
        """
        backoff = 2
        
        for attempt in range(1, retries + 1):
            try:
                if method.upper() == 'GET':
                    coro = session.get(url, headers=headers, params=params, timeout=30)
                elif method.upper() == 'POST':
                    coro = session.post(url, headers=headers, json=json_data, params=params, timeout=30)
                elif method.upper() == 'PUT':
                    coro = session.put(url, headers=headers, json=json_data, params=params, timeout=30)
                else:
                    logger.error(f"Unsupported method {method}")
                    return None

                async with coro as resp:
                    if resp.status == 200:
                        try:
                            return await resp.json()
                        except:
                            # Иногда WB отдает 200, но не JSON (пусто или текст)
                            text = await resp.text()
                            if not text: return {}
                            return {"text": text}
                            
                    elif resp.status == 204:
                        return None # No content
                        
                    elif resp.status == 429:
                        logger.warning(f"Rate Limit (429) on {url}. Sleeping {backoff}s...")
                        await asyncio.sleep(backoff)
                        backoff *= 2 
                        
                    elif resp.status >= 500:
                        logger.warning(f"Server Error ({resp.status}). Retry {attempt}/{retries}...")
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        
                    else:
                        text = await resp.text()
                        if attempt == retries:
                            logger.error(f"WB API Error {resp.status} on {url}: {text[:200]}")
                        return None
                        
            except aiohttp.ClientError as e:
                logger.error(f"Network error {url}: {e}")
                if attempt == retries: return None
                await asyncio.sleep(backoff)
                
            except Exception as e:
                logger.error(f"Request failed: {e}")
                if attempt == retries: return None
                await asyncio.sleep(backoff)
        
        return None

    def _get_cache_key(self, token, method, params):
        token_part = token[-10:] if token else "none"
        # params может быть None
        p = params if params else {}
        param_str = json.dumps(p, sort_keys=True)
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
        """
        Умная проверка: проверяет Контент, если нет - Статистику.
        Используется при сохранении токена.
        """
        headers = {"Authorization": token}
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            try:
                # 1. Проверка через Content API (лимиты - очень легкий запрос)
                url = f"{self.URLS['content']}/content/v2/cards/limits"
                async with session.get(url, headers=headers) as resp:
                    if resp.status in [200, 429]: return True
                    
                    # 2. Если 401 (нет доступа к контенту), пробуем Статистику
                    if resp.status in [401, 403]:
                        url_stat = f"{self.URLS['statistics']}/api/v1/supplier/incomes"
                        async with session.get(url_stat, headers=headers, params={"dateFrom": "2024-01-01"}) as resp_stat:
                            return resp_stat.status in [200, 204, 429]
                return False
            except Exception as e:
                logger.error(f"Token check error: {e}")
                return False