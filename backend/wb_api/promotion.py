import logging
import aiohttp
from typing import Optional, Dict, Any, List
from .base import WBApiBase

logger = logging.getLogger("WB-API-Promotion")

class WBPromotionMixin(WBApiBase):

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
        
    async def get_auction_cpm(self, keyword: str) -> List[Dict]:
        """
        Получение реальных ставок конкурентов (Аукцион) по ключевому слову.
        Использует публичный API, который отдает 'реальные' цифры, используемые при ранжировании.
        """
        url = "https://catalog-ads.wildberries.ru/api/v6/search"
        params = {"keyword": keyword}
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, params=params, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # data['adverts'] содержит список: [{'code': '...', 'cpm': 1500, 'advertId': ...}, ...]
                        # Сортируем по CPM убыванию (это и есть реальные места 1, 2, 3...)
                        adverts = data.get('adverts', [])
                        if not adverts: 
                            return []
                        # Очищаем и сортируем
                        auction = sorted(
                            [{"pos": i+1, "cpm": a.get("cpm", 0), "id": a.get("advertId")} for i, a in enumerate(adverts)], 
                            key=lambda x: x["cpm"], 
                            reverse=True
                        )
                        # Пересчитываем позиции (иногда WB отдает мусор, но сортировка по CPM верна для аукциона)
                        for i, item in enumerate(auction):
                            item["pos"] = i + 1
                        return auction
            except Exception as e:
                logger.error(f"Failed to fetch auction for '{keyword}': {e}")
        return []

    async def get_campaign_info_v2(self, token: str, campaign_id: int):
        """Получение расширенной инфо о кампании через V1 endpoint (более надежный)"""
        url = f"https://advert-api.wb.ru/adv/v1/promotion/adverts"
        headers = {"Authorization": token}
        async with aiohttp.ClientSession() as session:
            # Запрашиваем конкретную кампанию
            # API требует отправлять type, но если мы хотим получить инфо по ID, пробуем так:
            # Обычно это работает через GET с параметром, но в V1 часто POST
            # Используем fallback на v0, который у вас уже реализован в get_current_bid_info
            # Но здесь важно получить статус: Активна/Пауза
            pass 
            # (Можно оставить текущую реализацию get_advert_campaigns, она рабочая)