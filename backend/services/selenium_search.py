import logging
import asyncio
import aiohttp
import json
import random
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("UniversalParser")

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
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ]

    # --- ЧАСТЬ 1: БЫСТРЫЙ ПОИСК ЧЕРЕЗ КОРЗИНЫ (AIOHTTP) ---

    async def _find_card_in_baskets(self, sku: int):
        """
        Брутфорс ВСЕХ возможных корзин (от 01 до 25).
        Это позволяет находить даже самые новые товары без сложных формул.
        """
        vol = sku // 100000
        part = sku // 1000
        
        # Генерируем список хостов от 01 до 25 (актуально на 2025 год)
        hosts = [f"{i:02d}" for i in range(1, 26)] 

        async with aiohttp.ClientSession() as session:
            tasks = []
            for host in hosts:
                url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
                tasks.append(self._check_url(session, url, host, sku))
            
            # Ждем завершения всех, но возвращаем первый успешный
            for future in asyncio.as_completed(tasks):
                result = await future
                if result: return result
        
        return None

    async def _check_url(self, session, url, host, sku):
        try:
            # Таймаут очень короткий, чтобы не ждать мертвые сервера
            async with session.get(url, timeout=1.0) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Генерируем картинку
                    vol = sku // 100000
                    part = sku // 1000
                    data['image_url'] = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"
                    return data
        except: return None

    # --- ЧАСТЬ 2: ГЛАВНЫЙ МЕТОД ---

    async def get_product_details(self, sku: int):
        sku = int(sku)
        logger.info(f"⚡ Scanning SKU: {sku}")
        
        # 1. Пробуем JSON (Супер быстро)
        card = await self._find_card_in_baskets(sku)
        
        if card:
            name = card.get('imt_name') or card.get('subj_name', 'Unknown')
            brand = card.get('selling', {}).get('brand_name', '')
            image = card.get('image_url')
            
            price = 0
            # Ищем цену в массиве sizes
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
                logger.warning(f"⚠️ JSON found but NO PRICE. Fallback to Selenium.")
        else:
            logger.warning(f"⚠️ JSON not found (checked baskets 01-25). Fallback to Selenium.")

        # 2. Selenium Fallback
        return await self._selenium_get_details(sku)

    # --- ЧАСТЬ 3: SELENIUM (FIXED) ---

    def _init_driver(self):
        if self.driver: return

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        # Отключаем детекторы
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(f"user-agent={random.choice(self.user_agents)}")

        try:
            self.driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options
            )
            self.driver.set_page_load_timeout(40) # Увеличили таймаут
            logger.info("🚀 Selenium Driver initialized")
        except Exception as e:
            logger.error(f"Driver Init Failed: {e}")
            raise e

    async def _selenium_get_details(self, sku: int):
        if not self.driver: self._init_driver()
        
        url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
        result = {"valid": False, "sku": sku, "price": 0}

        try:
            self.driver.get(url)
            
            # Ждем загрузки JS-стейта, а не визуальных элементов
            await asyncio.sleep(3) 

            # Пытаемся достать данные из памяти браузера (самый надежный метод)
            json_data = self.driver.execute_script("""
                try {
                    return window.__INITIAL_STATE__ ? JSON.stringify(window.__INITIAL_STATE__) : 
                           (window.staticModel ? JSON.stringify(window.staticModel) : null);
                } catch(e) { return null; }
            """)

            if json_data:
                data = json.loads(json_data)
                
                # Разбор формата INITIAL_STATE
                if 'product' in data and 'product' in data['product']:
                    prod = data['product']['product']
                    result['valid'] = True
                    result['name'] = prod.get('name')
                    result['brand'] = prod.get('brand')
                    result['price'] = int(prod.get('salePriceU', 0) / 100)
                
                # Разбор формата staticModel (старый)
                elif 'kindId' in data:
                    result['valid'] = True
                    result['name'] = data.get('imt_name')
                    result['brand'] = data.get('selling', {}).get('brand_name')
                    result['price'] = int(data.get('price', {}).get('clientPriceU', 0) / 100)

                if result['price'] > 0:
                    logger.info(f"✅ Found via Selenium JS: {result['price']}₽")
                    return result

            # Фолбэк на DOM (если JS не спарсился)
            # Ищем любой текст с ценой, так как классы меняются
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            prices = re.findall(r'(\d[\d\s]*)\s?₽', body_text)
            
            # Фильтруем адекватные цены (больше 100р, меньше 1млн)
            valid_prices = []
            for p in prices:
                clean = int(p.replace(' ', '').replace('\xa0', ''))
                if 100 < clean < 1000000:
                    valid_prices.append(clean)
            
            if valid_prices:
                result['price'] = min(valid_prices) # Обычно цена продажи - самая низкая на экране
                result['valid'] = True
                result['name'] = self.driver.title.split(' - ')[0]
                logger.info(f"✅ Found via Text Search: {result['price']}₽")
                return result

        except Exception as e:
            logger.error(f"Selenium error: {e}")
            self.driver.quit()
            self.driver = None # Сброс драйвера

        return result

    # --- МЕТОДЫ ДЛЯ БИДДЕРА ---
    def get_search_auction(self, query: str):
        if not self.driver: self._init_driver()
        url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}&sort=popular"
        ads = []
        try:
            self.driver.get(url)
            # Ждем чуть дольше
            time.sleep(2)
            
            # Берем из JS
            js_data = self.driver.execute_script("return window.__INITIAL_STATE__")
            
            products = []
            if js_data:
                products = (js_data.get('catalog', {}).get('data', {}).get('products', []) or 
                            js_data.get('payload', {}).get('products', []))
            
            for idx, p in enumerate(products):
                if 'log' in p:
                    ads.append({
                        "position": idx + 1,
                        "id": p.get('id'),
                        "cpm": p.get('log', {}).get('cpm', 0),
                        "brand": p.get('brand'),
                        "name": p.get('name')
                    })
                    if len(ads) >= 20: break
        except Exception as e:
            logger.error(f"Auction error: {e}")
        return ads

    # --- МЕТОД ДЛЯ SEO (Синхронный враппер) ---
    def get_seo_position(self, query: str, sku: int, geo: str = "moscow"):
        """Поиск позиции товара (Синхронно для executor)"""
        # Этот метод запускается в executor, поэтому он должен быть синхронным
        if not self.driver: self._init_driver()
        sku = int(sku)
        result = {"found": False, "page": None, "position": None, "absolute_pos": None}
        
        try:
            if "wildberries.ru" not in self.driver.current_url:
                self.driver.get("https://www.wildberries.ru/404")
            
            geo_ids = {"moscow": "-1257786", "spb": "-1257786"}
            self.driver.add_cookie({"name": "x-geo-id", "value": geo, "domain": ".wildberries.ru"})
            self.driver.refresh()
        except: pass

        global_counter = 0
        for page in range(1, 6):
            url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}&page={page}&sort=popular"
            try:
                self.driver.get(url)
                time.sleep(2) # Ожидание загрузки JS
                
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