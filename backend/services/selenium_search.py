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

# Папка для отладки, если Selenium увидит капчу или белый экран
DEBUG_DIR = "debug_screenshots"
os.makedirs(DEBUG_DIR, exist_ok=True)

# Твои куки для SEO
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
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
        ]

    # --- ЧАСТЬ 1: АГРЕССИВНЫЙ ПОИСК ЧЕРЕЗ КОРЗИНЫ (AIOHTTP) ---

    async def _find_card_in_baskets(self, sku: int):
        """
        Параллельный поиск card.json по 50 корзинам.
        """
        vol = sku // 100000
        part = sku // 1000
        
        # Генерируем корзины от 01 до 50 (чтобы наверняка)
        hosts = [f"{i:02d}" for i in range(1, 51)]

        async with aiohttp.ClientSession() as session:
            tasks = []
            for host in hosts:
                url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
                tasks.append(self._check_url(session, url, host, sku))
            
            # Ждем первый успешный ответ
            for future in asyncio.as_completed(tasks):
                result = await future
                if result:
                    return result
        return None

    async def _check_url(self, session, url, host, sku):
        try:
            # Увеличил таймаут до 3 сек, чтобы не отбрасывать медленные, но живые сервера
            async with session.get(url, timeout=3.0) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    vol = sku // 100000
                    part = sku // 1000
                    data['image_url'] = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"
                    return data
        except:
            return None

    # --- ЧАСТЬ 2: ОСНОВНОЙ МЕТОД ---

    async def get_product_details(self, sku: int):
        sku = int(sku)
        logger.info(f"⚡ Scanning SKU: {sku}")
        
        # 1. Сначала ищем JSON
        card = await self._find_card_in_baskets(sku)
        
        if card:
            name = card.get('imt_name') or card.get('subj_name', 'Unknown')
            brand = card.get('selling', {}).get('brand_name', '')
            image = card.get('image_url')
            
            price = 0
            for size in card.get('sizes', []):
                p = size.get('price', {}).get('total') or size.get('price', {}).get('product') or size.get('priceU')
                if p:
                    price = int(p / 100)
                    break
            
            if price > 0:
                logger.info(f"✅ Found in JSON: {price}₽")
                return {
                    "valid": True, "sku": sku, "name": name, 
                    "brand": brand, "price": price, 
                    "image": image, "rating": 0, "review_count": 0
                }
            else:
                logger.warning(f"⚠️ JSON found but NO PRICE. Starting Selenium...")
        else:
            logger.warning(f"⚠️ JSON not found (checked 01-50). Starting Selenium...")

        # 2. Selenium Fallback
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._selenium_sync_task, sku)

    # --- ЧАСТЬ 3: SELENIUM (КАК В ТВОЕМ СТАРОМ КОДЕ) ---

    def _init_driver(self):
        if self.driver: return

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument(f"user-agent={random.choice(self.user_agents)}")

        try:
            self.driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options
            )
            # Большой таймаут, чтобы точно прогрузилось
            self.driver.set_page_load_timeout(60)
            logger.info("🚀 Selenium Driver initialized")
        except Exception as e:
            logger.error(f"Driver Init Failed: {e}")
            raise e

    def _selenium_sync_task(self, sku):
        """Синхронная задача для Executor (Блокирующая, но надежная)"""
        if not self.driver: self._init_driver()
        
        url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
        result = {"valid": False, "sku": sku, "price": 0}

        try:
            self.driver.get(url)
            
            # --- ВЕРНУЛ ТВОЙ СКРОЛЛ И SLEEP ---
            time.sleep(3) 
            self.driver.execute_script("window.scrollTo(0, 400);")
            time.sleep(2) # Ждем прогрузки после скролла
            
            # Ждем хоть что-то
            try:
                WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            except: pass

            # 1. JS INJECTION (Приоритет)
            js_data = self.driver.execute_script("""
                try {
                    return window.__INITIAL_STATE__ ? JSON.stringify(window.__INITIAL_STATE__) : 
                           (window.staticModel ? JSON.stringify(window.staticModel) : null);
                } catch(e) { return null; }
            """)

            if js_data:
                data = json.loads(js_data)
                
                # Формат INITIAL_STATE
                if 'product' in data and 'product' in data['product']:
                    prod = data['product']['product']
                    result['valid'] = True
                    result['name'] = prod.get('name')
                    result['brand'] = prod.get('brand')
                    result['price'] = int(prod.get('salePriceU', 0) / 100)

                # Формат staticModel
                elif 'kindId' in data:
                    result['valid'] = True
                    result['name'] = data.get('imt_name')
                    result['brand'] = data.get('selling', {}).get('brand_name')
                    p = data.get('price', {}).get('clientPriceU') or data.get('clientPriceU')
                    if p: result['price'] = int(p / 100)

                if result['price'] > 0:
                    logger.info(f"✅ Found via Selenium JS: {result['price']}₽")
                    return result

            # 2. DOM REGEX FALLBACK
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            prices = re.findall(r'(\d[\d\s]*)\s?₽', body_text)
            
            valid = []
            for p in prices:
                val = int(p.replace(' ', '').replace('\xa0', ''))
                if 100 < val < 1000000: valid.append(val)
            
            if valid:
                result['price'] = min(valid)
                result['valid'] = True
                result['name'] = self.driver.title.split(' - ')[0]
                logger.info(f"✅ Found via Text: {result['price']}₽")
                return result
            
            # Если ничего не нашли - делаем скриншот для отладки
            self.driver.save_screenshot(f"{DEBUG_DIR}/fail_{sku}.png")
            logger.warning(f"📸 Failed to parse. Screenshot saved to {DEBUG_DIR}/fail_{sku}.png")

        except Exception as e:
            logger.error(f"Selenium error: {e}")
            # При фатальной ошибке рестартим драйвер
            self.driver.quit()
            self.driver = None 

        return result

    # --- БИДДЕР ---
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
                            "position": idx + 1, "id": p.get('id'),
                            "cpm": p.get('log', {}).get('cpm', 0),
                            "brand": p.get('brand'), "name": p.get('name')
                        })
                        if len(ads) >= 20: break
        except: pass
        return ads

    # --- SEO ---
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
                            "found": True, "page": page, "position": idx + 1,
                            "absolute_pos": global_counter, "is_advertising": 'log' in p
                        })
                        return result
            except: break
        return result

    def close(self):
        if self.driver: self.driver.quit()

selenium_service = UniversalSeleniumService()