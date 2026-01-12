import logging
from typing import List, Dict, Any
from .base import WBBaseClient, WBEndpoint

logger = logging.getLogger("WB-API-Content")

class WBContentMixin(WBBaseClient):

    async def get_cards_list(self, token: str, limit: int = 100, offset: int = 0, search: str = "") -> Dict:
        """Получение списка номенклатур (карточек товаров)"""
        
        payload = {
            "settings": {
                "cursor": {
                    "limit": limit
                },
                "filter": {
                    "withPhoto": -1
                }
            }
        }
        
        if search:
            payload["settings"]["filter"]["textSearch"] = search
            
        data = await self._request("POST", WBEndpoint.CONTENT_CARDS.value, token, json_data=payload)
        
        if not data or "cards" not in data:
            return {"cards": [], "cursor": {}}
            
        return data