import logging
import asyncio
import aiohttp
from typing import Optional, Any, Dict, Union

logger = logging.getLogger("WB-API-Base")

class WBApiBase:
    """
    Базовый класс для всех API сервисов Wildberries.
    Отвечает за выполнение HTTP запросов, повторные попытки (retry) и обработку ошибок.
    """
    
    COMMON_URL = "https://common-api.wildberries.ru/api/v1"
    STATISTICS_URL = "https://statistics-api.wildberries.ru"
    ADVERT_URL = "https://advert-api.wb.ru/adv/v1"
    CONTENT_URL = "https://content-api.wildberries.ru/content/v2"

    def __init__(self):
        pass

    async def _request_with_retry(
        self,
        session: Optional[aiohttp.ClientSession],
        url: str,
        headers: Dict[str, Any],
        params: Optional[Dict] = None,
        method: str = "GET",
        json_data: Optional[Dict] = None,
        retries: int = 3,
        delay: int = 1
    ) -> Optional[Any]:
        """
        Выполняет запрос с автоматическим ретраем.
        Если session is None, создает новую сессию на один запрос.
        """
        if session is None:
            # Если сессии нет, создаем контекст (connection pool на один запрос)
            async with aiohttp.ClientSession() as new_session:
                return await self._execute_request(
                    new_session, url, headers, params, method, json_data, retries, delay
                )
        else:
            # Если сессия есть, используем её
            return await self._execute_request(
                session, url, headers, params, method, json_data, retries, delay
            )

    async def _execute_request(
        self,
        session: aiohttp.ClientSession,
        url: str,
        headers: Dict[str, Any],
        params: Optional[Dict],
        method: str,
        json_data: Optional[Dict],
        retries: int,
        delay: int
    ) -> Optional[Any]:
        
        for attempt in range(1, retries + 1):
            try:
                if method.upper() == "GET":
                    async with session.get(url, headers=headers, params=params) as response:
                        return await self._process_response(response)
                
                elif method.upper() == "POST":
                    async with session.post(url, headers=headers, json=json_data, params=params) as response:
                        return await self._process_response(response)
                        
                elif method.upper() == "PUT":
                    async with session.put(url, headers=headers, json=json_data, params=params) as response:
                        return await self._process_response(response)
                        
            except aiohttp.ClientError as e:
                logger.error(f"Network error {url}: {e}")
                if attempt == retries:
                    return None
            except Exception as e:
                logger.error(f"Request failed {url}: {e}")
                if attempt == retries:
                    return None
            
            # Экспоненциальная задержка перед следующей попыткой
            await asyncio.sleep(delay * attempt)
        
        return None

    async def _process_response(self, response: aiohttp.ClientResponse) -> Optional[Any]:
        """Обработка статусов ответа"""
        if response.status == 200:
            try:
                return await response.json()
            except:
                text = await response.text()
                # Иногда WB возвращает 200, но пустой или битый JSON
                if not text: return {}
                return {"text": text}
        
        elif response.status == 401:
            logger.error(f"Unauthorized (401) for {response.url}. Check token.")
            return None
            
        elif response.status == 429:
            logger.warning(f"Rate Limit (429) for {response.url}. Sleeping...")
            await asyncio.sleep(5)
            # Возбуждаем ошибку, чтобы сработал внешний retry loop
            raise aiohttp.ClientError("Rate Limit")
            
        else:
            text = await response.text()
            logger.error(f"API Error {response.status}: {text[:200]}")
            return None