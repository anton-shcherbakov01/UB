import logging
import asyncio
import aiohttp
import json
import random
import os
import re
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("UniversalParser")

DEBUG_DIR = "debug_screenshots"
os.makedirs(DEBUG_DIR, exist_ok=True)

GEO_COOKIES = {
    "moscow": {"x-geo-id": "moscow", "dst": "-1257786"},
    "spb": {"x-geo-id": "spb", "dst": "-1257786"}, 
    "ekb": {"x-geo-id": "ekb", "dst": "-1113276"},
    "krasnodar": {"x-geo-id": "krasnodar", "dst": "-1192533"},
    "kazan": {"x-geo-id": "kazan", "dst": "-2133464"},
}

class UniversalSeleniumService:
    def __init__(self):
        self.driver = None
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ]

    # --- ЧАСТЬ 1: БРУТФОРС JSON (ТОЧНЫЙ) ---

    async def _find_card_in_baskets(self, sku: int):
        vol = sku // 100000
        part = sku // 1000
        hosts = [f"{i:02d}" for i in range(1, 51)] # 50 корзин

        async with aiohttp.ClientSession() as session:
            tasks = [self._check_url(session, f"https://basket-{h}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json", h, sku) for h in hosts]
            
            for future in asyncio.as_completed(tasks):
                result = await future
                if result: return result
        return None

    async def _check_url(self, session, url, host, sku):
        try:
            async with session.get(url, timeout=3.0) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    vol = sku // 100000
                    part = sku // 1000
                    data['image_url'] = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"
                    return data
        except: return None

    # --- ЧАСТЬ 2: ЛОГИКА ЦЕНЫ ---

    async def get_product_details(self, sku: int):
        sku = int(sku)
        logger.info(f"⚡ Scanning SKU: {sku}")
        
        # 1. Поиск JSON
        card = await self._find_card_in_baskets(sku)
        
        if card:
            name = card.get('imt_name') or card.get('subj_name', 'Unknown')
            brand = card.get('selling', {}).get('brand_name', '')
            image = card.get('image_url')
            
            # --- ИЩЕМ ЦЕНУ С УЧЕТОМ НАЛИЧИЯ ---
            real_prices = []
            
            # Перебираем размеры
            for size in card.get('sizes', []):
                # Проверяем сток (есть ли товар в наличии)
                total_stock = sum(s.get('qty', 0) for s in size.get('stocks', []))
                
                # Если сток 0, цену игнорируем (она может быть старой)
                if total_stock == 0: continue

                # Извлекаем цену
                p = size.get('price', {}).get('total') or size.get('price', {}).get('product') or size.get('priceU')
                if p:
                    real_prices.append(int(p / 100))
            
            # Если нашли цены среди товаров В НАЛИЧИИ
            if real_prices:
                final_price = min(real_prices)
                logger.info(f"✅ Found VALID price in JSON (Stock > 0): {final_price}₽")
                return {
                    "valid": True, "sku": sku, "name": name, 
                    "brand": brand, "price": final_price, 
                    "image": image, "rating": 0, "review_count": 0
                }
            else:
                logger.warning(f"⚠️ JSON found, but NO STOCK available. Trying Selenium for visual price...")
        else:
            logger.warning(f"⚠️ JSON not found (checked 01-50). Starting Selenium...")

        # 2. Selenium
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._selenium_sync_task, sku)

    # --- ЧАСТЬ 3: SELENIUM (ЗАЩИТА ОТ КРЕДИТОВ) ---

    def _init_driver(self):
        if self.driver: return
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(f"user-agent={random.choice(self.user_agents)}")

        try:
            self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            self.driver.set_page_load_timeout(60)
            logger.info("🚀 Selenium Driver initialized")
        except Exception as e:
            logger.error(f"Driver Init Failed: {e}")
            raise e

    def _selenium_sync_task(self, sku):
        if not self.driver: self._init_driver()
        url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
        result = {"valid": False, "sku": sku, "price": 0}

        try:
            self.driver.get(url)
            time.sleep(3)
            self.driver.execute_script("window.scrollTo(0, 400);")
            time.sleep(2)

            # 1. JS PARSING (Приоритет)
            js_data = self.driver.execute_script("""
                try {
                    // Пробуем разные места, куда WB прячет данные
                    if (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.product) 
                        return JSON.stringify(window.__INITIAL_STATE__.product);
                    if (window.staticModel) 
                        return JSON.stringify(window.staticModel);
                    return null;
                } catch(e) { return null; }
            """)

            if js_data:
                data = json.loads(js_data)
                
                # Логика извлечения из product (React)
                prod = data.get('product') or data
                
                # Имя/Бренд
                result['valid'] = True
                result['name'] = prod.get('name') or prod.get('imt_name')
                result['brand'] = prod.get('brand') or prod.get('selling', {}).get('brand_name')

                # Цена (приоритет - clientPriceU, затем salePriceU)
                # Смотрим массив sizes, если есть
                price_found = 0
                sizes = prod.get('sizes', [])
                if sizes:
                    # Ищем мин цену среди размеров
                    prices = []
                    for s in sizes:
                        p = s.get('price', {}).get('total') or s.get('price', {}).get('clientPriceU') or s.get('salePriceU')
                        if p: prices.append(int(p / 100))
                    if prices: price_found = min(prices)
                
                # Если в размерах пусто, смотрим общую цену
                if price_found == 0:
                    p_obj = prod.get('price', {})
                    raw_price = p_obj.get('clientPriceU') or p_obj.get('salePriceU') or prod.get('salePriceU') or prod.get('clientPriceU')
                    if raw_price: price_found = int(raw_price / 100)

                if price_found > 0:
                    result['price'] = price_found
                    logger.info(f"✅ Found via Selenium JS: {result['price']}₽")
                    return result

            # 2. TEXT SEARCH (С ЗАЩИТОЙ ОТ СПЛИТА)
            # Если JS не сработал, читаем текст, но фильтруем мусор
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            
            # Регулярка: ищет число + символ рубля, но проверяет, нет ли рядом слова "мес"
            # (\d[\d\s]*) - число
            # \s?₽ - знак рубля
            # (?!.*мес) - негативный просмотр (не работает в findall напрямую так просто, делаем циклом)
            
            raw_matches = re.findall(r'(\d[\d\s]*)\s?₽', body_text)
            
            valid_prices = []
            for match in raw_matches:
                # Очищаем от пробелов
                clean_str = match.replace(' ', '').replace('\xa0', '')
                if not clean_str.isdigit(): continue
                val = int(clean_str)
                
                # Фильтр 1: Слишком дешево (скорее всего кредит) или слишком дорого
                if val < 500 or val > 500000: continue
                
                # Фильтр 2: Проверка контекста (есть ли эта цена в тексте рядом со словом "мес")
                # Это грубая проверка, но работает.
                # Если число 492, и в тексте есть "492 ₽ / мес", мы его игнорируем
                if f"{match} ₽ / мес" in body_text or f"{match}₽ / мес" in body_text:
                    continue
                
                valid_prices.append(val)

            if valid_prices:
                # Обычно цена продажи - это минимальная адекватная цена на экране (не считая кредитов)
                result['price'] = min(valid_prices)
                result['valid'] = True
                result['name'] = self.driver.title.split(' - ')[0]
                logger.info(f"✅ Found via Smart Text Search: {result['price']}₽")
                return result
            
            # Скриншот, если все сломалось
            self.driver.save_screenshot(f"{DEBUG_DIR}/fail_price_{sku}.png")

        except Exception as e:
            logger.error(f"Selenium error: {e}")
            self.driver.quit()
            self.driver = None 

        return result

    # --- МЕТОДЫ ДЛЯ БИДДЕРА И SEO (ОСТАВЛЯЕМ КАК ЕСТЬ) ---
    def get_search_auction(self, query: str):
        if not self.driver: self._init_driver()
        url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}&sort=popular"
        ads = []
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.ID, "catalog")))
            js_data = self.driver.execute_script("return window.__INITIAL_STATE__")
            if js_data:
                products = (js_data.get('catalog', {}).get('data', {}).get('products', []) or 
                            js_data.get('payload', {}).get('products', []))
                for idx, p in enumerate(products):
                    if 'log' in p:
                        ads.append({
                            "position": idx + 1, "id": p.get('id'), "cpm": p.get('log', {}).get('cpm', 0),
                            "brand": p.get('brand'), "name": p.get('name')
                        })
                        if len(ads) >= 20: break
        except: pass
        return ads

    def get_seo_position(self, query: str, sku: int, geo: str = "moscow"):
        if not self.driver: self._init_driver()
        sku = int(sku)
        result = {"found": False, "page": None, "position": None, "absolute_pos": None}
        try:
            if "wildberries.ru" not in self.driver.current_url:
                self.driver.get("https://www.wildberries.ru/404")
            cookies = GEO_COOKIES.get(geo, GEO_COOKIES["moscow"])
            for name, value in cookies.items():
                self.driver.add_cookie({"name": name, "value": value, "domain": ".wildberries.ru"})
            self.driver.refresh()
        except: pass

        global_counter = 0
        for page in range(1, 6):
            url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}&page={page}&sort=popular"
            try:
                self.driver.get(url)
                WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                js_data = self.driver.execute_script("return window.__INITIAL_STATE__")
                products = []
                if js_data:
                    products = (js_data.get('catalog', {}).get('data', {}).get('products', []) or 
                                js_data.get('payload', {}).get('products', []))
                if not products: break
                for idx, p in enumerate(products):
                    global_counter += 1
                    if p.get('id') == sku:
                        result.update({
                            "found": True, "page": page, "position": idx + 1, "absolute_pos": global_counter, "is_advertising": 'log' in p
                        })
                        return result
            except: break
        return result

    def close(self):
        if self.driver: self.driver.quit()

selenium_service = UniversalSeleniumService()