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
        """
        Получение списка товаров с ценами и скидками.
        Это самый быстрый способ узнать текущую цену селлера.
        """
        url = f"{self.PRICES_URL}/api/v2/list/goods/filter"
        headers = {"Authorization": token}
        params = {
            "limit": limit,
            "offset": offset
        }
        
        # Используем session=None, чтобы базовый класс создал новую
        data = await self._request_with_retry(None, url, headers, params=params, method='GET')
        
        if data and 'data' in data and 'listGoods' in data['data']:
            return data['data']['listGoods']
        
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
            
        return all_goods