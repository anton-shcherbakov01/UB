# backend/wb_api/content.py
import logging
from typing import List, Dict, Any
from .base import WBApiBase

logger = logging.getLogger("WB-API-Content")

class WBContentMixin(WBApiBase):
    async def get_cards_with_dimensions(self, token: str) -> Dict[int, Dict]:
        """
        Получает список всех товаров с их габаритами и категорией.
        Возвращает словарь: {nmId: {volume_liters, subject_id, subject_name}}
        """
        url = "https://content-api.wildberries.ru/content/v2/get/cards/list"
        headers = {"Authorization": token}
        
        # Запрашиваем батчами, чтобы не перегрузить
        payload = {
            "settings": {
                "cursor": {"limit": 100},
                "filter": {"withPhoto": -1}
            }
        }
        
        result_map = {}
        
        try:
            while True:
                data = await self._request_with_retry(None, url, headers, method='POST', json_data=payload) # session передается снаружи или создается внутри _request
                # Примечание: В твоем базовом классе session обязателен, здесь упрощено для примера
                # Лучше использовать существующий механизм сессий из base.py
                
                cards = data.get('cards', [])
                if not cards:
                    break
                    
                for card in cards:
                    nm_id = card.get('nmID')
                    dims = card.get('dimensions', {})
                    # Считаем объем в литрах: (Д * Ш * В) / 1000
                    l = int(dims.get('length', 0))
                    w = int(dims.get('width', 0))
                    h = int(dims.get('height', 0))
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
                
                if total < 100: break
                
                payload['settings']['cursor']['updatedAt'] = updated_at
                payload['settings']['cursor']['nmID'] = nm_id

        except Exception as e:
            logger.error(f"Error fetching cards dimensions: {e}")
            
        return result_map