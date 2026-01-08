import os
import time
import random
import logging
import json
import re
import sys
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

    # --- ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ДЛЯ СТАТИКИ (BASKETS) ---
    
    def _get_basket_number(self, sku: int) -> str:
        """Определяет номер корзины (хоста) по артикулу"""
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
        return "18" # Fallback

    async def get_static_data(self, sku: int):
        """
        Получает мгновенные данные из JSON-корзины WB (без Selenium).
        Возвращает: name, brand, root_id (imt_id), image_url
        """
        basket = self._get_basket_number(sku)
        vol = sku // 100000
        part = sku // 1000
        url = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "name": data.get("imt_name") or data.get("subj_name"),
                            "brand": data.get("selling", {}).get("brand_name"),
                            "root_id": data.get("root"),
                            "subject_id": data.get("subj_root_id"),
                            "image": f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"
                        }
        except Exception as e:
            logger.warning(f"Static data fetch failed: {e}")
        return None

    # --- SELENIUM LOGIC ---

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
        edge_options.add_argument("--window-size=1920,1080")
        edge_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
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
            if elements:
                txt = driver.execute_script("return arguments[0].textContent;", elements[0])
                if not txt: txt = driver.execute_script("return arguments[0].innerText;", elements[0])
                digits = re.sub(r'[^\d]', '', txt)
                return int(digits) if digits else 0
        except: return 0
        return 0

    # ВАЖНО: Этот метод теперь асинхронный, так как вызывает async get_static_data
    # Но так как он вызывается из синхронного Celery, мы будем использовать loop.run_until_complete внутри main.py или tasks.py
    # Либо сделаем его синхронной оберткой.
    # В данном случае, чтобы не ломать архитектуру Selenium (он синхронный), 
    # мы вызовем aiohttp внутри синхронного кода через asyncio.run() или loop
    
    def get_product_data(self, sku: int):
        logger.info(f"--- АНАЛИЗ SKU: {sku} ---")
        
        # 1. Сначала пытаемся получить статику (это быстро и надежно)
        static_info = {}
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            static_info = loop.run_until_complete(self.get_static_data(sku)) or {}
            logger.info(f"Статика получена: {static_info.get('name')}")
        except Exception as e:
            logger.error(f"Ошибка статики: {e}")

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
                while time.time() - start < 45:
                    if driver.find_elements(By.CSS_SELECTOR, "[class*='priceBlockFinalPrice']"): break
                    time.sleep(1)

                wallet = self._extract_price(driver, "[class*='priceBlockWalletPrice'], [class*='productLinePriceWallet'], .price-block__wallet-price")
                standard = self._extract_price(driver, "[class*='priceBlockFinalPrice'], [class*='productLinePriceNow'], .price-block__final-price")
                base = self._extract_price(driver, "[class*='priceBlockOldPrice'], [class*='productLinePriceOld'], .price-block__old-price")

                if not standard and not wallet:
                     # Fallback JS Scanner
                    js_prices = driver.execute_script("let r=[]; document.querySelectorAll('[class*=\"price\"]').forEach(e=>{let t=e.innerText; let m=t.match(/\\d[\\d\\s]{2,}/g); if(m) m.forEach(v=>{let n=parseInt(v.replace(/\\s/g,'')); if(n>100 && n<1000000) r.push(n)})}); return [...new Set(r)].sort((a,b)=>a-b);")
                    if js_prices:
                        clean = sorted([n for n in js_prices if n > 400])
                        if clean:
                            wallet = clean[0]
                            standard = clean[1] if len(clean) > 1 else clean[0]
                            base = clean[-1] if len(clean) > 1 else 0

                if wallet == 0: wallet = standard
                if standard == 0: raise Exception("Цена не найдена")

                # Если статика не сработала, берем из Selenium
                brand = static_info.get('brand') or "Unknown"
                name = static_info.get('name') or f"Товар {sku}"
                
                # Если в статике пусто, пробуем со страницы
                if brand == "Unknown":
                     brand_el = driver.find_elements(By.CSS_SELECTOR, ".product-page__header-brand")
                     if brand_el: brand = brand_el[0].text.strip()
                if name == f"Товар {sku}":
                     name_el = driver.find_elements(By.CSS_SELECTOR, ".product-page__header-title")
                     if name_el: name = name_el[0].text.strip()

                return {
                    "id": sku, 
                    "name": name,
                    "brand": brand,
                    "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                    "status": "success"
                }
            except Exception as e:
                logger.error(f"Error {attempt}: {e}")
                continue
            finally:
                if driver: driver.quit()
        return {"id": sku, "status": "error", "message": "Failed"}

    def get_full_product_info(self, sku: int, limit: int = 50):
        """
        Сбор отзывов. Использует imtId из статики + aiohttp API.
        Это намного быстрее и надежнее Selenium.
        """
        logger.info(f"--- АНАЛИЗ ОТЗЫВОВ SKU: {sku} ---")
        
        try:
            # 1. Получаем Root ID (imtId) из статики
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            static_data = loop.run_until_complete(self.get_static_data(sku))
            
            if not static_data or not static_data.get('root_id'):
                raise Exception("Не удалось получить Root ID товара из статики")
                
            root_id = static_data['root_id']
            img_url = static_data['image']
            
            # 2. Качаем отзывы через API (aiohttp)
            reviews_data = []
            rating = 0.0
            
            async def fetch_feedbacks():
                url = f"https://feedbacks1.wb.ru/feedbacks/v1/{root_id}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        return None

            feed_data = loop.run_until_complete(fetch_feedbacks())
            
            if feed_data:
                rating = float(feed_data.get('valuation', 0))
                raw_list = feed_data.get('feedbacks', [])
                # Сортируем по дате (свежие) и фильтруем пустые
                raw_list.sort(key=lambda x: x.get('createdDate', ''), reverse=True)
                
                for f in raw_list:
                    txt = f.get('text', '')
                    if txt:
                        reviews_data.append({
                            "text": txt,
                            "rating": f.get('productValuation', 5)
                        })
                    if len(reviews_data) >= limit: break
            
            if not reviews_data:
                # Если API пустое, только тогда запускаем Selenium (Fallback)
                logger.warning("API отзывов пустое, запускаю Selenium...")
                return self._selenium_reviews_fallback(sku, limit)

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

    def _selenium_reviews_fallback(self, sku, limit):
        logger.info(f"--- АНАЛИЗ ОТЗЫВОВ SKU: {sku} ---")
        driver = None
        try:
            # 1. Получаем imtId (root) товара
            driver = self._init_driver()
            driver.get(f"https://www.wildberries.ru/catalog/{sku}/detail.aspx")
            time.sleep(3)
            
            if "Kaspersky" in driver.page_source: raise Exception("Blocked by Kaspersky")

            # Пытаемся достать root ID из JS
            root_id = driver.execute_script("return window.staticModel?.product?.root || window.staticModel?.card?.root || 0;")
            
            # Если не вышло, пробуем через API card.wb.ru (это публичный API)
            if not root_id:
                logger.info("Root ID не в staticModel, пробую API...")
                # Используем requests внутри Python, чтобы не мучить браузер
                card_resp = requests.get(f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={sku}")
                if card_resp.status_code == 200:
                    data = card_resp.json()
                    root_id = data['data']['products'][0]['root']
            
            driver.quit() # Браузер больше не нужен
            driver = None

            if not root_id:
                raise Exception("Не удалось получить root ID товара")

            logger.info(f"Root ID: {root_id}. Скачиваю отзывы через API...")

            # 2. Скачиваем отзывы через прямой запрос (самый надежный метод)
            # feedbacks1.wb.ru/feedbacks/v1/{root_id}
            
            reviews_data = []
            rating = 0.0
            
            api_url = f"https://feedbacks1.wb.ru/feedbacks/v1/{root_id}"
            resp = requests.get(api_url)
            
            if resp.status_code == 200:
                data = resp.json()
                rating = float(data.get('valuation', 0))
                
                raw_feedbacks = data.get('feedbacks', [])
                # Сортируем по дате (свежие первые) или полезности
                # Берем только текстовые
                for f in raw_feedbacks:
                    if f.get('text'):
                        reviews_data.append({
                            "text": f['text'],
                            "rating": f.get('productValuation', 5)
                        })
                        if len(reviews_data) >= limit: break
            else:
                raise Exception(f"API отзывов вернул {resp.status_code}")

            return {
                "sku": sku,
                "image": f"https://basket-01.wbbasket.ru/vol{sku//100000}/part{sku//1000}/{sku}/images/c246x328/1.webp", # Генерируем ссылку на фото
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