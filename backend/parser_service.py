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

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
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
        logger.info(f"--- PRICES SKU: {sku} ---")
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            driver = None
            try:
                driver = self._init_driver()
                driver.get(f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP&dest=-1257786")
                time.sleep(3)
                driver.execute_script("window.scrollTo(0, 400);")
                if "Kaspersky" in driver.page_source: driver.quit(); continue

                start = time.time()
                while time.time() - start < 45:
                    if driver.find_elements(By.CSS_SELECTOR, "[class*='priceBlockFinalPrice']"): break
                    time.sleep(1)

                wallet = self._extract_price(driver, "[class*='priceBlockWalletPrice'], .price-block__wallet-price")
                standard = self._extract_price(driver, "[class*='priceBlockFinalPrice'], .price-block__final-price")
                base = self._extract_price(driver, "[class*='priceBlockOldPrice'], .price-block__old-price")

                if not standard: # Fallback JS
                    js_prices = driver.execute_script("let r=[]; document.querySelectorAll('[class*=\"price\"]').forEach(e=>{let t=e.innerText; let m=t.match(/\\d[\\d\\s]{2,}/g); if(m) m.forEach(v=>{let n=parseInt(v.replace(/\\s/g,'')); if(n>100 && n<1000000) r.push(n)})}); return [...new Set(r)].sort((a,b)=>a-b);")
                    if js_prices:
                        wallet = js_prices[0]
                        standard = js_prices[1] if len(js_prices) > 1 else js_prices[0]
                        base = js_prices[-1] if len(js_prices) > 2 else 0

                if wallet == 0: wallet = standard
                if standard == 0: raise Exception("Prices not found")

                brand_el = driver.find_elements(By.CSS_SELECTOR, ".product-page__header-brand")
                name_el = driver.find_elements(By.CSS_SELECTOR, ".product-page__header-title")
                
                return {
                    "id": sku, 
                    "name": name_el[0].text.strip() if name_el else f"Товар {sku}",
                    "brand": brand_el[0].text.strip() if brand_el else "Unknown",
                    "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                    "status": "success"
                }
            except Exception as e:
                logger.error(f"Err: {e}")
                continue
            finally:
                if driver: driver.quit()
        return {"id": sku, "status": "error", "message": "Failed"}

    def get_full_product_info(self, sku: int, limit: int = 50):
        """
        Сбор отзывов через API WB (feedbacks1.wb.ru).
        Не требует Selenium, работает мгновенно.
        """
        logger.info(f"--- REVIEWS API SKU: {sku} ---")
        try:
            # 1. Получаем imtId (root) через карточку товара (публичный JSON)
            card_url = f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={sku}"
            resp = requests.get(card_url, timeout=10)
            if resp.status_code != 200: raise Exception("WB Card API error")
            
            data = resp.json()
            products = data.get('data', {}).get('products', [])
            if not products: raise Exception("Product not found")
            
            root_id = products[0].get('root')
            img_url = f"https://basket-01.wbbasket.ru/vol{sku//100000}/part{sku//1000}/{sku}/images/c246x328/1.webp" # Генерация ссылки на фото
            rating = float(products[0].get('reviewRating', 0))

            # 2. Получаем отзывы
            feed_url = f"https://feedbacks1.wb.ru/feedbacks/v1/{root_id}"
            feed_resp = requests.get(feed_url, timeout=10)
            if feed_resp.status_code != 200: raise Exception("Feedbacks API error")
            
            feed_data = feed_resp.json()
            raw_feedbacks = feed_data.get('feedbacks', [])
            
            # Сортировка: полезные и с текстом
            reviews_data = []
            for f in raw_feedbacks:
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

        except Exception as e:
            logger.error(f"Reviews Error: {e}")
            return {"status": "error", "message": str(e)}

parser_service = SeleniumWBParser()