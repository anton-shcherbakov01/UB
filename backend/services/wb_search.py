import aiohttp
import asyncio
import logging
import random
from urllib.parse import quote
from typing import Dict, Any, List

logger = logging.getLogger("WBSearch")

# Расширенные гео-зоны.
# dest - это комбинация ID складов, которые приоритетны для региона.
# Эти данные взяты из актуальных конфигов WB для мобильных приложений.
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

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 10; SM-A505FN) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.152 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36"
]

class WBSearchService:
    """
    Ultimate WB Search Parser.
    Собирает не только позицию, но и окружение (конкурентов), цены и сроки доставки.
    """
    
    BASE_URL = "https://search.wb.ru/exactmatch/ru/common/v5/search"

    def _get_headers(self):
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "*/*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": "https://www.wildberries.ru",
        }

    async def get_sku_position(
        self, 
        query: str, 
        target_sku: int, 
        geo: str = "moscow",
        depth_pages: int = 5
    ) -> Dict[str, Any]:
        dest_id = GEO_ZONES.get(geo, GEO_ZONES["moscow"])
        encoded_query = quote(query)
        target_sku = int(target_sku)
        
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
            "total_products": 0,
            "product_info": {},      # Детали нашего товара
            "neighbors": [],         # Кто стоит рядом (конкуренты)
            "top_3": []              # Топ-3 выдачи для сравнения
        }

        async with aiohttp.ClientSession(headers=self._get_headers()) as session:
            tasks = []
            for page in range(1, depth_pages + 1):
                url = (
                    f"{self.BASE_URL}?"
                    f"ab_testing=false&appType=1&curr=rub&dest={dest_id}"
                    f"&query={encoded_query}&resultset=catalog&sort=popular"
                    f"&spp=30&suppressSpellcheck=false&page={page}"
                )
                tasks.append(self._fetch_page(session, url, page))
            
            pages_data = await asyncio.gather(*tasks)

        # Сквозная нумерация и поиск
        global_counter = 0
        sorted_pages = sorted(pages_data, key=lambda x: x['page'])
        
        all_products_flat = []
        
        # 1. Сначала развернем все товары в один плоский список для удобства анализа соседей
        for p_data in sorted_pages:
            if p_data['page'] == 1:
                result['total_products'] = p_data['total']
            
            for prod in p_data['products']:
                global_counter += 1
                # Обогащаем продукт абсолютной позицией
                prod['_abs_pos'] = global_counter
                prod['_page'] = p_data['page']
                all_products_flat.append(prod)

        # 2. Собираем Топ-3 (для бенчмарка)
        for i in range(min(3, len(all_products_flat))):
            result['top_3'].append(self._extract_product_data(all_products_flat[i]))

        # 3. Ищем наш SKU
        target_index = -1
        for idx, prod in enumerate(all_products_flat):
            if prod.get('id') == target_sku:
                target_index = idx
                result['found'] = True
                result['page'] = prod['_page']
                # Позиция на странице вычисляется как (abs_pos - 1) % 100 + 1
                result['position'] = (prod['_abs_pos'] - 1) % 100 + 1
                result['absolute_pos'] = prod['_abs_pos']
                
                # Рекламные данные
                if prod.get('log'):
                    result['is_advertising'] = True
                    result['cpm'] = prod.get('log', {}).get('cpm')
                
                # Детальная инфа о нашем товаре
                result['product_info'] = self._extract_product_data(prod)
                break
        
        # 4. Если нашли, берем соседей (2 сверху, 2 снизу)
        if target_index != -1:
            start_idx = max(0, target_index - 2)
            end_idx = min(len(all_products_flat), target_index + 3)
            
            for i in range(start_idx, end_idx):
                if i == target_index: continue # Пропускаем себя
                neighbor = self._extract_product_data(all_products_flat[i])
                # Помечаем, выше он или ниже
                neighbor['relation'] = 'above' if i < target_index else 'below'
                result['neighbors'].append(neighbor)

        return result

    def _extract_product_data(self, prod: dict) -> dict:
        """Парсит сырой JSON товара в чистую структуру"""
        
        # Цены в копейках
        price_u = prod.get('priceU', 0) / 100
        sale_price_u = prod.get('salePriceU', 0) / 100
        
        return {
            "id": prod.get('id'),
            "name": prod.get('name'),
            "brand": prod.get('brand'),
            "rating": prod.get('reviewRating'),
            "feedbacks": prod.get('feedbacks'),
            "price": sale_price_u, # Цена продажи (со скидками)
            "base_price": price_u, # Цена до скидок
            "promo_text": prod.get('promoTextCat'), # Например "Доставка завтра"
            "delivery_time": prod.get('time1', 0) + prod.get('time2', 0), # Время доставки (условные часы)
            "image": f"https://basket-{self._get_basket_number(prod.get('id'))}.wbbasket.ru/vol{str(prod.get('id'))[:4]}/part{str(prod.get('id'))[:6]}/{prod.get('id')}/images/c246x328/1.jpg",
            "position": prod.get('_abs_pos'),
            "is_ad": bool(prod.get('log'))
        }

    def _get_basket_number(self, nm_id: int) -> str:
        """Определяет номер корзины для генерации ссылки на фото (алгоритм WB)"""
        if not nm_id: return "01"
        vol = int(nm_id // 100000)
        if 0 <= vol <= 143: return "01"
        if 144 <= vol <= 287: return "02"
        if 288 <= vol <= 431: return "03"
        if 432 <= vol <= 719: return "04"
        if 720 <= vol <= 1007: return "05"
        if 1008 <= vol <= 1061: return "06"
        if 1062 <= vol <= 1115: return "07"
        if 1116 <= vol <= 1169: return "08"
        if 1170 <= vol <= 1313: return "09"
        if 1314 <= vol <= 1601: return "10"
        if 1602 <= vol <= 1655: return "11"
        if 1656 <= vol <= 1919: return "12"
        if 1920 <= vol <= 2045: return "13"
        if 2046 <= vol <= 2189: return "14"
        return "15" # Fallback

    async def _fetch_page(self, session, url, page_num):
        try:
            async with session.get(url, timeout=6) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        'page': page_num,
                        'products': data.get('data', {}).get('products', []),
                        'total': data.get('data', {}).get('total', 0)
                    }
        except Exception as e:
            logger.warning(f"Page {page_num} timeout/error: {e}")
        return {'page': page_num, 'products': [], 'total': 0}

wb_search_service = WBSearchService()