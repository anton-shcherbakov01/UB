import os
import time
import random
import logging
import zipfile
import json
import re
import sys
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
            logger.error(f"Driver Error: {e}")
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
        logger.info(f"--- АНАЛИЗ ЦЕН SKU: {sku} ---")
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            driver = None
            try:
                driver = self._init_driver()
                driver.get("https://www.wildberries.ru/")
                driver.add_cookie({"name": "x-city-id", "value": "77"})
                driver.get(f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP&dest=-1257786")
                
                time.sleep(3)
                driver.execute_script("window.scrollTo(0, 400);")
                
                if "Kaspersky" in driver.page_source: driver.quit(); continue

                start = time.time()
                found = False
                while time.time() - start < 45:
                    if driver.find_elements(By.CSS_SELECTOR, "[class*='priceBlockFinalPrice']"): 
                        found = True; break
                    time.sleep(1)

                wallet = self._extract_price(driver, "[class*='priceBlockWalletPrice'], [class*='productLinePriceWallet'], .price-block__wallet-price")
                standard = self._extract_price(driver, "[class*='priceBlockFinalPrice'], [class*='productLinePriceNow'], .price-block__final-price")
                base = self._extract_price(driver, "[class*='priceBlockOldPrice'], [class*='productLinePriceOld'], .price-block__old-price")

                if not standard and not wallet:
                    js_prices = driver.execute_script("let r=[]; document.querySelectorAll('[class*=\"price\"]').forEach(e=>{let t=e.innerText; let m=t.match(/\\d[\\d\\s]{2,}/g); if(m) m.forEach(v=>{let n=parseInt(v.replace(/\\s/g,'')); if(n>100 && n<1000000) r.push(n)})}); return [...new Set(r)].sort((a,b)=>a-b);")
                    if js_prices:
                        wallet = js_prices[0]
                        standard = js_prices[1] if len(js_prices) > 1 else js_prices[0]
                        base = js_prices[-1] if len(js_prices) > 2 else 0

                if wallet == 0: wallet = standard
                if standard == 0: raise Exception("Price not found")

                brand_el = driver.find_elements(By.CSS_SELECTOR, ".product-page__header-brand, .product-page__brand, span.brand")
                name_el = driver.find_elements(By.CSS_SELECTOR, ".product-page__header-title, h1")
                
                return {
                    "id": sku, 
                    "name": name_el[0].text.strip() if name_el else f"Товар {sku}",
                    "brand": brand_el[0].text.strip() if brand_el else "Unknown",
                    "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                    "status": "success"
                }
            except Exception as e:
                logger.error(f"Error: {e}")
                continue
            finally:
                if driver: driver.quit()
        return {"id": sku, "status": "error", "message": "Failed to parse prices"}

    def get_full_product_info(self, sku: int, limit: int = 50):
        """
        НОВЫЙ МЕТОД: Парсинг отзывов для ИИ.
        Использует расширенные селекторы.
        """
        logger.info(f"--- АНАЛИЗ ОТЗЫВОВ SKU: {sku} ---")
        driver = None
        try:
            driver = self._init_driver()
            url = f"https://www.wildberries.ru/catalog/{sku}/feedbacks?targetUrl=GP&dest=-1257786"
            driver.get(url)
            
            time.sleep(5)
            if "Kaspersky" in driver.page_source: raise Exception("Blocked by Kaspersky")

            # Скролл
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)

            # Статика
            img_url = ""
            try:
                img = driver.find_elements(By.CSS_SELECTOR, ".photo-container__photo, .j-image-canvas, img[src*='images.wbstatic']")
                if img: img_url = img[0].get_attribute("src")
            except: pass

            rating = 0.0
            try:
                rate = driver.find_elements(By.CSS_SELECTOR, ".product-review__rating, .rating-product__value, .user-activity__rating")
                if rate: rating = float(rate[0].text.strip())
            except: pass

            # Отзывы
            reviews_data = []
            # Обновленные селекторы для отзывов
            review_cards = driver.find_elements(By.CSS_SELECTOR, ".comments__item, .feedback__item, .comments__item-wrap")
            
            for card in review_cards[:limit]:
                try:
                    text_el = card.find_elements(By.CSS_SELECTOR, ".comments__text, .feedback__text, .j-feedback-text")
                    if not text_el: continue
                    text = text_el[0].text.strip()
                    
                    stars = len(card.find_elements(By.CSS_SELECTOR, ".star.star--active, .feedback__rating-star--active"))
                    if stars == 0: stars = 5
                    
                    if text:
                        reviews_data.append({"text": text, "rating": stars})
                except: continue

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
        finally:
            if driver: driver.quit()

parser_service = SeleniumWBParser()