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
import zipfile  # БЫЛ ПРОПУЩЕН, ДОБАВЛЕН
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By

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

    def _calc_basket_static(self, sku: int) -> str:
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

    async def _find_card_json(self, sku: int):
        vol = sku // 100000
        part = sku // 1000
        calc_host = self._calc_basket_static(sku)
        # Приоритет: расчетный, затем новые, затем старые
        hosts_priority = [calc_host] + [f"{i:02d}" for i in range(18, 26)] + [f"{i:02d}" for i in range(1, 18)]
        hosts = []
        [hosts.append(h) for h in hosts_priority if h not in hosts]

        async with aiohttp.ClientSession() as session:
            for host in hosts:
                url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
                try:
                    async with session.get(url, timeout=1.5) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            data['image_url'] = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"
                            return data
                except:
                    continue
        return None

    def _create_proxy_auth_extension(self, user, pw, host, port):
        folder_path = "proxy_ext"
        if not os.path.exists(folder_path): os.makedirs(folder_path)
        
        manifest_json = json.dumps({
            "version": "1.0.0", 
            "manifest_version": 2, 
            "name": "Edge Proxy", 
            "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"], 
            "background": {"scripts": ["background.js"]}
        })
        
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
        edge_options.add_argument("--window-size=1920,1080")
        edge_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        if self.proxy_user and self.proxy_host:
            plugin_path = self._create_proxy_auth_extension(self.proxy_user, self.proxy_pass, self.proxy_host, self.proxy_port)
            edge_options.add_extension(plugin_path)
        
        try:
            driver_bin = '/usr/local/bin/msedgedriver'
            service = EdgeService(executable_path=driver_bin)
            driver = webdriver.Edge(service=service, options=edge_options)
        except Exception as e:
            logger.error(f"Driver Init Error: {e}")
            raise e
        driver.set_page_load_timeout(120)
        return driver

    def _extract_price(self, driver, selector):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                text = el.get_attribute("innerText") or el.text
                digits = re.sub(r'[^\d]', '', text)
                if digits: return int(digits)
        except: pass
        return 0

    def get_product_data(self, sku: int):
        logger.info(f"--- АНАЛИЗ ЦЕН SKU: {sku} ---")
        
        static_info = {"name": f"Товар {sku}", "brand": "Unknown", "image": ""}
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(self._find_card_json(sku))
            if data:
                static_info["name"] = data.get('imt_name') or data.get('subj_name')
                static_info["brand"] = data.get('selling', {}).get('brand_name')
                static_info["image"] = data.get('image_url')
                logger.info(f"Статика получена: {static_info['brand']} / {static_info['name']}")
            loop.close()
        except Exception as e:
            logger.warning(f"Static fail: {e}")

        # Если нашли статику и цены (иногда они есть в card.json, но не всегда актуальны для юзера), можно вернуть сразу
        # Но ТЗ требует Selenium для цен. Идем в Selenium.

        for attempt in range(1, 3):
            driver = None
            try:
                driver = self._init_driver()
                driver.get(f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP")
                time.sleep(3)
                driver.execute_script("window.scrollTo(0, 400);")
                
                # Проверка JSON на странице
                try:
                    p_json = driver.execute_script("return window.staticModel ? JSON.stringify(window.staticModel) : null;")
                    if p_json:
                        d = json.loads(p_json)
                        price = d.get('price') or (d['products'][0] if 'products' in d else {})
                        wallet = int(price.get('clientPriceU', 0)/100) or int(price.get('totalPrice', 0)/100)
                        
                        if wallet > 0:
                            return {
                                "id": sku, 
                                "name": static_info["name"], 
                                "brand": static_info["brand"],
                                "prices": {"wallet_purple": wallet, "standard_black": int(price.get('salePriceU',0)/100), "base_crossed": int(price.get('priceU',0)/100)},
                                "status": "success"
                            }
                except: pass

                # DOM
                start = time.time()
                while time.time() - start < 15: # Уменьшил таймаут для скорости
                    if driver.find_elements(By.CSS_SELECTOR, "[class*='price']"): break
                    time.sleep(1)

                wallet = self._extract_price(driver, ".price-block__wallet-price")
                standard = self._extract_price(driver, ".price-block__final-price")
                base = self._extract_price(driver, ".price-block__old-price")
                
                if wallet == 0 and standard > 0: wallet = standard

                if wallet > 0:
                    return {
                        "id": sku, 
                        "name": static_info["name"],
                        "brand": static_info["brand"],
                        "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                        "status": "success"
                    }

            except Exception as e:
                logger.error(f"Price Err {attempt}: {e}")
            finally:
                if driver: driver.quit()
        
        return {"id": sku, "status": "error", "message": "Failed to parse prices"}

    def get_full_product_info(self, sku: int, limit: int = 50):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            static_data = loop.run_until_complete(self._find_card_json(sku))
            loop.close()

            if not static_data: return {"status": "error", "message": "Товар не найден"}

            root_id = static_data.get('root') or static_data.get('root_id') or static_data.get('imt_id')
            if not root_id: return {"status": "error", "message": "Root ID не найден"}

            feed_data = None
            headers = {"User-Agent": "Mozilla/5.0"}
            
            # API Feedbacks
            try:
                url = f"https://feedbacks1.wb.ru/feedbacks/v1/{root_id}"
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code == 200: feed_data = r.json()
            except: pass
            
            if not feed_data: return {"status": "error", "message": "API отзывов недоступен"}
            
            reviews = []
            raw_list = feed_data.get('feedbacks', [])
            for f in raw_list:
                if f.get('text'): reviews.append({"text": f['text'], "rating": f.get('productValuation', 5)})
                if len(reviews) >= limit: break
            
            return {
                "sku": sku, "image": static_data.get('image_url'),
                "rating": float(feed_data.get('valuation', 0)),
                "reviews": reviews, "reviews_count": len(reviews),
                "status": "success"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

parser_service = SeleniumWBParser()