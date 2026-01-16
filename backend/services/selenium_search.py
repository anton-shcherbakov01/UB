import json
import logging
import time
import random
from typing import Dict, Any, List

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SeleniumSearch")

# Cookie для подмены региона (geo). 
# WB хранит регион в куках x-geo-id, dst, и т.д.
# Значения ниже примерные, для точной геолокации лучше использовать прокси нужного региона.
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
        self._init_driver()

    def _init_driver(self):
        """Инициализация максимально облегченного браузера"""
        chrome_options = Options()
        
        # --- ОПТИМИЗАЦИЯ СКОРОСТИ ---
        # 1. Headless (без GUI)
        chrome_options.add_argument("--headless=new") 
        # 2. Не ждать полной загрузки (картинок/скриптов аналитики)
        chrome_options.page_load_strategy = 'eager' 
        
        # 3. Отключаем лишнее
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        
        # 4. Маскировка под обычного пользователя (Anti-Detect)
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        try:
            self.driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options
            )
            self.driver.set_page_load_timeout(15) # Тайм-аут 15 сек макс
            logger.info("🚀 Selenium Driver initialized in SUPER-FAST mode")
        except Exception as e:
            logger.error(f"Failed to init driver: {e}")
            self.driver = None

    def _set_geo_cookies(self, geo: str):
        """Пытаемся выставить регион через куки"""
        if not self.driver: return
        
        # Чтобы поставить куки, нужно быть на домене. 
        # Если мы еще не там, делаем пустой переход (быстрый)
        if "wildberries.ru" not in self.driver.current_url:
            try:
                self.driver.get("https://www.wildberries.ru/404")
            except: pass

        cookies = GEO_COOKIES.get(geo)
        if cookies:
            for name, value in cookies.items():
                try:
                    self.driver.add_cookie({"name": name, "value": value, "domain": ".wildberries.ru"})
                except Exception as e:
                    logger.warning(f"Cookie error: {e}")

    def get_position(self, query: str, sku: int, geo: str = "moscow", max_pages: int = 5):
        if not self.driver:
            self._init_driver()

        target_sku = int(sku)
        result = {
            "sku": target_sku, "query": query, "geo": geo,
            "found": False, "page": None, "position": None,
            "total_products": 0, "top_3": []
        }

        # Установка гео (опционально)
        self._set_geo_cookies(geo)

        global_counter = 0

        for page in range(1, max_pages + 1):
            url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}&page={page}&sort=popular"
            logger.info(f"📄 Scraping Page {page}: {url}")

            try:
                self.driver.get(url)
                
                # --- ГЛАВНЫЙ ХАК ---
                # Мы не парсим HTML. Мы забираем готовый JSON из памяти JS.
                # WB хранит состояние каталога в window.__INITIAL_STATE__
                
                # Ждем появления JSON (или любого элемента, означающего загрузку)
                # Обычно достаточно подождать пару секунд или появления #catalog
                try:
                    WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.ID, "catalog"))
                    )
                except:
                    logger.warning("Timeout waiting for catalog, trying to extract data anyway...")

                # Выполняем JS для извлечения данных
                json_data = self.driver.execute_script("return window.__INITIAL_STATE__")
                
                if not json_data:
                    # Фолбэк: если JSON пустой, пробуем парсить старым методом (DOM)
                    # Но обычно JSON есть всегда.
                    logger.warning("⚠️ JS State is empty. WB might have changed structure.")
                    continue

                # Разбор JSON структуры (она может меняться, поэтому try-catch)
                try:
                    # Путь к товарам в стейте WB (может варьироваться)
                    products = json_data.get('catalog', {}).get('data', {}).get('products', [])
                    
                    # Если структура другая (иногда бывает)
                    if not products:
                         # Попробуем поискать в другом месте стейта
                         payload = json_data.get('payload', {})
                         products = payload.get('products', []) or payload.get('data', {}).get('products', [])

                    if not products:
                        logger.warning(f"Page {page}: No products found in JSON.")
                        if page == 1: break 
                        continue

                    # Если это первая страница, запомним Топ-3 для красоты
                    if page == 1:
                        for i in range(min(3, len(products))):
                            p = products[i]
                            result['top_3'].append({
                                "name": p.get('name'),
                                "brand": p.get('brand'),
                                "price": p.get('salePriceU', 0) / 100
                            })

                    # Ищем наш товар
                    for idx, p in enumerate(products):
                        global_counter += 1
                        if p.get('id') == target_sku:
                            logger.info(f"🎯 FOUND! Page {page}, Pos {idx+1}")
                            result['found'] = True
                            result['page'] = page
                            result['position'] = idx + 1
                            result['absolute_pos'] = global_counter
                            result['price'] = p.get('salePriceU', 0) / 100
                            result['rating'] = p.get('reviewRating')
                            
                            # Проверяем рекламу (в JSON она обычно помечена)
                            if 'log' in p or 'promoInfo' in p:
                                result['is_advertising'] = True
                            
                            return result

                except KeyError as e:
                    logger.error(f"Error parsing JSON structure: {e}")

            except Exception as e:
                logger.error(f"Selenium Page Load Error: {e}")
                # Перезапуск драйвера при фатальной ошибке
                self.driver.quit()
                self._init_driver()
                break

        return result

    def close(self):
        if self.driver:
            self.driver.quit()

# Создаем инстанс
selenium_service = OptimizedSeleniumService()