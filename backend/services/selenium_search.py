import logging
import asyncio
import aiohttp
import json
import random
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("UniversalParser")

# Настройки прокси (если есть в .env)
PROXY_URL = os.getenv("PROXY_URL")  # format: http://user:pass@host:port

class UniversalSeleniumService:
    def __init__(self):
        self.driver = None
        # User Agents для ротации
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        ]

    # --- ЧАСТЬ 1: ЛЕГКИЕ HTTP ЗАПРОСЫ (БЫСТРО) ---

    def _calc_basket(self, sku: int) -> str:
        """Вычисляет хост корзины WB (basket-XX)"""
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
        if 2406 <= vol <= 2621: return "16"
        if 2622 <= vol <= 2837: return "17"
        return "18" # Fallback

    async def _find_card_json(self, sku: int):
        """Пытается найти JSON карточки напрямую (без браузера)"""
        vol = sku // 100000
        part = sku // 1000
        basket = self._calc_basket(sku)
        
        # Генерируем возможные варианты (иногда basket меняется)
        hosts = [basket, "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14"]
        # Убираем дубли, сохраняя порядок
        hosts = list(dict.fromkeys(hosts))

        async with aiohttp.ClientSession() as session:
            for host in hosts:
                url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
                try:
                    async with session.get(url, timeout=1.5) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            # Формируем ссылку на фото сразу
                            data['image_url'] = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"
                            return data
                except:
                    continue
        return None

    # --- ЧАСТЬ 2: МЕТОДЫ ДЛЯ СКАНЕРА И МОНИТОРИНГА ---

    async def get_product_details(self, sku: int):
        """
        Главный метод: сначала пробует JSON, если там нет цены - запускает Selenium.
        """
        sku = int(sku)
        logger.info(f"⚡ Scanning SKU: {sku}")
        
        # 1. Быстрый путь (HTTP)
        try:
            card = await self._find_card_json(sku)
            if card:
                # Извлекаем базовые данные
                name = card.get('imt_name') or card.get('subj_name', 'Unknown')
                brand = card.get('selling', {}).get('brand_name', '')
                image = card.get('image_url')
                
                # Пытаемся найти цену в JSON (она бывает в sizes)
                price = 0
                try:
                    # Ищем минимальную цену среди размеров
                    sizes = card.get('sizes', [])
                    for s in sizes:
                        if s.get('price', {}).get('total'): # Новый формат
                            p = s['price']['total'] / 100
                            if price == 0 or p < price: price = p
                        elif s.get('priceU'): # Старый формат
                            p = s['priceU'] / 100
                            if price == 0 or p < price: price = p
                except: pass

                # Если цена нашлась в JSON - мы победили (0.1 сек)
                if price > 0:
                    logger.info(f"✅ Found via JSON: {price}₽")
                    return {
                        "valid": True, "sku": sku, "name": name, 
                        "brand": brand, "price": int(price), 
                        "image": image, "rating": 0, "review_count": 0
                    }
        except Exception as e:
            logger.warning(f"JSON fetch failed: {e}")

        # 2. Медленный путь (Selenium), если цены не было в JSON
        logger.info("⚠️ Price not in JSON, starting Selenium...")
        return await self._selenium_get_details(sku)

    # --- ЧАСТЬ 3: SELENIUM FALLBACK (ДЛЯ СЛОЖНЫХ СЛУЧАЕВ И БИДДЕРА) ---

    def _init_driver(self):
        """Инициализация Chrome (так как Docker настроен на Chrome)"""
        if self.driver: return

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Ротация UA
        chrome_options.add_argument(f"user-agent={random.choice(self.user_agents)}")

        try:
            self.driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=chrome_options
            )
            self.driver.set_page_load_timeout(20)
            logger.info("🚀 Selenium Driver initialized")
        except Exception as e:
            logger.error(f"Driver Init Failed: {e}")
            raise e

    async def _selenium_get_details(self, sku: int):
        if not self.driver: self._init_driver()
        
        url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
        result = {"valid": False, "sku": sku, "price": 0}

        try:
            # Синхронный вызов Selenium внутри async функции
            # (в идеале запускать через executor, но тут мы уже внутри threadpool роутера)
            self.driver.get(url)
            
            # Ждем цену
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".price-block__wallet-price, .price-block__final-price"))
                )
            except: 
                logger.warning("Timeout waiting for price element")

            # Парсим JS состояние (самый надежный способ в Selenium)
            try:
                json_data = self.driver.execute_script("return window.staticModel ? window.staticModel : null;")
                if not json_data:
                     # Попытка 2: SSR State
                     json_data = self.driver.execute_script("return window.__INITIAL_STATE__ && window.__INITIAL_STATE__.product ? window.__INITIAL_STATE__.product.product : null;")

                if json_data:
                    result['valid'] = True
                    result['name'] = json_data.get('imt_name') or json_data.get('name')
                    result['brand'] = json_data.get('selling', {}).get('brand_name') or json_data.get('brandName')
                    
                    # Цена
                    price_data = json_data.get('price') or {}
                    # Цена кошелька или обычная
                    price = price_data.get('clientPriceU') or price_data.get('salePriceU') or json_data.get('salePriceU')
                    if price:
                        result['price'] = int(price / 100)
                    
                    return result
            except Exception as e:
                logger.error(f"JS Parse error: {e}")

            # Фолбэк на DOM (если JS не сработал)
            try:
                price_el = self.driver.find_element(By.CSS_SELECTOR, ".price-block__wallet-price, .price-block__final-price")
                price_text = price_el.text.replace('₽', '').replace(' ', '').replace('\xa0', '')
                result['price'] = int(price_text)
                result['name'] = self.driver.find_element(By.CSS_SELECTOR, "h1").text
                result['valid'] = True
            except: pass

        except Exception as e:
            logger.error(f"Selenium error: {e}")
            self.driver.quit()
            self._init_driver() # Рестарт драйвера на случай зависания

        return result

    # --- ЧАСТЬ 4: БИДДЕР (АУКЦИОН) ---
    def get_search_auction(self, query: str):
        """Парсит рекламную выдачу"""
        if not self.driver: self._init_driver()
        
        url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}&sort=popular"
        ads = []
        
        try:
            self.driver.get(url)
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, "catalog")))
            
            # Быстрый захват JSON каталога
            js_data = self.driver.execute_script("return window.__INITIAL_STATE__")
            
            products = []
            if js_data:
                products = (js_data.get('catalog', {}).get('data', {}).get('products', []) or 
                            js_data.get('payload', {}).get('products', []))
            
            for idx, p in enumerate(products):
                if 'log' in p: # Это реклама
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

    # --- ЧАСТЬ 5: SEO ПОЗИЦИИ ---
    def get_seo_position(self, query: str, sku: int, geo: str = "moscow"):
        """Поиск позиции товара"""
        if not self.driver: self._init_driver()
        sku = int(sku)
        
        # Установка куки региона
        try:
            if "wildberries.ru" not in self.driver.current_url:
                self.driver.get("https://www.wildberries.ru/404")
            
            geo_ids = {
                "moscow": "-1257786", "spb": "-1257786", "ekb": "-1113276",
                "krasnodar": "-1192533", "kazan": "-2133464"
            }
            dst = geo_ids.get(geo, "-1257786")
            self.driver.add_cookie({"name": "x-geo-id", "value": geo, "domain": ".wildberries.ru"})
            self.driver.add_cookie({"name": "dst", "value": dst, "domain": ".wildberries.ru"})
            self.driver.refresh()
        except: pass

        result = {"found": False, "page": None, "position": None, "absolute_pos": None}
        global_counter = 0

        for page in range(1, 6): # До 5 страниц
            url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}&page={page}&sort=popular"
            try:
                self.driver.get(url)
                WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.ID, "catalog")))
                
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
                            "absolute_pos": global_counter, 
                            "is_advertising": 'log' in p
                        })
                        return result
            except: break
        
        return result

    def close(self):
        if self.driver: self.driver.quit()

selenium_service = UniversalSeleniumService()