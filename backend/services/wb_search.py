import asyncio
import logging
import random
import json
from urllib.parse import quote
from typing import Dict, Any, List

# Используем curl_cffi для обхода TLS Fingerprinting
from curl_cffi.requests import AsyncSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WBSearch")

# --- НАСТРОЙКИ ---
# Вставьте сюда ваш прокси, если запускаете с сервера!
# Формат: "http://user:pass@ip:port"
# Если пусто - работает напрямую (сработает только с локального ПК, с сервера вряд ли)
PROXY_URL = None 

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

# Ротация версий API (если одна забанена или пустая, пробуем другую)
API_VERSIONS = [
    "https://search.wb.ru/exactmatch/ru/common/v9/search",
    "https://search.wb.ru/exactmatch/ru/common/v7/search", 
    "https://search.wb.ru/exactmatch/ru/common/v5/search",
    "https://search.wb.ru/exactmatch/ru/common/v4/search",
]

class WBSearchService:
    async def get_sku_position(self, query: str, target_sku: int, geo: str = "moscow", depth_pages: int = 5) -> Dict[str, Any]:
        dest_id = GEO_ZONES.get(geo, GEO_ZONES["moscow"])
        encoded_query = quote(query)
        target_sku = int(target_sku)
        
        logger.info(f"🐢 [HUMAN-SEARCH] Ищу SKU {target_sku} по '{query}' (Geo: {geo})")

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
            "used_api": None,
            "debug_logs": []
        }

        proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

        # Пробуем разные версии API, пока не получим непустой ответ
        for base_url in API_VERSIONS:
            if result['found']: break # Уже нашли
            
            logger.info(f"🔄 Пробую API endpoint: {base_url}")
            
            # Эмуляция Chrome 120
            async with AsyncSession(impersonate="chrome120", proxies=proxies) as session:
                global_counter = 0
                
                # ВАЖНО: Последовательный перебор страниц, а не параллельный!
                for page in range(1, depth_pages + 1):
                    
                    # 1. Задержка как у человека (0.5 - 1.5 сек между страницами)
                    if page > 1:
                        sleep_time = random.uniform(0.5, 1.5)
                        await asyncio.sleep(sleep_time)

                    url = (
                        f"{base_url}?"
                        f"ab_testing=false&appType=1&curr=rub&dest={dest_id}"
                        f"&query={encoded_query}&resultset=catalog&sort=popular"
                        f"&spp=30&suppressSpellcheck=false&page={page}"
                    )

                    try:
                        resp = await session.get(url, timeout=10)
                        
                        if resp.status_code == 200:
                            try:
                                data = resp.json()
                                products = data.get('data', {}).get('products', [])
                                total = data.get('data', {}).get('total', 0)
                                
                                if page == 1 and total > 0:
                                    result['total_products'] = total
                                    result['used_api'] = base_url

                                # Если API вернул пустой список товаров, значит этот endpoint нам не подходит
                                # или нас мягко заблокировали. Прерываем этот цикл, идем к следующему API.
                                if not products:
                                    logger.warning(f"⚠️ API {base_url} вернул 200 OK, но 0 товаров на стр {page}.")
                                    if page == 1: 
                                        break # Смысла листать дальше нет, меняем версию API
                                    else:
                                        continue # Может просто страница пустая

                                # Ищем товар
                                for idx, prod in enumerate(products):
                                    global_counter += 1
                                    if prod.get('id') == target_sku:
                                        logger.info(f"🎯 НАЙДЕНО! Позиция: {global_counter} (Стр {page})")
                                        result['found'] = True
                                        result['page'] = page
                                        result['position'] = idx + 1
                                        result['absolute_pos'] = global_counter
                                        if prod.get('log'):
                                            result['is_advertising'] = True
                                            result['cpm'] = prod.get('log', {}).get('cpm')
                                        return result
                                
                                # Если нашли товары, но не наш артикул - идем на след. страницу
                                logger.info(f"✅ Стр {page}: {len(products)} товаров. Ищем дальше...")
                                
                            except json.JSONDecodeError:
                                logger.error(f"❌ Ошибка JSON на {base_url}")
                                break
                        
                        elif resp.status_code == 429:
                            logger.warning(f"⛔ 429 Too Many Requests на {base_url}. Меняю стратегию.")
                            await asyncio.sleep(2)
                            break # Меняем версию API
                        
                        else:
                            logger.warning(f"⚠️ HTTP {resp.status_code} на {base_url}")
                            break

                    except Exception as e:
                        logger.error(f"❌ Ошибка сети: {e}")
                        break
            
            # Если после прохода по всем страницам одной версии API мы нашли хоть какие-то товары (total > 0),
            # но не нашли наш артикул - значит его реально нет в топе. Не нужно менять API.
            if result['total_products'] > 0:
                logger.info("📦 Товары были найдены, но целевого артикула среди них нет.")
                break

        return result

wb_search_service = WBSearchService()