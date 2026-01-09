import os
import time
import random
import logging
import json
import re
import sys
import requests
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

    # --- ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ---
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
        try:
            basket = self._get_basket_number(sku)
            vol = sku // 100000
            part = sku // 1000
            url = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                data['image_url'] = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"
                return data
        except: pass
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
                digits = re.sub(r'[^\d]', '', txt)
                return int(digits) if digits else 0
        except: return 0
        return 0

    def get_product_data(self, sku: int):
        """Парсинг цен (Selenium Old Stable)"""
        logger.info(f"--- PRICES SKU: {sku} ---")
        
        # Берем имя из статики, чтобы не падать на селекторах
        static_data = self._get_static_card_data(sku)
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

                # Ожидание
                start = time.time()
                while time.time() - start < 60:
                    if driver.find_elements(By.CSS_SELECTOR, "[class*='priceBlockFinalPrice']"): break
                    time.sleep(1)

                # Селекторы
                wallet = self._extract_price(driver, "[class*='priceBlockWalletPrice'], .price-block__wallet-price, [class*='productLinePriceWallet']")
                standard = self._extract_price(driver, "[class*='priceBlockFinalPrice'], .price-block__final-price, [class*='productLinePriceNow']")
                base = self._extract_price(driver, "[class*='priceBlockOldPrice'], .price-block__old-price, [class*='productLinePriceOld']")

                # JS Fallback
                if not standard and not wallet:
                    logger.info("JS Fallback...")
                    js_prices = driver.execute_script("let r=[]; document.querySelectorAll('[class*=\"price\"]').forEach(e=>{let t=e.innerText; let m=t.match(/\\d[\\d\\s]{2,}/g); if(m) m.forEach(v=>{let n=parseInt(v.replace(/\\s/g,'')); if(n>100 && n<1000000) r.push(n)})}); return [...new Set(r)].sort((a,b)=>a-b);")
                    if js_prices:
                        clean = sorted([n for n in js_prices if n > 400])
                        if clean:
                            wallet = clean[0]
                            standard = clean[1] if len(clean) > 1 else clean[0]
                            base = clean[-1] if len(clean) > 1 else 0

                if wallet == 0: wallet = standard
                if standard == 0: raise Exception("Prices not found")
                
                # Доп. попытка взять бренд со страницы
                if brand == "Unknown":
                    b_el = driver.find_elements(By.CSS_SELECTOR, ".product-page__header-brand")
                    if b_el: brand = b_el[0].text.strip()

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
        return {"id": sku, "status": "error", "message": "Failed to parse prices"}

    def get_full_product_info(self, sku: int, limit: int = 50):
        """
        Сбор отзывов (Static + API). Работает стабильно.
        """
        logger.info(f"--- REVIEWS SKU: {sku} ---")
        try:
            static_data = self._get_static_card_data(sku)
            if not static_data: return {"status": "error", "message": "Static API fail"}
            
            root_id = static_data.get('root_id') or static_data.get('root') or static_data.get('imt_id')
            if not root_id: return {"status": "error", "message": "No Root ID"}
            
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            feed_data = None
            
            for d in ["feedbacks1", "feedbacks2"]:
                try:
                    r = requests.get(f"https://{d}.wb.ru/feedbacks/v1/{root_id}", headers=headers, timeout=10)
                    if r.status_code == 200: 
                        feed_data = r.json()
                        break
                except: pass
            
            if not feed_data: return {"status": "error", "message": "Feedbacks API fail"}
            
            reviews = []
            for f in feed_data.get('feedbacks', [])[:limit]:
                if f.get('text'): reviews.append({"text": f['text'], "rating": f.get('productValuation', 5)})
            
            return {
                "sku": sku, "image": static_data.get('image_url'),
                "rating": float(feed_data.get('valuation', 0)),
                "reviews": reviews, "reviews_count": len(reviews),
                "status": "success"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

parser_service = SeleniumWBParser()