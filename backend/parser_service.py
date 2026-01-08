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

                if not standard: 
                    js_prices = driver.execute_script("let r=[]; document.querySelectorAll('[class*=\"price\"]').forEach(e=>{let t=e.innerText; let m=t.match(/\\d[\\d\\s]{2,}/g); if(m) m.forEach(v=>{let n=parseInt(v.replace(/\\s/g,'')); if(n>100 && n<1000000) r.push(n)})}); return [...new Set(r)].sort((a,b)=>a-b);")
                    if js_prices:
                        clean = sorted([n for n in js_prices if n > 400])
                        if clean:
                            wallet = clean[0]
                            standard = clean[1] if len(clean) > 1 else clean[0]
                            base = clean[-1] if len(clean) > 1 else 0

                if wallet == 0: wallet = standard
                if standard == 0: raise Exception("Price not found")

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
        Теперь с ретраями и логами ошибок.
        """
        logger.info(f"--- REVIEWS API SKU: {sku} ---")
        
        # Заголовки как у настоящего браузера
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Origin": "https://www.wildberries.ru",
            "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
        }

        try:
            # 1. Получаем imtId (root) через карточку товара
            card_url = f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={sku}"
            data = None
            
            # Ретрай для получения карточки
            for i in range(3):
                try:
                    logger.info(f"GET Card Attempt {i+1}: {card_url}")
                    resp = requests.get(card_url, headers=headers, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        break
                    else:
                        logger.warning(f"Card API Fail {resp.status_code}: {resp.text[:100]}")
                except Exception as req_e:
                    logger.warning(f"Card API Error: {req_e}")
                time.sleep(2)
            
            if not data:
                raise Exception("Не удалось получить данные карточки после 3 попыток")

            products = data.get('data', {}).get('products', [])
            if not products: 
                raise Exception(f"Товар не найден в API WB. Ответ: {str(data)[:200]}")
            
            root_id = products[0].get('root')
            if not root_id:
                raise Exception(f"Root ID (imtId) не найден для SKU {sku}")
                
            img_url = f"https://basket-01.wbbasket.ru/vol{sku//100000}/part{sku//1000}/{sku}/images/c246x328/1.webp" 
            rating = float(products[0].get('reviewRating', 0))

            logger.info(f"Root ID: {root_id}. Запрос отзывов...")

            # 2. Получаем отзывы
            feed_url = f"https://feedbacks1.wb.ru/feedbacks/v1/{root_id}"
            feed_data = None
            
            # Ретрай для отзывов
            for i in range(3):
                try:
                    resp = requests.get(feed_url, headers=headers, timeout=10)
                    if resp.status_code == 200:
                        feed_data = resp.json()
                        break
                    else:
                        logger.warning(f"Feedbacks API Fail {resp.status_code}")
                except Exception as req_e:
                    logger.warning(f"Feedbacks API Error: {req_e}")
                time.sleep(2)

            if not feed_data:
                 raise Exception("Не удалось скачать отзывы (API недоступен)")

            raw_feedbacks = feed_data.get('feedbacks', [])
            if not raw_feedbacks:
                 logger.info("У товара нет отзывов.")
            
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
            logger.error(f"REVIEWS CRITICAL ERROR: {str(e)}")
            return {"status": "error", "message": str(e)}

parser_service = SeleniumWBParser()