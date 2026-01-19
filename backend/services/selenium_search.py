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
logger = logging.getLogger("SeleniumSearch")

# Папка для скриншотов ошибок (чтобы вы могли видеть, что видит бот)
DEBUG_DIR = "debug_screenshots"
os.makedirs(DEBUG_DIR, exist_ok=True)

GEO_COOKIES = {
    "moscow": {"x-geo-id": "moscow", "dst": "-1257786"},
    "spb": {"x-geo-id": "spb", "dst": "-1257786"}, 
    "ekb": {"x-geo-id": "ekb", "dst": "-1113276"},
    "krasnodar": {"x-geo-id": "krasnodar", "dst": "-1192533"},
    "kazan": {"x-geo-id": "kazan", "dst": "-2133464"},
}

class OptimizedSeleniumService:
    def __init__(self):
        self.driver = None

    def _init_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless=new") 
        # ВАЖНО: Возвращаем нормальную загрузку, так как WB это Single Page App
        chrome_options.page_load_strategy = 'normal' 
        
        # Маскировка
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        # Реальный User-Agent десктопа
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

        try:
            self.driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options
            )
            self.driver.set_page_load_timeout(30)
            logger.info("🚀 Selenium Driver initialized (Full Load Mode)")
        except Exception as e:
            logger.error(f"Failed to init driver: {e}")
            raise e

    def _set_geo_cookies(self, geo: str):
        if "wildberries.ru" not in self.driver.current_url:
            try:
                self.driver.get("https://www.wildberries.ru/404")
                time.sleep(1)
            except: pass

        cookies = GEO_COOKIES.get(geo)
        if cookies:
            for name, value in cookies.items():
                self.driver.add_cookie({"name": name, "value": value, "domain": ".wildberries.ru"})
            self.driver.refresh()
            time.sleep(2) # Даем время на применение региона

    def get_position(self, query: str, sku: int, geo: str = "moscow", max_pages: int = 5):
        if not self.driver:
            self._init_driver()

        target_sku = int(sku)
        result = {
            "sku": target_sku, "query": query, "geo": geo,
            "found": False, "page": None, "position": None,
            "absolute_pos": None, "total_products": 0,
            "is_advertising": False, "cpm": None
        }

        try:
            self._set_geo_cookies(geo)
        except Exception as e:
            logger.warning(f"Geo set error: {e}")

        global_counter = 0

        for page in range(1, max_pages + 1):
            url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}&page={page}&sort=popular"
            logger.info(f"📄 Loading Page {page}...")
            
            try:
                self.driver.get(url)
                
                # 1. Ждем загрузки карточек (до 10 секунд)
                try:
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "product-card"))
                    )
                except Exception:
                    logger.warning(f"Timeout waiting for cards on page {page}. Checking page title...")
                    
                    # ДЕБАГ: Проверяем, не забанили ли нас
                    title = self.driver.title
                    logger.info(f"Page Title: {title}")
                    
                    # Делаем скриншот ошибки
                    screenshot_path = f"{DEBUG_DIR}/error_page_{page}.png"
                    self.driver.save_screenshot(screenshot_path)
                    logger.warning(f"📸 Screenshot saved to {screenshot_path}")
                    
                    if "Access Denied" in title or "Just a moment" in title:
                        logger.error("⛔ BLOCKED by Cloudflare/WB Security")
                        break
                    
                    # Если тайтл нормальный, но карточек нет - возможно, товаров просто нет
                    if page == 1:
                        logger.warning("No cards found even though access seems OK.")
                    
                    # Если это не первая страница, может товары кончились
                    if page > 1: break
                    continue

                # 2. Попытка №1: Быстрый JSON (через JS)
                products_data = []
                try:
                    js_data = self.driver.execute_script("return window.__INITIAL_STATE__")
                    # Пробуем разные пути (WB меняет их)
                    if js_data:
                        products_data = (
                            js_data.get('catalog', {}).get('data', {}).get('products', []) or
                            js_data.get('payload', {}).get('products', [])
                        )
                except: pass

                # 3. Попытка №2: Парсинг DOM (Медленно, но надежно)
                if not products_data:
                    logger.info("⚠️ JSON method failed or empty. Fallback to DOM parsing.")
                    # Ищем элементы в HTML
                    card_elements = self.driver.find_elements(By.CLASS_NAME, "product-card")
                    
                    for el in card_elements:
                        try:
                            # Пытаемся достать ID из атрибутов или ссылки
                            # WB часто кладет ID в id="c123456"
                            el_id_str = el.get_attribute('id') # c123456
                            nm_id = int(el_id_str.replace('c', '')) if el_id_str else 0
                            
                            # Проверяем рекламу (класс .product-card--ad или наличие блока)
                            is_ad = "product-card--ad" in el.get_attribute("class")
                            
                            products_data.append({
                                "id": nm_id,
                                "log": {"cpm": 0} if is_ad else None # Фейковый лог, чтобы пометить как рекламу
                            })
                        except: continue

                if not products_data:
                    logger.warning(f"Page {page}: No products extracted via DOM or JSON.")
                    continue

                logger.info(f"✅ Extracted {len(products_data)} products from Page {page}")

                # 4. Поиск в списке
                for idx, p in enumerate(products_data):
                    global_counter += 1
                    
                    # Сравнение
                    if p.get('id') == target_sku:
                        logger.info(f"🎯 FOUND! Page {page}, Pos {idx+1}")
                        result['found'] = True
                        result['page'] = page
                        result['position'] = idx + 1
                        result['absolute_pos'] = global_counter
                        
                        if p.get('log'):
                            result['is_advertising'] = True
                            result['cpm'] = p.get('log', {}).get('cpm')
                        
                        return result

            except Exception as e:
                logger.error(f"Page {page} fatal error: {e}")
                self.driver.quit()
                self._init_driver()
                break

        return result

    def close(self):
        if self.driver:
            self.driver.quit()

selenium_service = OptimizedSeleniumService()