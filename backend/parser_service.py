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
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("WB-Parser")
logging.getLogger('WDM').setLevel(logging.ERROR)

class SeleniumWBParser:
    def __init__(self):
        self.headless = os.getenv("HEADLESS", "True").lower() == "true"
        self.proxy_user = os.getenv("PROXY_USER")
        self.proxy_pass = os.getenv("PROXY_PASS")
        self.proxy_host = os.getenv("PROXY_HOST")
        self.proxy_port = os.getenv("PROXY_PORT")

    # --- ЛОГИКА ПОИСКА КОРЗИН (BRUTE FORCE) ---
    async def _find_working_basket(self, sku: int) -> dict:
        """
        Перебирает сервера корзин, чтобы найти рабочий card.json.
        """
        vol = sku // 100000
        part = sku // 1000
        
        # Список хостов для проверки (приоритетные + остальные)
        # Стандартный расчет
        t = vol
        if 0 <= t <= 143: default = "01"
        elif 144 <= t <= 287: default = "02"
        elif 288 <= t <= 431: default = "03"
        elif 432 <= t <= 719: default = "04"
        elif 720 <= t <= 1007: default = "05"
        elif 1008 <= t <= 1061: default = "06"
        elif 1062 <= t <= 1115: default = "07"
        elif 1116 <= t <= 1169: default = "08"
        elif 1170 <= t <= 1313: default = "09"
        elif 1314 <= t <= 1601: default = "10"
        elif 1602 <= t <= 1655: default = "11"
        elif 1656 <= t <= 1919: default = "12"
        elif 1920 <= t <= 2045: default = "13"
        elif 2046 <= t <= 2189: default = "14"
        elif 2190 <= t <= 2405: default = "15"
        elif 2406 <= t <= 2621: default = "16"
        elif 2622 <= t <= 2837: default = "17"
        else: default = "18"

        hosts = [default] + [f"{i:02d}" for i in range(1, 21) if f"{i:02d}" != default]

        async with aiohttp.ClientSession() as session:
            for host in hosts:
                url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
                try:
                    async with session.get(url, timeout=2) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            data['image_url'] = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"
                            return data
                except:
                    continue
        return None

    # --- SELENIUM ---
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
        except:
            raise Exception("Driver init failed")
        driver.set_page_load_timeout(120)
        return driver

    def _extract_price(self, driver, selector):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                txt = driver.execute_script("return arguments[0].textContent;", elements[0])
                if not txt: txt = driver.execute_script("return arguments[0].innerText;", elements[0])
                digits = re.sub(r'[^\d]', '', txt)
                return int(digits) if digits else 0
        except: return 0
        return 0

    def get_product_data(self, sku: int):
        logger.info(f"--- АНАЛИЗ ЦЕН SKU: {sku} ---")
        
        # 1. СТАТИКА (Быстрое имя и бренд)
        static_info = {"name": f"Товар {sku}", "brand": "Unknown"}
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(self._find_working_basket(sku))
            if data:
                static_info["name"] = data.get('imt_name') or data.get('subj_name')
                static_info["brand"] = data.get('selling', {}).get('brand_name')
            loop.close()
        except: pass

        # 2. SELENIUM (Цены)
        for attempt in range(1, 3):
            driver = None
            try:
                driver = self._init_driver()
                driver.get("https://www.wildberries.ru/")
                driver.add_cookie({"name": "x-city-id", "value": "77"}) 
                driver.get(f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP&dest=-1257786")
                
                time.sleep(3)
                if "Kaspersky" in driver.page_source: driver.quit(); continue

                # JSON injection check
                try:
                    p_json = driver.execute_script("return window.staticModel ? JSON.stringify(window.staticModel) : null;")
                    if p_json:
                        d = json.loads(p_json)
                        price = d.get('price') or (d['products'][0] if 'products' in d else {})
                        wallet = int(price.get('clientPriceU', 0)/100) or int(price.get('totalPrice', 0)/100)
                        if wallet > 0:
                            return {
                                "id": sku, 
                                "name": static_info["name"], "brand": static_info["brand"],
                                "prices": {"wallet_purple": wallet, "standard_black": int(price.get('salePriceU',0)/100), "base_crossed": int(price.get('priceU',0)/100)},
                                "status": "success"
                            }
                except: pass

                # DOM check
                start = time.time()
                while time.time() - start < 60:
                    if driver.find_elements(By.CSS_SELECTOR, "[class*='price']"): break
                    time.sleep(1)

                wallet = self._extract_price(driver, "[class*='priceBlockWalletPrice'], .price-block__wallet-price")
                standard = self._extract_price(driver, "[class*='priceBlockFinalPrice'], .price-block__final-price")
                base = self._extract_price(driver, "[class*='priceBlockOldPrice'], .price-block__old-price")

                if wallet == 0 and standard > 0: wallet = standard
                if wallet == 0: raise Exception("Price not found")

                return {
                    "id": sku, 
                    "name": static_info["name"], "brand": static_info["brand"],
                    "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                    "status": "success"
                }

            except Exception as e:
                logger.error(f"Try {attempt} error: {e}")
                continue
            finally:
                if driver: driver.quit()
        return {"id": sku, "status": "error", "message": "Failed to parse prices"}

    def get_full_product_info(self, sku: int, limit: int = 50):
        """
        Сбор отзывов: Static JSON (Brute Force) -> API
        """
        logger.info(f"--- АНАЛИЗ ОТЗЫВОВ SKU: {sku} ---")
        try:
            # 1. Ищем корзину перебором
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            static_data = loop.run_until_complete(self._find_working_basket(sku))
            loop.close()

            if not static_data:
                raise Exception("Не удалось найти card.json (товар удален или сбой WB)")

            root_id = static_data.get('root') or static_data.get('root_id') or static_data.get('imt_id')
            if not root_id: raise Exception("Root ID не найден")

            # 2. Качаем отзывы
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Origin": "https://www.wildberries.ru",
                "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            }
            
            feed_data = None
            for domain in ["feedbacks1", "feedbacks2"]:
                try:
                    resp = requests.get(f"https://{domain}.wb.ru/feedbacks/v1/{root_id}", headers=headers, timeout=10)
                    if resp.status_code == 200:
                        feed_data = resp.json()
                        break
                except: pass
            
            if not feed_data: raise Exception("API отзывов не отвечает")

            rating = float(feed_data.get('valuation', 0))
            reviews = []
            for f in feed_data.get('feedbacks', [])[:limit]:
                if f.get('text'):
                    reviews.append({"text": f['text'], "rating": f.get('productValuation', 5)})

            return {
                "sku": sku, "image": static_data['image_url'], "rating": rating,
                "reviews": reviews, "reviews_count": len(reviews), "status": "success"
            }

        except Exception as e:
            logger.error(f"Reviews Error: {e}")
            return {"status": "error", "message": str(e)}

parser_service = SeleniumWBParser()