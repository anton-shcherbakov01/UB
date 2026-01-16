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

    # --- ЧАСТЬ 1: БРУТФОРС JSON ---

    async def _find_card_in_baskets(self, sku: int):
        vol = sku // 100000
        part = sku // 1000
        hosts = [f"{i:02d}" for i in range(1, 51)]

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

    # --- ЧАСТЬ 2: ЛОГИКА ---

    async def get_product_details(self, sku: int):
        sku = int(sku)
        logger.info(f"⚡ Scanning SKU: {sku}")
        
        # 1. Поиск JSON
        card = await self._find_card_in_baskets(sku)
        
        if card:
            name = card.get('imt_name') or card.get('subj_name', 'Unknown')
            brand = card.get('selling', {}).get('brand_name', '')
            image = card.get('image_url')
            
            real_prices = []
            for size in card.get('sizes', []):
                # Собираем все возможные ключи цены
                p_data = size.get('price', {})
                p = p_data.get('total') or p_data.get('product') or size.get('priceU') or size.get('basicPriceU')
                if p: real_prices.append(int(p / 100))
            
            if real_prices:
                final_price = min(real_prices)
                logger.info(f"✅ Found VALID price in JSON: {final_price}₽")
                return {
                    "valid": True, "sku": sku, "name": name, 
                    "brand": brand, "price": final_price, 
                    "image": image, "rating": 0, "review_count": 0
                }
            else:
                logger.warning(f"⚠️ JSON found but NO PRICE fields. Trying Selenium...")
        else:
            logger.warning(f"⚠️ JSON not found. Starting Selenium...")

        # 2. Selenium
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._selenium_sync_task, sku)

    # --- ЧАСТЬ 3: SELENIUM (С ИЗОЛЯЦИЕЙ КОНТЕЙНЕРА) ---

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

            # 1. JS INJECTION (Приоритет - данные из памяти)
            js_data = self.driver.execute_script("""
                try {
                    if (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.product) 
                        return JSON.stringify(window.__INITIAL_STATE__.product);
                    if (window.staticModel) return JSON.stringify(window.staticModel);
                    return null;
                } catch(e) { return null; }
            """)

            if js_data:
                try:
                    data = json.loads(js_data)
                    prod = data.get('product') or data
                    result['valid'] = True
                    result['name'] = prod.get('name') or prod.get('imt_name')
                    result['brand'] = prod.get('brand') or prod.get('selling', {}).get('brand_name')

                    # Извлекаем цену
                    prices_list = []
                    sizes = prod.get('sizes', [])
                    for s in sizes:
                        # Проверяем все возможные поля
                        p = s.get('price', {}).get('total') or s.get('price', {}).get('clientPriceU') or s.get('priceU')
                        if p: prices_list.append(int(p / 100))
                    
                    if not prices_list:
                        # Общая цена
                        raw = prod.get('price', {}).get('clientPriceU') or prod.get('clientPriceU') or prod.get('salePriceU')
                        if raw: prices_list.append(int(raw / 100))

                    if prices_list:
                        result['price'] = min(prices_list)
                        logger.info(f"✅ Found via Selenium JS: {result['price']}₽")
                        return result
                except: pass

            # 2. CSS SELECTORS (СКОУПЕД ПОИСК)
            # Мы ищем цену ТОЛЬКО внутри правого блока (где кнопка купить), 
            # чтобы не зацепить "похожие товары" снизу.
            
            # Попытка найти контейнер цены
            main_container = None
            try:
                # Основной контейнер цены на десктопе
                main_container = self.driver.find_element(By.CSS_SELECTOR, ".product-page__price-block")
            except:
                try:
                    # Альтернативный контейнер (иногда бывает)
                    main_container = self.driver.find_element(By.CSS_SELECTOR, ".product-page__aside-container")
                except: pass
            
            # Если нашли контейнер - ищем цену ТОЛЬКО В НЕМ
            search_context = main_container if main_container else self.driver
            
            selectors = [
                ".price-block__wallet-price",
                ".price-block__final-price", 
                ".price-block__content"
            ]
            
            for sel in selectors:
                try:
                    # Ищем ВНУТРИ контекста
                    elements = search_context.find_elements(By.CSS_SELECTOR, sel)
                    for el in elements:
                        txt = el.text
                        if not txt or "мес" in txt or "рассроч" in txt: continue
                        
                        clean = re.sub(r'[^\d]', '', txt)
                        if not clean: continue
                        val = int(clean)
                        
                        if val > 50:
                            result['price'] = val
                            result['valid'] = True
                            result['name'] = self.driver.title.split(' - ')[0]
                            logger.info(f"✅ Found via Scoped Selector '{sel}': {val}₽")
                            return result
                except: continue

            # Скриншот
            self.driver.save_screenshot(f"{DEBUG_DIR}/fail_price_{sku}.png")

        except Exception as e:
            logger.error(f"Selenium error: {e}")
            self.driver.quit()
            self.driver = None 

        return result

    # --- МЕТОДЫ БИДДЕРА И SEO ОСТАВЛЯЕМ КАК БЫЛИ ---
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