import asyncio
import logging
import random
import json
from urllib.parse import quote
from typing import Dict, Any

# Импортируем магию, которая лечит TLS Fingerprint
from curl_cffi.requests import AsyncSession

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

class WBSearchService:
    # Используем API каталога, оно реже банит, чем search.wb.ru
    # Но для поиска V9 тоже подойдет, если притвориться хромом
    BASE_URL = "https://search.wb.ru/exactmatch/ru/common/v9/search"

    async def get_sku_position(self, query: str, target_sku: int, geo: str = "moscow", depth_pages: int = 5) -> Dict[str, Any]:
        dest_id = GEO_ZONES.get(geo, GEO_ZONES["moscow"])
        encoded_query = quote(query)
        target_sku = int(target_sku)
        
        logger.info(f"🛡️ [TLS-Bypass] Ищу SKU {target_sku} по '{query}' (Geo: {geo})")

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
            "debug_logs": []
        }

        # impersonate="chrome120" — Ключевой момент!
        # Мы говорим серверу: "Я реальный Chrome 120", и подделываем TLS-хендшейк.
        async with AsyncSession(impersonate="chrome120") as session:
            tasks = []
            for page in range(1, depth_pages + 1):
                # appType=1 (Desktop), так как мы притворяемся десктопным хромом
                url = (
                    f"{self.BASE_URL}?"
                    f"ab_testing=false&appType=1&curr=rub&dest={dest_id}"
                    f"&query={encoded_query}&resultset=catalog&sort=popular"
                    f"&spp=30&suppressSpellcheck=false&page={page}"
                )
                tasks.append(self._fetch_page(session, url, page))
            
            pages_data = await asyncio.gather(*tasks)

        global_counter = 0
        sorted_pages = sorted(pages_data, key=lambda x: x['page'])
        
        for p_data in sorted_pages:
            status_line = f"Page {p_data['page']}: {len(p_data['products'])} items. (HTTP {p_data['status']})"
            logger.info(status_line)
            result['debug_logs'].append(status_line)

            if p_data['page'] == 1:
                result['total_products'] = p_data['total']

            for idx, prod in enumerate(p_data['products']):
                global_counter += 1
                if prod.get('id') == target_sku:
                    logger.info(f"🎯 FOUND! Abs Pos: {global_counter}")
                    result['found'] = True
                    result['page'] = p_data['page']
                    result['position'] = idx + 1
                    result['absolute_pos'] = global_counter
                    if prod.get('log'):
                        result['is_advertising'] = True
                        result['cpm'] = prod.get('log', {}).get('cpm')
                    return result

        return result

    async def _fetch_page(self, session, url, page_num):
        try:
            # curl_cffi не требует заголовков User-Agent вручную, он ставит их сам из пресета
            resp = await session.get(url, timeout=10)
            
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    products = data.get('data', {}).get('products', [])
                    total = data.get('data', {}).get('total', 0)
                    return {'page': page_num, 'products': products, 'total': total, 'status': 200}
                except Exception:
                    return {'page': page_num, 'products': [], 'total': 0, 'status': 'JSON_ERR'}
            
            elif resp.status_code == 429:
                logger.warning(f"⚠️ Page {page_num}: 429 Blocked (Try Proxy)")
            
            return {'page': page_num, 'products': [], 'total': 0, 'status': resp.status_code}
            
        except Exception as e:
            logger.error(f"❌ Page {page_num} Error: {e}")
            return {'page': page_num, 'products': [], 'total': 0, 'status': 'CONN_ERR'}

wb_search_service = WBSearchService()