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

    def _extract_price(self, driver, selector):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                txt = driver.execute_script("return arguments[0].textContent;", elements[0])
                if not txt: txt = driver.execute_script("return arguments[0].innerText;", elements[0])
                digits = re.sub(r'[^\d]', '', txt)
                val = int(digits) if digits else 0
                if val > 0: logger.info(f"Price found ({selector}): {val}")
                return val
        except: return 0
        return 0

    # --- ЦЕНЫ (SELENIUM ONLY) ---
    def get_product_data(self, sku: int):
        logger.info(f"--- PRICES SKU: {sku} ---")
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
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

                start = time.time()
                while time.time() - start < 45:
                    if driver.find_elements(By.CSS_SELECTOR, "[class*='price']"): break
                    time.sleep(1)

                wallet = self._extract_price(driver, ".price-block__wallet-price, [class*='priceBlockWalletPrice']")
                standard = self._extract_price(driver, ".price-block__final-price, [class*='priceBlockFinalPrice']")
                base = self._extract_price(driver, ".price-block__old-price, [class*='priceBlockOldPrice']")

                if not standard: 
                    # JS FALLBACK (OLD WORKING)
                    js_prices = driver.execute_script("let r=[]; document.querySelectorAll('[class*=\"price\"]').forEach(e=>{let t=e.innerText; let m=t.match(/\\d[\\d\\s]{2,}/g); if(m) m.forEach(v=>{let n=parseInt(v.replace(/\\s/g,'')); if(n>100 && n<1000000) r.push(n)})}); return [...new Set(r)].sort((a,b)=>a-b);")
                    if js_prices:
                        wallet = js_prices[0]
                        standard = js_prices[1] if len(js_prices) > 1 else js_prices[0]
                        base = js_prices[-1] if len(js_prices) > 1 else 0

                if wallet == 0: wallet = standard
                if standard == 0: raise Exception("Price not found")

                brand_el = driver.find_elements(By.CSS_SELECTOR, ".product-page__header-brand, .brand-name")
                name_el = driver.find_elements(By.CSS_SELECTOR, ".product-page__header-title, h1")
                
                brand = brand_el[0].text.strip() if brand_el else "Unknown"
                name = name_el[0].text.strip() if name_el else f"Товар {sku}"

                return {
                    "id": sku, "name": name, "brand": brand,
                    "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                    "status": "success"
                }
            except Exception as e:
                logger.error(f"Err {attempt}: {e}")
                continue
            finally:
                if driver: driver.quit()
        return {"id": sku, "status": "error", "message": "Failed"}

    # --- ОТЗЫВЫ (API ONLY) ---
    def get_full_product_info(self, sku: int, limit: int = 50):
        logger.info(f"--- REVIEWS SKU: {sku} ---")
        try:
            # 1. Получаем Root ID через статику (без браузера)
            # Алгоритм корзин для 2025/26
            vol = sku // 100000
            part = sku // 1000
            
            # Перебор корзин для поиска card.json
            card_data = None
            for host_id in range(1, 20):
                host = f"{host_id:02d}"
                url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
                try:
                    r = requests.get(url, timeout=2)
                    if r.status_code == 200:
                        card_data = r.json()
                        card_data['host'] = host
                        break
                except: pass
            
            if not card_data:
                # Если статика не найдена, пробуем получить root через API карточки (без браузера)
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
                api_url = f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&nm={sku}"
                try:
                    r = requests.get(api_url, headers=headers, timeout=5)
                    if r.status_code == 200:
                        card_data = r.json().get('data', {}).get('products', [{}])[0]
                except: pass

            if not card_data: return {"status": "error", "message": "Product not found (card.json)"}
            
            root_id = card_data.get('root') or card_data.get('root_id') or card_data.get('imt_id')
            if not root_id: return {"status": "error", "message": "No Root ID"}

            # Картинка
            host = card_data.get('host', '01')
            img_url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"

            # 2. Качаем отзывы
            feed_data = None
            for d in ["feedbacks1", "feedbacks2"]:
                try:
                    r = requests.get(f"https://{d}.wb.ru/feedbacks/v1/{root_id}", timeout=10)
                    if r.status_code == 200: 
                        feed_data = r.json()
                        break
                except: pass
            
            if not feed_data: return {"status": "error", "message": "Feedbacks API fail"}
            
            reviews = []
            for f in feed_data.get('feedbacks', [])[:limit]:
                if f.get('text'): reviews.append({"text": f['text'], "rating": f.get('productValuation', 5)})
            
            return {
                "sku": sku, "image": img_url,
                "rating": float(feed_data.get('valuation', 0)),
                "reviews": reviews, "reviews_count": len(reviews),
                "status": "success"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

parser_service = SeleniumWBParser()