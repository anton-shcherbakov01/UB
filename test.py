import asyncio
import json
import random
from curl_cffi.requests import AsyncSession
from loguru import logger
from pydantic import BaseModel, Field

# --- КОНФИГУРАЦИЯ ---
TARGET_SKU = 172672138
# Ваша "сильная" строка прокси
RAW_PROXY_DATA = "http://mjpnvqmohh-mobile-country-RU-asn-12389.21378.12846.25490.29069.34168.34584.42548.8439.8675.8570.43132.35177.34267.34137.28860.24699.21017.12730.12332.12683.13118.21479.25515.29456.34205.34974.42610.8443.21487.35154.43574.25436.15468.35516.13056.35125.48322.60891.48100.8359.48541.8580.50071.49154.48123.44736.43148.42115.41771.39001.49816.48212.48000.44579.43038.42087.40993.35728.49350.48124.44895.43720.42322.41822.39811.34351.30922.29194.13055.31558.29497.13155.33894.30881.21365.42842.8402.3253.16345.21483.34038.29125.8755.42110.3216-hold-query:F1Fnj8kGBWpcdMAb@175.110.115.169:443:UBPROXIES[https://api.asocks.com/user/port/refresh/ip/4070af6b-f0c5-11f0-bf50-bc24114c89e8]"

# ЗАГОЛОВКИ CHROME 120 (строго по документу )
CHROME_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/catalog/0/detail.aspx",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
    "X-Requested-With": "XMLHttpRequest"
}

class MPStatsStyleScraper:
    def __init__(self, raw_data):
        self.raw_data = raw_data
        self.proxy_url = self._clean_proxy()

    def _clean_proxy(self):
        s = self.raw_data.replace("http://", "").replace("https://", "")
        if "@" not in s: return ""
        auth, net = s.split("@", 1)
        ip, port = net.split(":")[:2]
        return f"http://{auth}@{ip}:{port}"

    def get_basket_host(self, sku: int) -> str:
        """Алгоритм выбора хоста CDN [cite: 107-113]"""
        vol = sku // 100000
        if 0 <= vol <= 143: return '01'
        elif 144 <= vol <= 287: return '02'
        elif 288 <= vol <= 431: return '03'
        elif 432 <= vol <= 719: return '04'
        elif 720 <= vol <= 1007: return '05'
        elif 1008 <= vol <= 1061: return '06'
        elif 1062 <= vol <= 1115: return '07'
        elif 1116 <= vol <= 1169: return '08'
        elif 1170 <= vol <= 1313: return '09'
        elif 1314 <= vol <= 1601: return '10'
        elif 1602 <= vol <= 1655: return '11'
        elif 1656 <= vol <= 1919: return '12' # Ваш SKU 1726...
        else: return '13'

    async def run(self):
        logger.info("Запуск парсера (Архитектура MPStats)...")
        
        # Используем chrome120 для соответствия заголовкам [cite: 165]
        async with AsyncSession(impersonate="chrome120", proxy=self.proxy_url, timeout=30, verify=False, headers=CHROME_HEADERS) as session:
            try:
                # --- ЭТАП 1: ПОЛУЧЕНИЕ METADATA & SELLER ID (Basket API) ---
                # Этот этап критичен для получения supplierId
                vol = TARGET_SKU // 100000
                part = TARGET_SKU // 1000
                host = self.get_basket_host(TARGET_SKU)
                
                static_url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{TARGET_SKU}/info/ru/card.json"
                logger.info(f"1. Скачиваем метаданные (Basket-{host})...")
                
                resp = await session.get(static_url)
                if resp.status_code != 200:
                    logger.error(f"Ошибка Basket API: {resp.status_code}")
                    return

                info = resp.json()
                
                # --- ПОИСК ID ПРОДАВЦА (УЧИТЫВАЕМ НОВУЮ СТРУКТУРУ) ---
                seller_id = info.get('supplierId') or info.get('supplier_id')
                
                # Ищем во вложенных объектах (selling, seller)
                if not seller_id and 'selling' in info:
                     seller_id = info['selling'].get('supplier_id')
                if not seller_id and 'seller' in info:
                     seller_id = info['seller'].get('id')
                
                if not seller_id:
                    logger.error("Не удалось найти ID продавца в JSON (структура изменилась?)")
                    return
                
                logger.success(f"Продавец найден: ID {seller_id}")

                # --- ЭТАП 2: ЗАПРОС К КАТАЛОГУ ПРОДАВЦА (Catalog API) ---
                # Это "обходной путь", который использует MPStats. 
                # Запрос идет не к card.wb.ru, а к catalog.wb.ru [cite: 101]
                logger.info("2. Запрос в Каталог Продавца...")
                
                catalog_url = "https://catalog.wb.ru/sellers/catalog"
                params = {
                    "appType": 1, 
                    "curr": "rub", 
                    "dest": -1257786,  # Москва (каталог менее чувствителен к geo-mismatch)
                    "supplier": seller_id, 
                    "nm": TARGET_SKU
                }
                
                # Имитируем поведение человека: задержка после получения статики
                await asyncio.sleep(random.uniform(0.5, 1.5))
                
                resp = await session.get(catalog_url, params=params)

                if resp.status_code == 200:
                    data = resp.json()
                    products = data.get('data', {}).get('products', [])
                    
                    target = next((p for p in products if p['id'] == TARGET_SKU), None)
                    
                    if target:
                        # --- ЭТАП 3: ПАРСИНГ ДАННЫХ (Pydantic Style) ---
                        # Используем логику ценообразования из документа [cite: 124]
                        price_u = target['priceU'] / 100
                        sale_price_u = target['salePriceU'] / 100
                        discount = target['sale']
                        
                        logger.success("✅ ДАННЫЕ УСПЕШНО ПОЛУЧЕНЫ")
                        print(f"\n======== ОТЧЕТ (MPSTATS METHOD) ========")
                        print(f"Товар:   {target['name']}")
                        print(f"Бренд:   {target['brand']} (ID: {target['brandId']})")
                        print(f"Цена:    {sale_price_u} RUB (Скидка {discount}%)")
                        print(f"База:    {price_u} RUB")
                        print(f"Рейтинг: {target['reviewRating']} ({target['feedbacks']} отзывов)")
                        print(f"========================================")
                    else:
                        logger.warning("Товар есть в статике, но скрыт в каталоге (Out of Stock).")
                
                elif resp.status_code == 429:
                    logger.error("429 Too Many Requests (Catalog). Попробуйте сменить IP.")
                
                elif resp.status_code == 404:
                     logger.error("404 Not Found. Возможно, продавец скрыл каталог.")

            except Exception as e:
                logger.error(f"Критическая ошибка: {e}")

if __name__ == "__main__":
    scraper = MPStatsStyleScraper(RAW_PROXY_DATA)
    asyncio.run(scraper.run())