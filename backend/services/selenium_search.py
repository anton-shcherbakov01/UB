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
            for size in card.get('sizes', []):
                total_stock = sum(s.get('qty', 0) for s in size.get('stocks', []))
                if total_stock == 0: continue
                p = size.get('price', {}).get('total') or size.get('price', {}).get('product') or size.get('priceU')
                if p: real_prices.append(int(p / 100))
            
            if real_prices:
                final_price = min(real_prices)
                logger.info(f"✅ Found VALID price in JSON (Stock > 0): {final_price}₽")
                return {
                    "valid": True, "sku": sku, "name": name, 
                    "brand": brand, "price": final_price, 
                    "image": image, "rating": 0, "review_count": 0
                }
            else:
                logger.warning(f"⚠️ JSON found, but NO STOCK. Trying Selenium...")
        else:
            logger.warning(f"⚠️ JSON not found. Starting Selenium...")

        # 2. Selenium
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._selenium_sync_task, sku)

    # --- ЧАСТЬ 3: SELENIUM (С JS V3) ---

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
            time.sleep(4) # Чуть дольше ждем
            self.driver.execute_script("window.scrollTo(0, 400);")
            time.sleep(2)

            # 1. НОВЫЙ МЕТОД JS (SSR Data)
            # WB хранит данные в скрытом скрипте с ID "ssr-state" или "product-data"
            js_data = self.driver.execute_script("""
                try {
                    // Метод 1: Initial State
                    if (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.product) 
                        return JSON.stringify(window.__INITIAL_STATE__.product);
                    
                    // Метод 2: Static Model
                    if (window.staticModel) return JSON.stringify(window.staticModel);
                    
                    // Метод 3: Поиск в DOM скриптах
                    var scripts = document.querySelectorAll('script');
                    for(var i=0; i<scripts.length; i++) {
                        if(scripts[i].innerText.includes('"clientPriceU"')) {
                            return scripts[i].innerText;
                        }
                    }
                    return null;
                } catch(e) { return null; }
            """)

            if js_data:
                # Пытаемся найти цены в JSON
                try:
                    # Чистим JSON если он грязный (из скрипта)
                    if "window.__INITIAL_STATE__=" in js_data:
                        js_data = js_data.split("window.__INITIAL_STATE__=")[1].split(";")[0]
                    
                    # Ищем все вхождения "clientPriceU": 155500
                    prices = re.findall(r'"clientPriceU":\s*(\d+)', js_data)
                    prices_rub = [int(int(p)/100) for p in prices]
                    
                    # Фильтруем (1000 - 500000)
                    valid_p = [p for p in prices_rub if 1000 <= p <= 500000]
                    
                    if valid_p:
                        result['price'] = min(valid_p)
                        result['valid'] = True
                        result['name'] = self.driver.title.split(' - ')[0]
                        logger.info(f"✅ Found via Deep JS Scan: {result['price']}₽")
                        return result
                except: pass

            # 2. DOM SEARCH (ПО БЛОКУ ЦЕНЫ)
            # Ищем конкретно блок цены, а не весь текст
            try:
                # Селектор цены кошелька (обычно фиолетовая)
                price_el = self.driver.find_element(By.CSS_SELECTOR, ".price-block__wallet-price")
                price_text = price_el.text.replace(' ', '').replace('₽', '').replace('\xa0', '')
                if price_text.isdigit():
                    result['price'] = int(price_text)
                    result['valid'] = True
                    result['name'] = self.driver.title.split(' - ')[0]
                    logger.info(f"✅ Found via CSS Selector: {result['price']}₽")
                    return result
            except: pass

            # 3. TEXT FALLBACK (С ФИЛЬТРОМ)
            # Если ничего не помогло, ищем в тексте, но фильтруем < 1000р (так как у тебя товар дорогой)
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            matches = re.findall(r'(\d[\d\s]*)\s?₽', body_text)
            
            valid_prices = []
            for match in matches:
                val = int(match.replace(' ', '').replace('\xa0', ''))
                # ФИЛЬТР: Цена должна быть больше 1000р (защита от рассрочки 492р)
                # Если товар реально стоит 500р, можно уменьшить порог, но для твоего кейса это спасет.
                if 1000 <= val <= 500000: 
                    valid_prices.append(val)

            if valid_prices:
                result['price'] = min(valid_prices)
                result['valid'] = True
                result['name'] = self.driver.title.split(' - ')[0]
                logger.info(f"✅ Found via Text (Filtered >1000): {result['price']}₽")
                return result
            
            # Скриншот
            self.driver.save_screenshot(f"{DEBUG_DIR}/fail_price_{sku}.png")

        except Exception as e:
            logger.error(f"Selenium error: {e}")
            self.driver.quit()
            self.driver = None 

        return result

    # --- МЕТОДЫ ДЛЯ БИДДЕРА И SEO ---
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