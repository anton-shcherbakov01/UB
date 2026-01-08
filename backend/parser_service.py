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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | [%(name)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("WB-Parser")
logging.getLogger('WDM').setLevel(logging.ERROR)

class SeleniumWBParser:
    """
    Микросервис парсинга Wildberries v7.0 (Static CDN + Selenium).
    Использует алгоритм вычисления корзин для мгновенного доступа к данным товара.
    """
    def __init__(self):
        self.headless = os.getenv("HEADLESS", "True").lower() == "true"
        self.proxy_user = os.getenv("PROXY_USER")
        self.proxy_pass = os.getenv("PROXY_PASS")
        self.proxy_host = os.getenv("PROXY_HOST")
        self.proxy_port = os.getenv("PROXY_PORT")

    # --- ВСПОМОГАТЕЛЬНАЯ ЛОГИКА WB (BASKETS) ---
    def _get_basket_number(self, sku: int) -> str:
        """Алгоритм определения хоста корзины по артикулу"""
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
        """
        Скачивает card.json напрямую с CDN Wildberries.
        Самый надежный способ получить root ID и статику.
        """
        try:
            basket = self._get_basket_number(sku)
            vol = sku // 100000
            part = sku // 1000
            url = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
            
            # CDN обычно не требует прокси, используем прямой запрос
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            else:
                logger.warning(f"Static CDN returned {resp.status_code} for {url}")
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
        driver.set_page_load_timeout(60)
        return driver

    def _get_json_from_browser(self, driver, url):
        """Открывает URL в браузере и парсит body как JSON."""
        logger.info(f"Browser API Request: {url}")
        driver.get(url)
        if "Kaspersky" in driver.page_source: return None
        content = driver.find_element(By.TAG_NAME, "body").text
        try: return json.loads(content)
        except: return None

    def _extract_digits(self, text):
        if not text: return 0
        text = str(text).replace('&nbsp;', '').replace(u'\xa0', '')
        digits = re.sub(r'[^\d]', '', text)
        return int(digits) if digits else 0

    def get_product_data(self, sku: int):
        """Парсинг цен (Selenium)"""
        logger.info(f"--- АНАЛИЗ ЦЕН SKU: {sku} ---")
        
        # 1. Получаем статику для надежного названия и бренда
        static_data = self._get_static_card_data(sku)
        brand = static_data.get('selling', {}).get('brand_name') if static_data else "Unknown"
        name = static_data.get('imt_name') or static_data.get('subj_name') if static_data else f"Товар {sku}"

        for attempt in range(1, 3):
            driver = None
            try:
                driver = self._init_driver()
                
                # Используем API карточки через браузер для цен
                api_url = f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&nm={sku}"
                data = self._get_json_from_browser(driver, api_url)
                
                if data and 'data' in data and data['data']['products']:
                    product = data['data']['products'][0]
                    wallet = self._extract_digits(product.get('clientPriceU', 0)) // 100
                    standard = self._extract_digits(product.get('salePriceU', 0)) // 100
                    base = self._extract_digits(product.get('priceU', 0)) // 100
                    
                    if wallet == 0: wallet = standard
                    
                    # Если название/бренд не нашлись в статике, берем отсюда
                    if brand == "Unknown": brand = product.get('brand', 'Unknown')
                    if name == f"Товар {sku}": name = product.get('name', name)

                    logger.info(f"Успех (JSON API): {wallet}₽")
                    return {
                        "id": sku, "name": name, "brand": brand,
                        "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                        "status": "success"
                    }
                
                raise Exception("JSON API не вернул данные")

            except Exception as e:
                logger.error(f"Try {attempt}: {e}")
                continue
            finally:
                if driver: driver.quit()
        return {"id": sku, "status": "error", "message": "Failed to parse prices"}

    def get_full_product_info(self, sku: int, limit: int = 50):
        """
        Сбор отзывов. Использует Static CDN для получения root ID.
        """
        logger.info(f"--- АНАЛИЗ ОТЗЫВОВ SKU: {sku} ---")
        driver = None
        try:
            # 1. Получаем Root ID через статику (без браузера, мгновенно)
            static_data = self._get_static_card_data(sku)
            
            if not static_data:
                # Если статика не сработала, пробуем через браузерное API карточки
                logger.warning("Статика не сработала, пробуем Browser API...")
                driver = self._init_driver()
                api_url = f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&nm={sku}"
                card_data = self._get_json_from_browser(driver, api_url)
                if card_data and 'data' in card_data and card_data['data']['products']:
                    static_data = card_data['data']['products'][0]
                    static_data['root_id'] = static_data.get('root')
                    # Генерируем картинку, если её нет
                    vol = sku // 100000
                    part = sku // 1000
                    static_data['image'] = f"https://basket-{self._get_basket_number(sku)}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"

            if not static_data or not static_data.get('root_id'):
                raise Exception("Не удалось получить Root ID товара")

            root_id = static_data['root_id']
            img_url = static_data.get('image', '')
            
            logger.info(f"Root ID: {root_id}. Запрос отзывов...")

            # 2. Скачиваем отзывы через requests (Feedbacks API)
            # Используем заголовки браузера
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Origin": "https://www.wildberries.ru",
                "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            }
            
            # Пробуем разные зеркала API отзывов
            feed_data = None
            for domain in ["feedbacks1", "feedbacks2"]:
                try:
                    url = f"https://{domain}.wb.ru/feedbacks/v1/{root_id}"
                    resp = requests.get(url, headers=headers, timeout=10)
                    if resp.status_code == 200:
                        feed_data = resp.json()
                        break
                except: pass
            
            if not feed_data:
                raise Exception("API отзывов недоступен")

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