import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .base import WBBaseClient, WBEndpoint

logger = logging.getLogger("WB-API-Promotion")

class WBPromotionMixin(WBBaseClient):
    
    async def get_active_campaigns(self, token: str) -> List[Dict]:
        """Получение списка активных рекламных кампаний"""
        data = await self._request("GET", WBEndpoint.ADV_LIST.value, token)
        if not data or "adverts" not in data:
            return []
        
        # Фильтруем только активные (status 9 - идут показы, 11 - на паузе, но активна)
        active_ids = [
            adv['advertId'] for adv in data['adverts'] 
            if adv['status'] in [9, 11]
        ]
        return active_ids

    async def get_campaign_info(self, token: str, campaign_id: int) -> Optional[Dict]:
        """Детальная информация о кампании"""
        params = {"id": campaign_id}
        # У WB специфичный эндпоинт, принимающий id в query для списка, 
        # но мы используем POST для массового получения, или GET для одного
        # Здесь используем GET/POST согласно документации v1
        
        # Для получения инфо часто используется POST с массивом ID
        data = await self._request("POST", WBEndpoint.ADV_INFO.value, token, json_data=[campaign_id])
        if data and isinstance(data, list) and len(data) > 0:
            return data[0]
        return None

    async def get_current_bid_info(self, token: str, campaign_id: int) -> Dict:
        """Получение текущей ставки и позиции (эмуляция или реальный запрос)"""
        # WB не отдает "текущую позицию" прямо в API управления ставками, 
        # но отдает текущую ставку кампании.
        info = await self.get_campaign_info(token, campaign_id)
        if not info:
            return {"price": 0, "status": 0}
            
        params = info.get('params', [])
        price = 0
        if params and len(params) > 0:
            price = params[0].get('price', 0)
            
        return {
            "price": price,
            "status": info.get('status'),
            "type": info.get('type')
        }

    async def update_bid(self, token: str, campaign_id: int, new_bid: int):
        """Обновление ставки (CPM)"""
        # Для типа 8 (Авто) и 9 (Поиск) разные эндпоинты, здесь пример для Поиска/Каталога (v0/cpm)
        payload = {
            "advertId": campaign_id,
            "type": 6, # Тип смены ставки, 6 = cpm
            "cpm": new_bid,
            "param": 0, # В зависимости от типа кампании (subjectId или 0)
            "instrument": 0 # 0 - не менять
        }
        # Для автокампаний нужен другой роут /adv/v1/auto/cpm.
        # Упрощенная логика: пробуем универсальный или разделяем по типу.
        # Здесь предполагаем ручное управление (Поиск).
        
        url = "https://advert-api.wildberries.ru/adv/v0/cpm"
        res = await self._request("POST", url, token, json_data=payload)
        return res

    async def get_advert_stats(self, token: str, campaign_id: int) -> Dict:
        """Получение статистики (CTR, CPC) за последние дни"""
        dates = [(datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]
        payload = [{"id": campaign_id, "dates": dates}]
        
        data = await self._request("POST", WBEndpoint.ADV_STATS.value, token, json_data=payload)
        
        if not data or not isinstance(data, list):
            return {"ctr": 0, "views": 0, "clicks": 0}
            
        # Агрегация статистики за период
        total_views = 0
        total_clicks = 0
        
        for day in data:
            for day_stat in day.get('days', []):
                total_views += day_stat.get('views', 0)
                total_clicks += day_stat.get('clicks', 0)
                
        ctr = (total_clicks / total_views * 100) if total_views > 0 else 0
        return {
            "ctr": round(ctr, 2),
            "views": total_views,
            "clicks": total_clicks
        }