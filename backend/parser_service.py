import os
import time
import random
import logging
import json
import re
import sys
import requests
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | [%(name)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("WB-Parser")
logging.getLogger('WDM').setLevel(logging.ERROR)

class SeleniumWBParser:
    """
    Микросервис парсинга Wildberries v9.0 (Ultra Stable).
    Приоритет на API методы. Selenium используется как крайняя мера.
    """
    def __init__(self):
        self.headless = os.getenv("HEADLESS", "True").lower() == "true"
        self.proxy_user = os.getenv("PROXY_USER")
        self.proxy_pass = os.getenv("PROXY_PASS")
        self.proxy_host = os.getenv("PROXY_HOST")
        self.proxy_port = os.getenv("PROXY_PORT")

    # --- BASKET LOGIC ---
    def _get_basket_number(self, sku: int) -> str:
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
        return "18"

    def _get_static_card_data(self, sku: int):
        """1. Самый быстрый способ: Static JSON"""
        try:
            basket = self._get_basket_number(sku)
            vol = sku // 100000
            part = sku // 1000
            url = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except: pass
        return None

    def _get_api_card_data(self, sku: int):
        """2. Средний способ: Mobile API (без браузера)"""
        try:
            # Эмулируем мобильное приложение/сайт без браузера
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Origin": "https://www.wildberries.ru",
                "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            }
            # Московский регион для точности
            url = f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&nm={sku}"
            resp = requests.get(url, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                products = data.get('data', {}).get('products', [])
                if products:
                    return products[0]
        except Exception as e:
            logger.warning(f"API Fallback Error: {e}")
        return None

    # --- SELENIUM SETUP ---
    def _create_proxy_auth_extension(self, user, pw, host, port):
        folder_path = "proxy_ext"
        if not os.path.exists(folder_path): os.makedirs(folder_path)
        manifest_json = json.dumps({"version": "1.0.0", "manifest_version": 2, "name": "Edge Proxy", "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"], "background": {"scripts": ["background.js"]}})
        session_id = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=10))
        auth_user = f"{user}-session-{session_id};country-ru"
        background_js = """
        var config = { mode: "fixed_servers", rules: { singleProxy: { scheme: "http", host: "%s", port: parseInt(%s) }, bypassList: ["localhost"] } };
        chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
        chrome.webRequest.onAuthRequired.addListener(function(details) { return { authCredentials: { username: "%s", password: "%s" } }; }, {urls: ["<all_urls>"]}, ['blocking']);
        """ % (host, port, auth_user, pw)
        extension_path = os.path.join(folder_path, "proxy_auth_plugin.zip")
        with zipfile.ZipFile(extension_path, 'w') as zp:
            zp.writestr("manifest.json", manifest_json)
            zp.writestr("background.js", background_js)
        return extension_path

    def _init_driver(self):
        edge_options = EdgeOptions()
        if self.headless: edge_options.add_argument("--headless=new")
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-dev-shm-usage")
        edge_options.add_argument("--disable-gpu")
        edge_options.add_argument("--disable-blink-features=AutomationControlled")
        plugin_path = self._create_proxy_auth_extension(self.proxy_user, self.proxy_pass, self.proxy_host, self.proxy_port)
        edge_options.add_extension(plugin_path)
        edge_options.add_argument("--window-size=1920,1080")
        edge_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        try:
            driver_bin = '/usr/local/bin/msedgedriver'
            service = EdgeService(executable_path=driver_bin)
            driver = webdriver.Edge(service=service, options=edge_options)
        except Exception as e:
            logger.error(f"Driver Error: {e}")
            raise e
        driver.set_page_load_timeout(120)
        return driver

    def _extract_digits(self, text):
        if not text: return 0
        text = str(text).replace('&nbsp;', '').replace(u'\xa0', '')
        digits = re.sub(r'[^\d]', '', text)
        return int(digits) if digits else 0

    def get_product_data(self, sku: int):
        logger.info(f"--- PRICES SKU: {sku} ---")
        
        # 1. Сначала пробуем API (это быстрее и надежнее для цен)
        api_data = self._get_api_card_data(sku)
        if api_data:
            try:
                # В API цены в копейках
                wallet = self._extract_digits(api_data.get('clientPriceU', 0)) // 100
                standard = self._extract_digits(api_data.get('salePriceU', 0)) // 100
                base = self._extract_digits(api_data.get('priceU', 0)) // 100
                
                if wallet == 0: wallet = standard
                
                brand = api_data.get('brand', 'Unknown')
                name = api_data.get('name', f"Товар {sku}")
                
                logger.info(f"API Success: {wallet}₽")
                return {
                    "id": sku, "name": name, "brand": brand,
                    "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                    "status": "success"
                }
            except: pass # Если API вернул битые данные, идем в Selenium
        
        # 2. Если API не сработал - Selenium
        for attempt in range(1, 3):
            driver = None
            try:
                driver = self._init_driver()
                driver.get("https://www.wildberries.ru/")
                driver.add_cookie({"name": "x-city-id", "value": "77"})
                driver.get(f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP&dest=-1257786")
                
                time.sleep(3)
                if "Kaspersky" in driver.page_source: driver.quit(); continue

                # Ищем JSON внутри страницы
                try:
                    product_json = driver.execute_script("return window.staticModel ? JSON.stringify(window.staticModel) : null;")
                    if product_json:
                        data = json.loads(product_json)
                        price_data = data.get('price') or (data['products'][0] if 'products' in data else {})
                        
                        wallet = int(price_data.get('clientPriceU', 0) / 100) or int(price_data.get('totalPrice', 0) / 100)
                        if wallet > 0:
                            brand = data.get('brand', 'Unknown')
                            name = data.get('name', f"Товар {sku}")
                            return {
                                "id": sku, "name": name, "brand": brand,
                                "prices": {"wallet_purple": wallet, "standard_black": wallet, "base_crossed": 0},
                                "status": "success"
                            }
                except: pass

                # DOM Parsing
                driver.execute_script("window.scrollTo(0, 400);")
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='price']")))
                
                prices = []
                elements = driver.find_elements(By.CSS_SELECTOR, ".price-block__wallet-price, .price-block__final-price, .price-block__old-price")
                for el in elements:
                    txt = el.get_attribute('textContent')
                    nums = re.findall(r'\d+', txt.replace('\xa0', '').replace(' ', ''))
                    if nums: prices.append(int(nums[0]))
                
                prices = sorted(list(set([p for p in prices if 100 < p < 1000000])))
                if prices:
                    return {
                        "id": sku, "name": f"Товар {sku}", "brand": "Unknown",
                        "prices": {"wallet_purple": prices[0], "standard_black": prices[1] if len(prices)>2 else prices[0], "base_crossed": prices[-1]},
                        "status": "success"
                    }
                raise Exception("Цены не найдены")

            except Exception as e:
                logger.error(f"Err: {e}")
                continue
            finally:
                if driver: driver.quit()
        return {"id": sku, "status": "error", "message": "Failed"}

    def get_full_product_info(self, sku: int, limit: int = 50):
        """
        Парсинг отзывов. 
        1. Static JSON (CDN)
        2. Mobile API (Requests)
        3. Browser (Last Resort)
        """
        logger.info(f"--- REVIEWS SKU: {sku} ---")
        root_id = None
        img_url = ""
        
        # 1. Пробуем статику
        static_data = self._get_static_card_data(sku)
        if static_data:
            root_id = static_data.get('root') or static_data.get('root_id')
            logger.info(f"Got root from Static: {root_id}")

        # 2. Пробуем API карточки (если статика пустая)
        if not root_id:
            api_data = self._get_api_card_data(sku)
            if api_data:
                root_id = api_data.get('root')
                logger.info(f"Got root from API: {root_id}")

        # Если Root ID так и не найден, кидаем ошибку (Selenium тут не поможет, если API не отдает)
        if not root_id:
            logger.error("Не удалось найти Root ID ни в статике, ни в API.")
            return {"status": "error", "message": "Товар не найден или удален"}

        # 3. Качаем отзывы через API
        try:
            feed_url = f"https://feedbacks1.wb.ru/feedbacks/v1/{root_id}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Origin": "https://www.wildberries.ru",
                "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            }
            
            resp = requests.get(feed_url, headers=headers, timeout=10)
            if resp.status_code != 200:
                # Пробуем зеркало
                feed_url = f"https://feedbacks2.wb.ru/feedbacks/v1/{root_id}"
                resp = requests.get(feed_url, headers=headers, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                rating = float(data.get('valuation', 0))
                reviews = []
                for f in data.get('feedbacks', [])[:limit]:
                    if f.get('text'):
                        reviews.append({"text": f['text'], "rating": f.get('productValuation', 5)})
                
                img_url = f"https://basket-{self._get_basket_number(sku)}.wbbasket.ru/vol{sku//100000}/part{sku//1000}/{sku}/images/c246x328/1.webp"
                
                logger.info(f"Отзывы получены: {len(reviews)}")
                return {
                    "sku": sku, "image": img_url, "rating": rating, 
                    "reviews": reviews, "reviews_count": len(reviews), 
                    "status": "success"
                }
            else:
                return {"status": "error", "message": f"API отзывов вернул {resp.status_code}"}
        
        except Exception as e:
            return {"status": "error", "message": str(e)}

parser_service = SeleniumWBParser()