import logging
import time
import json
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SeleniumService")

# Папка для скриншотов ошибок
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

    def _init_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless=new") 
        chrome_options.page_load_strategy = 'normal'
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

        try:
            self.driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options
            )
            self.driver.set_page_load_timeout(30)
            logger.info("🚀 Selenium Driver initialized")
        except Exception as e:
            logger.error(f"Failed to init driver: {e}")
            raise e

    def _set_geo_cookies(self, geo: str):
        if not self.driver: return
        # Переход на домен для установки кук
        if "wildberries.ru" not in self.driver.current_url:
            try:
                self.driver.get("https://www.wildberries.ru/404")
                time.sleep(0.5)
            except: pass

        cookies = GEO_COOKIES.get(geo, GEO_COOKIES["moscow"])
        for name, value in cookies.items():
            self.driver.add_cookie({"name": name, "value": value, "domain": ".wildberries.ru"})
        self.driver.refresh()
        time.sleep(1.5) # Время на применение региона

    def _extract_json_state(self):
        """Безопасное извлечение JSON состояния"""
        try:
            return self.driver.execute_script("return window.__INITIAL_STATE__")
        except:
            return None

    # --- МЕТОД 1: SEO Поиск (Позиции) ---
    def get_seo_position(self, query: str, sku: int, geo: str = "moscow", max_pages: int = 5):
        if not self.driver: self._init_driver()
        
        target_sku = int(sku)
        result = {"sku": target_sku, "query": query, "geo": geo, "found": False, "page": None, "position": None, "total_products": 0}

        try:
            self._set_geo_cookies(geo)
        except Exception as e:
            logger.warning(f"Geo error: {e}")

        global_counter = 0

        for page in range(1, max_pages + 1):
            url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}&page={page}&sort=popular"
            try:
                self.driver.get(url)
                WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, "catalog")))
                
                js_data = self._extract_json_state()
                products = []
                if js_data:
                    products = (js_data.get('catalog', {}).get('data', {}).get('products', []) or 
                                js_data.get('payload', {}).get('products', []))
                
                if not products:
                    logger.warning(f"Page {page} empty.")
                    if page == 1: break
                    continue

                if page == 1: result['total_products'] = len(products) * 10

                for idx, p in enumerate(products):
                    global_counter += 1
                    if p.get('id') == target_sku:
                        result.update({
                            "found": True, "page": page, "position": idx + 1, 
                            "absolute_pos": global_counter, 
                            "price": p.get('salePriceU', 0) / 100,
                            "is_advertising": 'log' in p
                        })
                        return result
            except Exception as e:
                logger.error(f"SEO Search error on page {page}: {e}")
                break
        return result

    # --- МЕТОД 2: Сканер (Данные о товаре) ---
    def get_product_details(self, sku: int):
        if not self.driver: self._init_driver()
        
        url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
        result = {"sku": sku, "valid": False, "price": 0, "name": "", "rating": 0, "review_count": 0}

        try:
            self.driver.get(url)
            # Ждем загрузки цены
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "price-block__final-price")))
            
            # Извлекаем данные через JS (быстрее и надежнее)
            js_data = self._extract_json_state()
            if js_data:
                product_data = js_data.get('product', {}).get('product', {})
                if not product_data:
                     # Фолбэк для другой структуры
                     product_data = js_data.get('payload', {}).get('data', {})

                if product_data:
                    result['valid'] = True
                    result['name'] = product_data.get('name', 'Unknown')
                    result['price'] = product_data.get('salePriceU', 0) / 100
                    result['rating'] = product_data.get('reviewRating', 0)
                    result['review_count'] = product_data.get('feedbacks', 0)
                    result['brand'] = product_data.get('brand', '')
                    return result
            
            # Если JS не сработал, парсим HTML
            try:
                price_el = self.driver.find_element(By.CLASS_NAME, "price-block__final-price")
                result['price'] = int(''.join(filter(str.isdigit, price_el.text)))
                result['name'] = self.driver.find_element(By.CLASS_NAME, "product-page__header").text
                result['valid'] = True
            except: pass

        except Exception as e:
            logger.error(f"Product detail error: {e}")
            # Перезапуск при фатальной ошибке
            self.driver.quit()
            self._init_driver()

        return result

    # --- МЕТОД 3: Биддер (Анализ рекламы) ---
    def get_search_auction(self, query: str):
        """Парсит рекламную выдачу (кто платит за рекламу)"""
        if not self.driver: self._init_driver()
        
        url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}&sort=popular"
        ads = []
        
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, "catalog")))
            
            js_data = self._extract_json_state()
            if js_data:
                products = (js_data.get('catalog', {}).get('data', {}).get('products', []) or 
                            js_data.get('payload', {}).get('products', []))
                
                for idx, p in enumerate(products):
                    # Если есть поле log - это реклама (или promoInfo)
                    if 'log' in p:
                        ads.append({
                            "position": idx + 1,
                            "id": p.get('id'),
                            "cpm": p.get('log', {}).get('cpm', 0),
                            "promo_pos": p.get('log', {}).get('promoPosition', 0),
                            "name": p.get('name'),
                            "brand": p.get('brand'),
                            "price": p.get('salePriceU', 0) / 100
                        })
                        
                        # Берем топ-20 рекламных мест, дальше не интересно
                        if len(ads) >= 20: break
        except Exception as e:
            logger.error(f"Auction parsing error: {e}")
            
        return ads

    def close(self):
        if self.driver: self.driver.quit()

selenium_service = UniversalSeleniumService()