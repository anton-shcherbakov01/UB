import aiohttp
import asyncio
import logging
import random
import json
from urllib.parse import quote
from typing import Dict, Any

# Логгер в консоль, чтобы вы видели всё
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WBSearch")

GEO_ZONES = {
    "moscow": "-1257786",      
    "spb": "-1257786",         
    "kazan": "-2133464",       
    "krasnodar": "-1192533",   
    "ekb": "-1113276",         
    "novosibirsk": "-1282245", 
    "khabarovsk": "-1216606",
    "belarus": "1235",         
    "kazakhstan": "-1227092"
}

# Имитируем реальные Android устройства
USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; Pixel 6 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; SM-A525F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Mobile Safari/537.36"
]

class WBSearchService:
    # ОБНОВЛЕНИЕ: Используем v9 (самый свежий)
    BASE_URL = "https://search.wb.ru/exactmatch/ru/common/v9/search"

    def _get_headers(self):
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br",
            "Origin": "https://www.wildberries.ru",
            "x-requested-with": "XMLHttpRequest"
        }

    async def get_sku_position(self, query: str, target_sku: int, geo: str = "moscow", depth_pages: int = 5) -> Dict[str, Any]:
        dest_id = GEO_ZONES.get(geo, GEO_ZONES["moscow"])
        encoded_query = quote(query)
        target_sku = int(target_sku)
        
        logger.info(f"🔎 [SEARCH v9] Ищу SKU {target_sku} по запросу '{query}' в регионе {geo}")

        result = {
            "sku": target_sku,
            "query": query,
            "geo": geo,
            "found": False,
            "page": None,
            "position": None,
            "absolute_pos": None,
            "is_advertising": False,
            "cpm": None,
            "top_3_found": [], # Для отладки: что бот видит в топе
            "total_products": 0
        }

        async with aiohttp.ClientSession(headers=self._get_headers()) as session:
            tasks = []
            for page in range(1, depth_pages + 1):
                # ОБНОВЛЕНИЕ: appType=64 (Android), sort=popular
                url = (
                    f"{self.BASE_URL}?"
                    f"ab_testing=false&appType=64&curr=rub&dest={dest_id}"
                    f"&query={encoded_query}&resultset=catalog&sort=popular"
                    f"&spp=30&suppressSpellcheck=false&page={page}"
                )
                tasks.append(self._fetch_page(session, url, page))
            
            pages_data = await asyncio.gather(*tasks)

        global_counter = 0
        sorted_pages = sorted(pages_data, key=lambda x: x['page'])
        
        for p_data in sorted_pages:
            products = p_data['products']
            
            # ЛОГИРОВАНИЕ: Пишем в консоль, что мы нашли на странице
            if not products:
                logger.warning(f"⚠️ Страница {p_data['page']}: Пусто (0 товаров). Статус: {p_data['status']}")
                continue
            else:
                first_item = products[0].get('name', 'Unknown')
                logger.info(f"✅ Страница {p_data['page']}: Найдено {len(products)} товаров. Топ-1: {first_item}")

            # Сохраняем Топ-3 всей выдачи для отладки
            if p_data['page'] == 1:
                result['total_products'] = p_data['total']
                for i in range(min(3, len(products))):
                    result['top_3_found'].append({
                        "id": products[i].get('id'),
                        "name": products[i].get('name'),
                        "brand": products[i].get('brand')
                    })

            for idx, prod in enumerate(products):
                global_counter += 1
                
                # Сравнение ID
                if prod.get('id') == target_sku:
                    logger.info(f"🎉 НАШЕЛ! {target_sku} на позиции {global_counter}")
                    
                    result['found'] = True
                    result['page'] = p_data['page']
                    result['position'] = idx + 1
                    result['absolute_pos'] = global_counter
                    
                    if prod.get('log'):
                        result['is_advertising'] = True
                        result['cpm'] = prod.get('log', {}).get('cpm')
                    
                    return result

        logger.info(f"💨 Поиск завершен. Просмотрено {global_counter} товаров. Артикул не найден.")
        return result

    async def _fetch_page(self, session, url, page_num):
        try:
            async with session.get(url, timeout=8) as resp:
                if resp.status == 200:
                    try:
                        data = await resp.json()
                        return {
                            'page': page_num, 
                            'products': data.get('data', {}).get('products', []),
                            'total': data.get('data', {}).get('total', 0),
                            'status': 200
                        }
                    except:
                        return {'page': page_num, 'products': [], 'total': 0, 'status': 'JSON_ERR'}
                return {'page': page_num, 'products': [], 'total': 0, 'status': resp.status}
        except Exception as e:
            logger.error(f"Page {page_num} Error: {e}")
            return {'page': page_num, 'products': [], 'total': 0, 'status': 'CONN_ERR'}

wb_search_service = WBSearchService()