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
        # Свежие юзер-агенты (Март 2024)
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ]

    # --- ЧАСТЬ 1: БЫСТРЫЙ ПОИСК ЧЕРЕЗ КОРЗИНЫ (AIOHTTP) ---

    def _calc_basket(self, sku: int) -> str:
        """Стандартный расчет корзины (как ориентир)"""
        vol = sku // 100000
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
        if 2190 <= vol <= 2405: return "15"
        return "16" # Fallback

    async def _find_card_in_baskets(self, sku: int):
        """
        Брутфорс корзин (как в старом коде).
        Это самый быстрый способ получить данные без браузера.
        """
        vol = sku // 100000
        part = sku // 1000
        calculated = self._calc_basket(sku)
        
        # Приоритетный список хостов: расчетный + топ популярных + остальные
        hosts = [calculated, "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15", "16", "17"]
        hosts = list(dict.fromkeys(hosts)) # Убрать дубли

        async with aiohttp.ClientSession() as session:
            # Запускаем все запросы параллельно! (Это займет < 0.5 сек)
            tasks = []
            for host in hosts:
                url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
                tasks.append(self._check_url(session, url, host, sku))
            
            # Ждем первого успешного ответа
            for future in asyncio.as_completed(tasks):
                result = await future
                if result: return result
        
        return None

    async def _check_url(self, session, url, host, sku):
        try:
            async with session.get(url, timeout=2.0) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Восстанавливаем ссылку на картинку
                    vol = sku // 100000
                    part = sku // 1000
                    data['image_url'] = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"
                    return data
        except: return None

    # --- ЧАСТЬ 2: ГЛАВНЫЙ МЕТОД ---

    async def get_product_details(self, sku: int):
        """
        Гибридный парсер:
        1. Ищет card.json по всем корзинам (0.2 сек)
        2. Если нашел, но нет цены -> запускает Selenium с JS-инъекцией (5 сек)
        """
        sku = int(sku)
        logger.info(f"⚡ Scanning SKU: {sku}")
        
        # Шаг 1: Ищем JSON напрямую (самый надежный метод старого скрипта)
        card = await self._find_card_in_baskets(sku)
        
        if card:
            name = card.get('imt_name') or card.get('subj_name', 'Unknown')
            brand = card.get('selling', {}).get('brand_name', '')
            image = card.get('image_url')
            
            # Пытаемся вытащить цену из sizes (WB прячет цену тут)
            price = 0
            for size in card.get('sizes', []):
                # Пробуем разные форматы цены WB
                p = size.get('price', {}).get('total') or size.get('price', {}).get('product') or size.get('priceU')
                if p:
                    price = int(p / 100)
                    break
            
            # Если цена есть - возвращаем сразу!
            if price > 0:
                logger.info(f"✅ Found in JSON: {price}₽")
                return {
                    "valid": True, "sku": sku, "name": name, 
                    "brand": brand, "price": price, 
                    "image": image, "rating": 0, "review_count": 0
                }
            else:
                logger.warning(f"⚠️ JSON found but NO PRICE. Falling back to Selenium.")
        else:
            logger.warning(f"⚠️ JSON not found in any basket. Falling back to Selenium.")

        # Шаг 2: Selenium (Тяжелая артиллерия)
        return await self._selenium_get_details(sku)

    # --- ЧАСТЬ 3: SELENIUM C JS-INJECTION (БЕЗ ОШИБОК СЕЛЕКТОРОВ) ---

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
            self.driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options
            )
            self.driver.set_page_load_timeout(25)
            logger.info("🚀 Selenium Driver initialized")
        except Exception as e:
            logger.error(f"Driver Init Failed: {e}")
            raise e

    async def _selenium_get_details(self, sku: int):
        # Оборачиваем синхронный Selenium в тредпул (по сути, простой вызов, но безопаснее)
        # В данном контексте вызовем синхронно, так как мы уже внутри async
        
        if not self.driver: self._init_driver()
        
        url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
        result = {"valid": False, "sku": sku, "price": 0}

        try:
            self.driver.get(url)
            
            # Ждем не цену, а просто загрузку body (чтобы скрипты отработали)
            try:
                WebDriverWait(self.driver, 8).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            except: pass

            # --- ГЛАВНЫЙ ТРЮК ИЗ СТАРОГО КОДА ---
            # Мы не ищем div class="price". Мы забираем данные из JS-переменных WB.
            
            # Попытка 1: window.staticModel (как в старом коде)
            json_data = self.driver.execute_script("return window.staticModel ? JSON.stringify(window.staticModel) : null;")
            
            # Попытка 2: window.__INITIAL_STATE__ (современный React state)
            if not json_data:
                json_data = self.driver.execute_script("return window.__INITIAL_STATE__ ? JSON.stringify(window.__INITIAL_STATE__) : null;")

            if json_data:
                data = json.loads(json_data)
                
                # Парсим структуру staticModel
                if 'kindId' in data or 'products' in data: 
                    # Логика для staticModel
                    prod = data if 'kindId' in data else (data.get('products') or [{}])[0]
                    result['valid'] = True
                    result['name'] = prod.get('name') or prod.get('imt_name')
                    result['brand'] = prod.get('brandName') or prod.get('brand')
                    
                    price = prod.get('price', {}).get('clientPriceU') or prod.get('clientPriceU') or prod.get('salePriceU')
                    if price: result['price'] = int(price / 100)

                # Парсим структуру INITIAL_STATE
                elif 'product' in data:
                    prod = data['product'].get('product', {})
                    result['valid'] = True
                    result['name'] = prod.get('name')
                    result['brand'] = prod.get('brand')
                    result['price'] = int(prod.get('salePriceU', 0) / 100)

                if result['price'] > 0:
                    logger.info(f"✅ Found via Selenium JS: {result['price']}₽")
                    return result

            # Фолбэк на DOM (если JS закрыт, ищем текстом)
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            # Ищем "Цена ... ₽" регуляркой
            prices = re.findall(r'(\d[\d\s]*)\s?₽', page_text)
            if prices:
                # Берем первую цену, похожую на правду (обычно она сверху)
                for p in prices:
                    clean_p = int(p.replace(' ', '').replace('\xa0', ''))
                    if clean_p > 100: # Отсекаем мусор
                        result['price'] = clean_p
                        result['valid'] = True
                        result['name'] = self.driver.title.split(' - ')[0]
                        logger.info(f"✅ Found via Regex: {clean_p}₽")
                        return result

        except Exception as e:
            logger.error(f"Selenium Fatal: {e}")
            self.driver.quit()
            self._init_driver()

        return result

    # --- МЕТОДЫ ДЛЯ SEO и БИДДЕРА (Без изменений) ---
    def get_search_auction(self, query: str):
        if not self.driver: self._init_driver()
        url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}&sort=popular"
        ads = []
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 8).until(EC.presence_of_element_located((By.ID, "catalog")))
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
        if not self.driver: self._init_driver()
        sku = int(sku)
        result = {"found": False, "page": None, "position": None, "absolute_pos": None}
        
        try:
            # Установка куки
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
                # Ждем не каталог, а body (быстрее)
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