import os
import time
import random
import logging
import json
import re
import sys
import requests
import asyncio
import aiohttp
import zipfile
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
    def __init__(self):
        self.headless = os.getenv("HEADLESS", "True").lower() == "true"
        self.proxy_user = os.getenv("PROXY_USER")
        self.proxy_pass = os.getenv("PROXY_PASS")
        self.proxy_host = os.getenv("PROXY_HOST")
        self.proxy_port = os.getenv("PROXY_PORT")

    # --- СТАТИКА (BASKETS) ---
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
        """Скачивает card.json напрямую. Самый надежный источник имени и бренда."""
        try:
            basket = self._get_basket_number(sku)
            vol = sku // 100000
            part = sku // 1000
            url = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
            
            # Таймаут 5 сек, без прокси (CDN работает везде)
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # Вычисляем ссылку на фото
                data['image_url'] = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"
                return data
        except Exception as e:
            logger.warning(f"Static API Warning: {e}")
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
            logger.error(f"Driver Init Error: {e}")
            raise e
        driver.set_page_load_timeout(120)
        return driver

    def _extract_digits(self, text):
        if not text: return 0
        text = str(text).replace('&nbsp;', '').replace(u'\xa0', '')
        digits = re.sub(r'[^\d]', '', text)
        return int(digits) if digits else 0

    def get_product_data(self, sku: int):
        """Парсинг цен (Selenium) + Название (Статика)"""
        logger.info(f"--- АНАЛИЗ ЦЕН SKU: {sku} ---")
        
        # 1. Получаем инфо из статики (быстро и надежно)
        static_data = self._get_static_card_data(sku)
        brand = static_data.get('selling', {}).get('brand_name') if static_data else "Unknown"
        name = static_data.get('imt_name') or static_data.get('subj_name') if static_data else f"Товар {sku}"

        for attempt in range(1, 3):
            driver = None
            try:
                driver = self._init_driver()
                
                # Заходим на главную для куки (Москва)
                driver.get("https://www.wildberries.ru/")
                driver.add_cookie({"name": "x-city-id", "value": "77"}) 
                
                # Идем в карточку
                url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP&dest=-1257786"
                logger.info(f"Загрузка (Попытка {attempt}): {url}")
                driver.get(url)
                
                time.sleep(3)
                if "Kaspersky" in driver.page_source: driver.quit(); continue

                # ЭТАП 1: Ищем JSON в JS
                try:
                    product_json = driver.execute_script("return window.staticModel ? JSON.stringify(window.staticModel) : null;")
                    if product_json:
                        data = json.loads(product_json)
                        price_data = data.get('price') or (data['products'][0] if 'products' in data else {})
                        
                        wallet = int(price_data.get('clientPriceU', 0) / 100) or int(price_data.get('totalPrice', 0) / 100)
                        if wallet > 0:
                            standard = int(price_data.get('salePriceU', 0) / 100)
                            base = int(price_data.get('priceU', 0) / 100)
                            
                            logger.info(f"JSON Price: {wallet}₽")
                            return {
                                "id": sku, "name": name, "brand": brand,
                                "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                                "status": "success"
                            }
                except: pass

                # ЭТАП 2: DOM Парсинг
                driver.execute_script("window.scrollTo(0, 400);")
                try:
                    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='price']")))
                except: pass

                prices = []
                # Ищем все элементы с ценой
                elements = driver.find_elements(By.CSS_SELECTOR, ".price-block__wallet-price, .price-block__final-price, .price-block__old-price, [class*='Price']")
                for el in elements:
                    txt = el.get_attribute('textContent')
                    nums = re.findall(r'\d+', txt.replace('\xa0', '').replace(' ', ''))
                    if nums: prices.append(int(nums[0]))
                
                # Фильтруем адекватные цены
                prices = sorted(list(set([p for p in prices if 100 < p < 1000000])))
                
                if prices:
                    logger.info(f"DOM Prices: {prices}")
                    wallet = prices[0]
                    base = prices[-1]
                    standard = prices[1] if len(prices) > 2 else wallet
                    
                    return {
                        "id": sku, "name": name, "brand": brand,
                        "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                        "status": "success"
                    }
                
                logger.warning("Цены не найдены в DOM")

            except Exception as e:
                logger.error(f"Try {attempt} Error: {e}")
                continue
            finally:
                if driver: driver.quit()
        return {"id": sku, "status": "error", "message": "Failed to parse prices"}

    def get_full_product_info(self, sku: int, limit: int = 50):
        """
        Сбор отзывов: Static JSON -> API Request.
        """
        logger.info(f"--- АНАЛИЗ ОТЗЫВОВ SKU: {sku} ---")
        
        try:
            # 1. Получаем root ID из статики
            static_data = self._get_static_card_data(sku)
            if not static_data:
                return {"status": "error", "message": "Не удалось загрузить карточку (Static)"}

            root_id = static_data.get('root') or static_data.get('root_id') or static_data.get('imt_id')
            if not root_id:
                return {"status": "error", "message": "Root ID не найден"}

            logger.info(f"Root ID: {root_id}")

            # 2. Качаем отзывы через requests
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Origin": "https://www.wildberries.ru",
                "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            }
            
            feed_data = None
            for domain in ["feedbacks1", "feedbacks2"]:
                try:
                    url = f"https://{domain}.wb.ru/feedbacks/v1/{root_id}"
                    resp = requests.get(url, headers=headers, timeout=10)
                    if resp.status_code == 200:
                        feed_data = resp.json()
                        break
                except: pass
            
            if not feed_data:
                return {"status": "error", "message": "API отзывов недоступен"}

            rating = float(feed_data.get('valuation', 0))
            raw_feedbacks = feed_data.get('feedbacks', [])
            
            reviews_data = []
            for f in raw_feedbacks:
                txt = f.get('text', '').strip()
                if txt:
                    reviews_data.append({
                        "text": txt,
                        "rating": f.get('productValuation', 5)
                    })
                if len(reviews_data) >= limit: break

            logger.info(f"Отзывы: {len(reviews_data)}")
            
            return {
                "sku": sku,
                "image": static_data.get('image_url'),
                "rating": rating,
                "reviews": reviews_data,
                "reviews_count": len(reviews_data),
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Reviews Error: {e}")
            return {"status": "error", "message": str(e)}

parser_service = SeleniumWBParser()