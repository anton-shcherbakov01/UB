import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger("WB-API-Base")

class WBEndpoint(Enum):
    # Advertising
    ADV_LIST = "https://advert-api.wildberries.ru/adv/v1/promotion/count"
    ADV_INFO = "https://advert-api.wildberries.ru/adv/v1/promotion/adverts"
    ADV_CPA = "https://advert-api.wildberries.ru/adv/v1/promotion/adverts" # POST specific
    ADV_BIDS = "https://advert-api.wildberries.ru/adv/v0/cpm"
    ADV_STATS = "https://advert-api.wildberries.ru/adv/v2/fullstats"
    
    # Statistics
    STATS_ORDERS = "https://statistics-api.wildberries.ru/api/v1/supplier/orders"
    STATS_STOCKS = "https://statistics-api.wildberries.ru/api/v1/supplier/stocks"
    STATS_SALES = "https://statistics-api.wildberries.ru/api/v1/supplier/sales"
    STATS_REPORT = "https://statistics-api.wildberries.ru/api/v5/supplier/reportDetailByPeriod"
    
    # Content
    CONTENT_CARDS = "https://suppliers-api.wildberries.ru/content/v2/get/cards/list"

class WBBaseClient:
    def __init__(self):
        # Семафор для ограничения одновременных запросов (Rate Limiting)
        self._semaphore = asyncio.Semaphore(10)
        self._timeout = aiohttp.ClientTimeout(total=30, connect=10)

    async def _request(
        self, 
        method: str, 
        url: str, 
        token: str, 
        params: Optional[Dict] = None, 
        json_data: Optional[Dict] = None,
        retries: int = 3,
        backoff_factor: float = 1.5
    ) -> Any:
        headers = {
            "Authorization": token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        async with self._semaphore:
            for attempt in range(retries):
                try:
                    async with aiohttp.ClientSession(timeout=self._timeout) as session:
                        async with session.request(
                            method, url, params=params, json=json_data, headers=headers
                        ) as response:
                            
                            # Handle Rate Limits
                            if response.status == 429:
                                wait_time = backoff_factor ** (attempt + 1)
                                logger.warning(f"Rate Limit 429 on {url}. Waiting {wait_time}s...")
                                await asyncio.sleep(wait_time)
                                continue

                            # Handle Auth Errors
                            if response.status == 401:
                                logger.error(f"Unauthorized 401 on {url}. Check Token.")
                                return None

                            if response.status >= 500:
                                logger.warning(f"Server Error {response.status} on {url}. Retry {attempt+1}/{retries}")
                                await asyncio.sleep(1)
                                continue

                            if response.status not in (200, 201, 204):
                                text = await response.text()
                                logger.error(f"WB API Error {response.status} on {url}: {text}")
                                return None
                            
                            try:
                                return await response.json()
                            except:
                                return await response.text()

                except asyncio.TimeoutError:
                    logger.error(f"Timeout on {url}")
                except Exception as e:
                    logger.error(f"Request failed: {str(e)}")
                    if attempt == retries - 1:
                        raise e
                
                await asyncio.sleep(1)
            
            return None