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
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ]

    # --- ЧАСТЬ 1: API (МГНОВЕННО И ТОЧНО) ---

    async def get_product_details(self, sku: int):
        sku = int(sku)
        logger.info(f"⚡ Scanning SKU: {sku} via API")
        
        # 1. Пробуем Mobile API (Самый надежный метод 2025)
        # Этот endpoint используется официальным приложением и сайтом
        url = f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={sku}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5.0) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        products = data.get('data', {}).get('products', [])
                        
                        if products:
                            p = products[0]
                            # Генерация ссылки на фото (алгоритм WB)
                            image_url = self._get_image_url(p.get('id'))
                            
                            # Цена (ищем минимальную среди размеров, как делает WB)
                            price = 0
                            for size in p.get('sizes', []):
                                current_price = size.get('price', {}).get('total') or size.get('priceU')
                                if current_price:
                                    current_price = int(current_price / 100)
                                    if price == 0 or current_price < price:
                                        price = current_price
                            
                            logger.info(f"✅ Found via API: {price}₽")
                            return {
                                "valid": True,
                                "sku": p.get('id'),
                                "name": p.get('name', ''),
                                "brand": p.get('brand', ''),
                                "price": price,
                                "image": image_url,
                                "rating": p.get('reviewRating', 0),
                                "review_count": p.get('feedbacks', 0)
                            }
        except Exception as e:
            logger.warning(f"API Scan failed: {e}")

        # 2. Если API не ответил — запускаем Selenium (Fallback)
        logger.warning(f"⚠️ API failed. Starting Selenium fallback...")
        return await self._selenium_get_details(sku)

    def _get_image_url(self, sku):
        """Алгоритм генерации ссылки на фото без перебора"""
        if not sku: return ""
        _vol = sku // 100000
        _part = sku // 1000
        
        # Определение хоста корзины по диапазонам (актуально на 2025)
        if 0 <= _vol <= 143: basket = "01"
        elif 144 <= _vol <= 287: basket = "02"
        elif 288 <= _vol <= 431: basket = "03"
        elif 432 <= _vol <= 719: basket = "04"
        elif 720 <= _vol <= 1007: basket = "05"
        elif 1008 <= _vol <= 1061: basket = "06"
        elif 1062 <= _vol <= 1115: basket = "07"
        elif 1116 <= _vol <= 1169: basket = "08"
        elif 1170 <= _vol <= 1313: basket = "09"
        elif 1314 <= _vol <= 1601: basket = "10"
        elif 1602 <= _vol <= 1655: basket = "11"
        elif 1656 <= _vol <= 1919: basket = "12"
        elif 1920 <= _vol <= 2045: basket = "13"
        elif 2046 <= _vol <= 2189: basket = "14"
        elif 2190 <= _vol <= 2405: basket = "15"
        elif 2406 <= _vol <= 2621: basket = "16"
        elif 2622 <= _vol <= 2837: basket = "17"
        else: basket = "18" # Для новых товаров часто 18+

        # Для очень новых товаров может быть basket-20+, поэтому если картинка не грузится
        # фронт обычно сам подбирает, но мы дадим наиболее вероятную.
        return f"https://basket-{basket}.wbbasket.ru/vol{_vol}/part{_part}/{sku}/images/c246x328/1.webp"

    # --- ЧАСТЬ 2: SELENIUM (РЕЗЕРВ) ---

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
            self.driver.set_page_load_timeout(30)
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
            await asyncio.sleep(2) # Даем прогрузиться скриптам

            # Попытка 1: JSON из JS (самая надежная)
            json_data = self.driver.execute_script("""
                return window.__INITIAL_STATE__ ? JSON.stringify(window.__INITIAL_STATE__) : null;
            """)

            if json_data:
                data = json.loads(json_data)
                try:
                    # Путь к данным в новом React-интерфейсе WB
                    prod = data.get('product', {}).get('product', {})
                    if prod:
                        result['valid'] = True
                        result['name'] = prod.get('name')
                        result['brand'] = prod.get('brand')
                        result['rating'] = prod.get('reviewRating')
                        result['review_count'] = prod.get('feedbacks')
                        result['price'] = int(prod.get('salePriceU', 0) / 100)
                        
                        logger.info(f"✅ Found via Selenium JS: {result['price']}₽")
                        return result
                except: pass

            # Попытка 2: Тупой поиск текста (если JS спрятан)
            text = self.driver.find_element(By.TAG_NAME, "body").text
            prices = re.findall(r'(\d[\d\s]*)\s?₽', text)
            valid_prices = [int(p.replace(' ', '').replace('\xa0', '')) for p in prices]
            valid_prices = [p for p in valid_prices if 100 < p < 1000000]
            
            if valid_prices:
                result['price'] = min(valid_prices)
                result['valid'] = True
                result['name'] = self.driver.title.split(' - ')[0]
                logger.info(f"✅ Found via Text Search: {result['price']}₽")
                return result

        except Exception as e:
            logger.error(f"Selenium error: {e}")
            self.driver.quit()
            self.driver = None

        return result

    # --- МЕТОДЫ ДЛЯ SEO и БИДДЕРА ---
    def get_search_auction(self, query: str):
        if not self.driver: self._init_driver()
        url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}&sort=popular"
        ads = []
        try:
            self.driver.get(url)
            time.sleep(2)
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