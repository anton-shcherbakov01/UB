import aiohttp
import asyncio
import logging
from typing import Dict

logger = logging.getLogger("WBApiService")

class WBApiService:
    # Базовые URL для разных шлюзов WB
    URLS = {
        "common": "https://common-api.wildberries.ru",
        "content": "https://content-api.wildberries.ru",
        "statistics": "https://statistics-api.wildberries.ru",
        "advert": "https://advert-api.wb.ru",
        "marketplace": "https://marketplace-api.wildberries.ru",
        "feedbacks": "https://feedbacks-api.wildberries.ru"
    }

    def __init__(self):
        # Короткий таймаут, чтобы проверка профиля не висела долго
        self.timeout = aiohttp.ClientTimeout(total=8)

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

    async def get_token_scopes(self, token: str) -> Dict[str, bool]:
        """
        Параллельный опрос всех шлюзов WB для построения карты доступов.
        """
        headers = {"Authorization": token}
        
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            # Формируем задачи
            tasks = {
                "content": self._probe(session, "GET", f"{self.URLS['content']}/content/v2/cards/limits", headers),
                "marketplace": self._probe(session, "GET", f"{self.URLS['marketplace']}/api/v3/warehouses", headers),
                "stats": self._probe(session, "GET", f"{self.URLS['statistics']}/api/v1/supplier/incomes", headers, params={"dateFrom": "2024-01-01"}),
                "advert": self._probe(session, "GET", f"{self.URLS['advert']}/adv/v1/promotion/count", headers),
                "feedbacks": self._probe(session, "GET", f"{self.URLS['feedbacks']}/api/v1/questions/count", headers, params={"isAnswered": "false"}),
                "prices": self._probe(session, "GET", f"{self.URLS['common']}/public/api/v1/info", headers)
            }
            
            # Запускаем параллельно
            results_list = await asyncio.gather(*tasks.values(), return_exceptions=True)
            
            # Собираем результаты
            keys = list(tasks.keys())
            raw_res = {}
            for i, key in enumerate(keys):
                res = results_list[i]
                raw_res[key] = res if isinstance(res, bool) else False

        # Маппинг для UI (13 категорий)
        return {
            "content": raw_res["content"],
            "marketplace": raw_res["marketplace"],
            "analytics": raw_res["stats"],
            "promotion": raw_res["advert"],
            "returns": raw_res["marketplace"],
            "documents": raw_res["content"],
            "statistics": raw_res["stats"],
            "finance": raw_res["stats"],
            "supplies": raw_res["marketplace"] or raw_res["content"],
            "chat": raw_res["feedbacks"],
            "questions": raw_res["feedbacks"],
            "prices": raw_res["prices"] or raw_res["content"],
            "users": True 
        }

    async def _probe(self, session, method, url, headers, params=None) -> bool:
        try:
            async with session.request(method, url, headers=headers, params=params) as resp:
                # 401/403 = Доступа нет. Всё остальное (200, 429, 404, 500) = Доступ есть (токен принят)
                if resp.status in [401, 403]: return False
                return True
        except:
            return False

# Экземпляр для импорта
wb_api_service = WBApiService()