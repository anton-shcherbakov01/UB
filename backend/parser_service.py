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
    """
    Микросервис парсинга Wildberries.
    Версия: Robust Static + Selenium.
    """
    def __init__(self):
        self.headless = os.getenv("HEADLESS", "True").lower() == "true"
        self.proxy_user = os.getenv("PROXY_USER")
        self.proxy_pass = os.getenv("PROXY_PASS")
        self.proxy_host = os.getenv("PROXY_HOST")
        self.proxy_port = os.getenv("PROXY_PORT")

    # --- ЛОГИКА ПОЛУЧЕНИЯ ROOT ID (IMT_ID) ---

    def _get_vol_part(self, sku: int):
        return sku // 100000, sku // 1000

    async def _find_card_json(self, sku: int):
        """
        Ищет card.json перебором корзин. Это самый надежный способ узнать Root ID без браузера.
        """
        vol, part = self._get_vol_part(sku)
        
        # Расчетная корзина (чтобы попробовать первой)
        t = vol
        if 0 <= t <= 143: host_num = "01"
        elif 144 <= t <= 287: host_num = "02"
        elif 288 <= t <= 431: host_num = "03"
        elif 432 <= t <= 719: host_num = "04"
        elif 720 <= t <= 1007: host_num = "05"
        elif 1008 <= t <= 1061: host_num = "06"
        elif 1062 <= t <= 1115: host_num = "07"
        elif 1116 <= t <= 1169: host_num = "08"
        elif 1170 <= t <= 1313: host_num = "09"
        elif 1314 <= t <= 1601: host_num = "10"
        elif 1602 <= t <= 1655: host_num = "11"
        elif 1656 <= t <= 1919: host_num = "12"
        elif 1920 <= t <= 2045: host_num = "13"
        elif 2046 <= t <= 2189: host_num = "14"
        elif 2190 <= t <= 2405: host_num = "15"
        elif 2406 <= t <= 2621: host_num = "16"
        elif 2622 <= t <= 2837: host_num = "17"
        else: host_num = "18"

        hosts = [host_num] + [f"{i:02d}" for i in range(1, 21) if f"{i:02d}" != host_num]
        
        async with aiohttp.ClientSession() as session:
            for host in hosts:
                url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
                try:
                    async with session.get(url, timeout=2) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            data['basket_host'] = host # Сохраняем, где нашли
                            return data
                except:
                    continue
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
        driver.set_page_load_timeout(90)
        return driver

    def _extract_digits(self, text):
        if not text: return 0
        text = str(text).replace('&nbsp;', '').replace(u'\xa0', '')
        digits = re.sub(r'[^\d]', '', text)
        return int(digits) if digits else 0

    # --- ОСНОВНЫЕ МЕТОДЫ ---

    def get_product_data(self, sku: int):
        """Парсинг цен (Selenium + Static Fallback для названий)"""
        logger.info(f"--- АНАЛИЗ ЦЕН SKU: {sku} ---")
        
        # 1. Получаем статику (для названия и бренда) асинхронно
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            static_data = loop.run_until_complete(self._find_card_json(sku))
            loop.close()
        except Exception as e:
            logger.warning(f"Static Fail: {e}")
            static_data = None

        brand = static_data.get('selling', {}).get('brand_name') if static_data else "Unknown"
        name = static_data.get('imt_name') or static_data.get('subj_name') if static_data else f"Товар {sku}"

        for attempt in range(1, 3):
            driver = None
            try:
                driver = self._init_driver()
                driver.get("https://www.wildberries.ru/")
                driver.add_cookie({"name": "x-city-id", "value": "77"})
                
                url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP&dest=-1257786"
                driver.get(url)
                
                time.sleep(3)
                driver.execute_script("window.scrollTo(0, 400);")
                if "Kaspersky" in driver.page_source: driver.quit(); continue

                # Пытаемся вытащить JSON цен из страницы
                try:
                    product_json = driver.execute_script("return window.staticModel ? JSON.stringify(window.staticModel) : null;")
                    if product_json:
                        data = json.loads(product_json)
                        price_data = data.get('price') or (data['products'][0] if 'products' in data else {})
                        
                        wallet = int(price_data.get('clientPriceU', 0) / 100) or int(price_data.get('totalPrice', 0) / 100)
                        if wallet > 0:
                            standard = int(price_data.get('salePriceU', 0) / 100)
                            base = int(price_data.get('priceU', 0) / 100)
                            if brand == "Unknown": brand = data.get('brand', 'Unknown')
                            if name == f"Товар {sku}": name = data.get('name', name)
                            
                            return {
                                "id": sku, "name": name, "brand": brand,
                                "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                                "status": "success"
                            }
                except: pass

                # Если JSON не вышел, ищем в DOM
                WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='price']")))
                
                prices = []
                elements = driver.find_elements(By.CSS_SELECTOR, ".price-block__wallet-price, .price-block__final-price, .price-block__old-price")
                for el in elements:
                    txt = el.get_attribute('textContent')
                    nums = re.findall(r'\d+', txt.replace('\xa0', '').replace(' ', ''))
                    if nums: prices.append(int(nums[0]))
                
                prices = sorted(list(set([p for p in prices if 100 < p < 1000000])))
                if prices:
                    wallet = prices[0]
                    base = prices[-1]
                    standard = prices[1] if len(prices) > 2 else wallet
                    
                    return {
                        "id": sku, "name": name, "brand": brand,
                        "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                        "status": "success"
                    }
                raise Exception("Цены не найдены")

            except Exception as e:
                logger.error(f"Try {attempt}: {e}")
                continue
            finally:
                if driver: driver.quit()
        return {"id": sku, "status": "error", "message": "Failed to parse prices"}

    def get_full_product_info(self, sku: int, limit: int = 50):
        """
        Сбор отзывов.
        1. Ищем card.json (перебором корзин) -> Получаем root ID.
        2. Качаем отзывы через API (feedbacks1/2...).
        """
        logger.info(f"--- ОТЗЫВЫ SKU: {sku} ---")
        
        # 1. Получаем Root ID через перебор корзин (без браузера)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            static_data = loop.run_until_complete(self._find_card_json(sku))
            loop.close()
        except Exception as e:
            logger.error(f"Static loop error: {e}")
            static_data = None

        if not static_data:
            return {"status": "error", "message": "Не удалось найти карточку товара (Static API)"}

        root_id = static_data.get('root') or static_data.get('root_id') or static_data.get('imt_id')
        if not root_id:
            return {"status": "error", "message": "Root ID не найден в карточке"}

        logger.info(f"Root ID: {root_id}")

        # Формируем URL картинки
        vol, part = self._get_vol_part(sku)
        basket_host = static_data.get('basket_host', '01')
        img_url = f"https://basket-{basket_host}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"

        # 2. Качаем отзывы (синхронно, так как мы уже в Celery потоке)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Origin": "https://www.wildberries.ru"
        }
        
        feed_data = None
        # Пробуем разные зеркала API
        for domain in ["feedbacks1", "feedbacks2", "feedbacks-api"]:
            try:
                url = f"https://{domain}.wb.ru/feedbacks/v1/{root_id}"
                if domain == "feedbacks-api":
                     url = f"https://{domain}.wildberries.ru/api/v1/feedbacks?isAnswered=false&take={limit}&skip=0&nmId={sku}&imtId={root_id}"
                
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    feed_data = resp.json()
                    logger.info(f"Отзывы получены с {domain}")
                    break
            except: pass
        
        if not feed_data:
            return {"status": "error", "message": "API отзывов недоступен"}

        # Обработка данных отзывов
        reviews_data = []
        raw_list = feed_data.get('feedbacks', []) or feed_data.get('data', {}).get('feedbacks', [])
        
        rating = float(feed_data.get('valuation', 0))
        
        for f in raw_list:
            txt = f.get('text', '').strip()
            if txt:
                reviews_data.append({
                    "text": txt,
                    "rating": f.get('productValuation', 5)
                })
            if len(reviews_data) >= limit: break

        return {
            "sku": sku,
            "image": img_url,
            "rating": rating,
            "reviews": reviews_data,
            "reviews_count": len(reviews_data),
            "status": "success"
        }

parser_service = SeleniumWBParser()