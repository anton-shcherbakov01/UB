import aiohttp
import asyncio
import logging
from urllib.parse import quote
from typing import Dict, Any, Optional

logger = logging.getLogger("WBSearch")

# Маппинг регионов (dest ID). 
# Это "магические" числа WB, которые переключают склад и выдачу.
GEO_ZONES = {
    "moscow": "-1257786",      # Москва
    "spb": "-1257786",         # СПБ (часто совпадает с МСК по выдаче, либо -59208)
    "kazan": "-2133464",       # Казань (склад)
    "krasnodar": "-1192533",   # Краснодар
    "ekb": "-1113276",         # Екатеринбург
    "novosibirsk": "-1282245", # Новосибирск
    "khabarovsk": "-1216606",  # Хабаровск
    "belarus": "1235",         # Минск
    "kazakhstan": "-1227092"   # Алматы
}

class WBSearchService:
    """
    Профессиональный парсер выдачи WB через Mobile API.
    Работает без Selenium.
    """
    
    BASE_URL = "https://search.wb.ru/exactmatch/ru/common/v5/search"

    async def get_sku_position(
        self, 
        query: str, 
        target_sku: int, 
        geo: str = "moscow",
        depth_pages: int = 5
    ) -> Dict[str, Any]:
        """
        Ищет позицию артикула по запросу.
        :param query: поисковой запрос
        :param target_sku: артикул
        :param geo: ключ региона из GEO_ZONES
        :param depth_pages: сколько страниц проверять (обычно 1-5, больше 10 нет смысла для SEO)
        """
        dest_id = GEO_ZONES.get(geo, GEO_ZONES["moscow"])
        encoded_query = quote(query)
        target_sku = int(target_sku)
        
        # Результат
        result = {
            "sku": target_sku,
            "query": query,
            "geo": geo,
            "found": False,
            "position": None,       # Абсолютная позиция
            "page": None,           # Страница
            "is_advertising": False,# Это автореклама?
            "organic_pos": None,    # Позиция без учета рекламы (если возможно вычислить)
            "total_products": 0,
            "cpm": None             # Ставка (если это реклама)
        }

        async with aiohttp.ClientSession() as session:
            tasks = []
            # WB отдает по 100 товаров на страницу API (независимо от веба)
            for page in range(1, depth_pages + 1):
                url = (
                    f"{self.BASE_URL}?"
                    f"ab_testing=false&appType=1&curr=rub&dest={dest_id}"
                    f"&query={encoded_query}&resultset=catalog&sort=popular"
                    f"&spp=30&suppressSpellcheck=false&page={page}"
                )
                tasks.append(self._fetch_page(session, url, page))
            
            # Запускаем запросы параллельно! Это даст скорость < 1 сек на 5 страниц
            pages_data = await asyncio.gather(*tasks)

        # Анализ результатов
        global_position_counter = 0
        
        for page_idx, data in sorted(pages_data, key=lambda x: x['page']):
            if not data['products']:
                continue
                
            if page_idx == 1:
                result['total_products'] = data.get('total', 0)

            for idx, product in enumerate(data['products']):
                global_position_counter += 1
                prod_id = product.get('id')
                
                if prod_id == target_sku:
                    result['found'] = True
                    result['page'] = page_idx
                    result['position'] = idx + 1 # Позиция на странице
                    result['absolute_pos'] = global_position_counter
                    
                    # Проверка на рекламу (log поле содержит данные об аукционе)
                    log_payload = product.get('log')
                    if log_payload:
                        result['is_advertising'] = True
                        result['cpm'] = log_payload.get('cpm')
                        result['promo_pos'] = log_payload.get('promoPosition')
                    
                    return result

        return result

    async def _fetch_page(self, session, url, page_num):
        try:
            async with session.get(url, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # data['data']['products'] - список товаров
                    return {
                        'page': page_num,
                        'products': data.get('data', {}).get('products', []),
                        'total': data.get('data', {}).get('total', 0)
                    }
        except Exception as e:
            logger.error(f"Error fetching page {page_num}: {e}")
        return {'page': page_num, 'products': [], 'total': 0}

# Создаем синглтон
wb_search_service = WBSearchService()