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

class UniversalSeleniumService:
    def __init__(self):
        self.driver = None
        # Твои проверенные User-Agents
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
        ]

    # --- ЧАСТЬ 1: БРУТФОРС КОРЗИН (БЫСТРО) ---

    async def _find_card_in_baskets(self, sku: int):
        """
        Параллельный поиск card.json по всем возможным корзинам.
        """
        vol = sku // 100000
        part = sku // 1000
        
        # Генерируем корзины от 01 до 21 (достаточно для 99% товаров)
        hosts = [f"{i:02d}" for i in range(1, 22)]

        async with aiohttp.ClientSession() as session:
            # Создаем список задач и запускаем их ОДНОВРЕМЕННО
            tasks = []
            for host in hosts:
                url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
                tasks.append(self._check_url(session, url, host, sku))
            
            # Ждем первый успешный ответ (as_completed возвращает итератор по мере завершения)
            for future in asyncio.as_completed(tasks):
                result = await future
                if result:
                    return result
        return None

    async def _check_url(self, session, url, host, sku):
        try:
            # Тайм-аут маленький, чтобы не висеть на мертвых серверах
            async with session.get(url, timeout=1.5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Генерируем ссылку на картинку сразу
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
        
        # 1. Сначала ищем JSON (это супер быстро)
        card = await self._find_card_in_baskets(sku)
        
        if card:
            name = card.get('imt_name') or card.get('subj_name', 'Unknown')
            brand = card.get('selling', {}).get('brand_name', '')
            image = card.get('image_url')
            
            # Пытаемся найти цену прямо в JSON (в блоке sizes)
            price = 0
            for size in card.get('sizes', []):
                # Разные форматы цены в разных версиях JSON
                p = size.get('price', {}).get('total') or size.get('price', {}).get('product') or size.get('priceU')
                if p:
                    price = int(p / 100)
                    break
            
            # Если цена нашлась в JSON — возвращаем мгновенно
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
            logger.warning(f"⚠️ JSON not found. Starting Selenium...")

        # 2. Если JSON не помог с ценой — запускаем Selenium
        return await self._selenium_get_details(sku)

    # --- ЧАСТЬ 3: ОПТИМИЗИРОВАННЫЙ SELENIUM ---

    def _init_driver(self):
        """Инициализация драйвера (ОДИН РАЗ)"""
        if self.driver: return

        chrome_options = Options()
        chrome_options.add_argument("--headless=new") # Новый быстрый headless
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
            # Ставим таймаут поменьше, чтобы не висеть вечно
            self.driver.set_page_load_timeout(20)
            logger.info("🚀 Selenium Driver initialized")
        except Exception as e:
            logger.error(f"Driver Init Failed: {e}")
            raise e

    async def _selenium_get_details(self, sku: int):
        # Запускаем в отдельном потоке, так как Selenium синхронный
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._selenium_sync_task, sku)

    def _selenium_sync_task(self, sku):
        if not self.driver: self._init_driver()
        
        url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
        result = {"valid": False, "sku": sku, "price": 0}

        try:
            self.driver.get(url)
            
            # Ждем появления цены (максимум 5 сек, не 15!)
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".price-block__wallet-price, .price-block__final-price"))
                )
            except: pass

            # 1. Пробуем вытащить данные из JS (как в твоем старом коде, но адаптировано)
            js_data = self.driver.execute_script("""
                try {
                    return window.staticModel ? JSON.stringify(window.staticModel) : 
                           (window.__INITIAL_STATE__ ? JSON.stringify(window.__INITIAL_STATE__) : null);
                } catch(e) { return null; }
            """)

            if js_data:
                data = json.loads(js_data)
                
                # Разбор формата staticModel (старый)
                if 'kindId' in data:
                    prod = data
                    result['valid'] = True
                    result['name'] = prod.get('imt_name')
                    result['brand'] = prod.get('selling', {}).get('brand_name')
                    p_val = prod.get('price', {}).get('clientPriceU') or prod.get('price', {}).get('totalPrice')
                    if p_val: result['price'] = int(p_val / 100)

                # Разбор формата INITIAL_STATE (новый React)
                elif 'product' in data and 'product' in data['product']:
                    prod = data['product']['product']
                    result['valid'] = True
                    result['name'] = prod.get('name')
                    result['brand'] = prod.get('brand')
                    result['price'] = int(prod.get('salePriceU', 0) / 100)

                if result['price'] > 0:
                    logger.info(f"✅ Found via Selenium JS: {result['price']}₽")
                    return result

            # 2. Если JS не сработал — ищем в DOM регуляркой (Fallback)
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            prices = re.findall(r'(\d[\d\s]*)\s?₽', body_text)
            
            valid_prices = []
            for p in prices:
                clean = int(p.replace(' ', '').replace('\xa0', ''))
                if 100 < clean < 1000000: valid_prices.append(clean)
            
            if valid_prices:
                result['price'] = min(valid_prices) # Минимальная цена на странице
                result['valid'] = True
                result['name'] = self.driver.title.split(' - ')[0]
                logger.info(f"✅ Found via Text: {result['price']}₽")
                return result

        except Exception as e:
            logger.error(f"Selenium error: {e}")
            self.driver.quit()
            self.driver = None # Сброс, чтобы пересоздать в след. раз

        return result

    # --- МЕТОДЫ ДЛЯ БИДДЕРА И SEO (Тоже оптимизированы) ---
    
    def get_search_auction(self, query: str):
        # Синхронный метод для executor'а
        if not self.driver: self._init_driver()
        url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}&sort=popular"
        ads = []
        try:
            self.driver.get(url)
            # Ждем каталог
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

    def get_seo_position(self, query: str, sku: int, geo: str = "moscow"):
        # Синхронный метод для executor'а
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
                # Ждем боди, а не каталог - быстрее
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