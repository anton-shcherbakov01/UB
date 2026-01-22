import logging
import aiohttp
from typing import Dict, List, Any
from .base import WBApiBase

logger = logging.getLogger("WB-API-Prices")

class WBPricesMixin(WBApiBase):
    """
    Миксин для работы с API Цен и Скидок.
    Документация: https://openapi.wildberries.ru/prices/api/ru/
    """
    PRICES_URL = "https://discounts-prices-api.wildberries.ru"

    async def get_goods_list(self, token: str, limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
        url = f"{self.PRICES_URL}/api/v2/list/goods/filter"
        headers = {"Authorization": token}
        params = {
            "limit": limit,
            "offset": offset
        }
        
        # ДЕБАГ: Логируем запрос
        # logger.info(f"Requesting Prices API: offset={offset}, limit={limit}")
        
        # Используем session=None, чтобы базовый класс создал новую
        # Метод GET, как требует документация
        data = await self._request_with_retry(None, url, headers, params=params, method='GET')
        
        if data:
            # ДЕБАГ: Если данные пришли, проверим структуру
            if 'data' in data and 'listGoods' in data['data']:
                goods = data['data']['listGoods']
                # logger.info(f"Got {len(goods)} goods from Prices API")
                return goods
            else:
                logger.error(f"WB Prices API Error structure: {data}")
        else:
            logger.error("WB Prices API returned None (Check Token Scopes 'Prices & Discounts')")
        
        return []

    async def get_all_goods_prices(self, token: str) -> List[Dict[str, Any]]:
        """
        Выгружает ВСЕ товары селлера (пагинация).
        """
        all_goods = []
        offset = 0
        limit = 1000
        
        while True:
            batch = await self.get_goods_list(token, limit=limit, offset=offset)
            if not batch:
                break
            
            all_goods.extend(batch)
            
            if len(batch) < limit:
                break
                
            offset += limit
            
        logger.info(f"Total goods fetched from Prices API: {len(all_goods)}")
        return all_goods