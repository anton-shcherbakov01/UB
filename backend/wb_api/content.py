import logging
from typing import Dict, Any, Optional
from .base import WBApiBase

logger = logging.getLogger("WB-API-Content")

class WBContentMixin(WBApiBase):
    """
    Миксин для работы с Content API (карточки товаров, габариты).
    """

    async def get_cards_with_dimensions(self, token: str) -> Dict[int, Dict]:
        """
        Получает список всех товаров с их габаритами и категорией.
        Возвращает словарь: {nmId: {volume_liters, subject_id, subject_name}}
        """
        url = "https://content-api.wildberries.ru/content/v2/get/cards/list"
        headers = {"Authorization": token}
        
        # Запрашиваем батчами
        payload = {
            "settings": {
                "cursor": {"limit": 100},
                "filter": {"withPhoto": -1}
            }
        }
        
        result_map = {}
        
        try:
            while True:
                # Используем _request_with_retry из базового класса
                # Важно: session=None, так как _request сам создаст или возьмет сессию
                data = await self._request_with_retry(
                    session=None, 
                    url=url, 
                    headers=headers, 
                    method='POST', 
                    json_data=payload
                )
                
                if not data:
                    break

                cards = data.get('cards', [])
                if not cards:
                    break
                    
                for card in cards:
                    nm_id = card.get('nmID')
                    dims = card.get('dimensions', {})
                    
                    # Считаем объем в литрах: (Д * Ш * В) / 1000
                    # Если габаритов нет, ставим безопасный дефолт
                    l = int(dims.get('length', 0))
                    w = int(dims.get('width', 0))
                    h = int(dims.get('height', 0))
                    
                    # Защита от нулевых габаритов (WB иногда отдает 0)
                    if l == 0: l = 10
                    if w == 0: w = 10
                    if h == 0: h = 10
                        
                    volume = (l * w * h) / 1000.0
                    
                    subject_id = card.get('subjectID')
                    subject_name = card.get('subjectName')
                    
                    result_map[nm_id] = {
                        "volume": round(volume, 2),
                        "subject_id": subject_id,
                        "subject_name": subject_name
                    }
                
                # Пагинация
                cursor = data.get('cursor', {})
                updated_at = cursor.get('updatedAt')
                nm_id = cursor.get('nmID')
                total = cursor.get('total')
                
                if total < 100: 
                    break
                
                payload['settings']['cursor']['updatedAt'] = updated_at
                payload['settings']['cursor']['nmID'] = nm_id

        except Exception as e:
            logger.error(f"Error fetching cards dimensions: {e}")
            
        return result_map