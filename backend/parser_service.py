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
    """
    Микросервис парсинга Wildberries v4.1.
    Исправлен парсинг отзывов: получение root ID через браузер.
    """
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
        edge_options.add_argument("--lang=ru-RU")
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
        text = text.replace('&nbsp;', '').replace(u'\xa0', '')
        digits = re.sub(r'[^\d]', '', text)
        return int(digits) if digits else 0

    def get_product_data(self, sku: int):
        logger.info(f"--- АНАЛИЗ ЦЕН SKU: {sku} ---")
        for attempt in range(1, 3):
            driver = None
            try:
                driver = self._init_driver()
                driver.get(f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP&dest=-1257786")
                
                time.sleep(3)
                if "Kaspersky" in driver.page_source: driver.quit(); continue

                # ЭТАП 1: Попытка вытащить JSON из страницы (Самый надежный метод)
                try:
                    product_json = driver.execute_script("return window.staticModel ? JSON.stringify(window.staticModel) : null;")
                    if product_json:
                        data = json.loads(product_json)
                        price_data = data.get('price') or {}
                        if not price_data and 'products' in data:
                             price_data = data['products'][0] if data['products'] else {}

                        basic = int(price_data.get('basicPrice', 0) / 100) or int(price_data.get('priceU', 0) / 100)
                        total = int(price_data.get('totalPrice', 0) / 100) or int(price_data.get('salePriceU', 0) / 100)
                        
                        brand = data.get('brand') or data.get('selling', {}).get('brand_name') or "Unknown"
                        name = data.get('name') or data.get('imt_name') or f"Товар {sku}"

                        if total > 0:
                            logger.info(f"JSON Success: {total}₽")
                            return {
                                "id": sku, "name": name, "brand": brand,
                                "prices": {"wallet_purple": total, "standard_black": total, "base_crossed": basic},
                                "status": "success"
                            }
                except: pass

                # ЭТАП 2: DOM Парсинг
                driver.execute_script("window.scrollTo(0, 400);")
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='price']")))

                prices = []
                elements = driver.find_elements(By.CSS_SELECTOR, ".price-block__wallet-price, .price-block__final-price, .price-block__old-price, [class*='Price']")
                for el in elements:
                    txt = el.get_attribute('textContent')
                    nums = re.findall(r'\d+', txt.replace('\xa0', '').replace(' ', ''))
                    if nums: prices.append(int(nums[0]))
                
                prices = sorted(list(set([p for p in prices if 100 < p < 1000000])))
                
                if prices:
                    wallet = prices[0]
                    base = prices[-1]
                    standard = prices[1] if len(prices) > 2 else wallet
                    
                    brand_el = driver.find_elements(By.CSS_SELECTOR, ".product-page__header-brand")
                    brand = brand_el[0].text.strip() if brand_el else "Unknown"
                    name_el = driver.find_elements(By.CSS_SELECTOR, "h1")
                    name = name_el[0].text.strip() if name_el else str(sku)

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
        Сбор отзывов. Сначала получаем root (imtId) через Selenium (гарантированно),
        затем делаем чистый запрос к API отзывов через requests.
        """
        logger.info(f"--- АНАЛИЗ ОТЗЫВОВ SKU: {sku} ---")
        driver = None
        try:
            # 1. Запускаем браузер ТОЛЬКО чтобы получить Root ID
            # Мы не используем requests к card.wb.ru, так как он падает (404/403)
            driver = self._init_driver()
            driver.get(f"https://www.wildberries.ru/catalog/{sku}/detail.aspx")
            
            # Ждем загрузки скриптов
            time.sleep(5)
            
            if "Kaspersky" in driver.page_source: 
                raise Exception("Blocked by Kaspersky")

            # Пытаемся достать root ID из JS-объектов на странице
            # Это самый надежный способ, так как эти данные нужны самому сайту для работы
            root_id = driver.execute_script("""
                try {
                    // Пробуем разные места, где WB хранит ID
                    return window.staticModel?.product?.root || 
                           window.staticModel?.card?.root || 
                           window.__INITIAL_STATE__?.model?.product?.root ||
                           0;
                } catch(e) { return 0; }
            """)
            
            # Если не нашли в JS, ищем ссылку на отзывы в DOM (в ней есть imtId)
            if not root_id:
                logger.info("JS Root ID не найден, ищем в DOM...")
                try:
                    # Ссылка на отзывы часто содержит imtId
                    # Пример: /catalog/172672138/feedbacks?imtId=123456
                    links = driver.find_elements(By.CSS_SELECTOR, "a[href*='feedbacks']")
                    for link in links:
                        href = link.get_attribute('href')
                        match = re.search(r'imtId=(\d+)', href)
                        if match:
                            root_id = int(match.group(1))
                            break
                except: pass

            driver.quit() # Браузер больше не нужен
            driver = None

            if not root_id:
                raise Exception("Не удалось получить Root ID товара со страницы")

            logger.info(f"Root ID (imtId): {root_id}. Запрос к API отзывов...")

            # 2. Скачиваем отзывы через прямой запрос к API
            # Используем заголовки браузера, чтобы не заблокировали
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Origin": "https://www.wildberries.ru",
                "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            }
            
            feed_url = f"https://feedbacks1.wb.ru/feedbacks/v1/{root_id}"
            
            # Ретрай для API
            feed_data = None
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
                 raise Exception("API отзывов недоступен")

            img_url = f"https://basket-01.wbbasket.ru/vol{sku//100000}/part{sku//1000}/{sku}/images/c246x328/1.webp"
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

            logger.info(f"Собрано {len(reviews_data)} отзывов")
            
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