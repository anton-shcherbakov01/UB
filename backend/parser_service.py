import os
import time
import random
import logging
import json
import re
import sys
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
    Микросервис парсинга Wildberries v6.0 (API via Browser).
    Использует Selenium как прокси-клиент для доступа к API WB, 
    что гарантирует обход TLS-фингерпринтинга и Cloudflare.
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
        """
        Открывает URL в браузере и возвращает JSON из тела страницы.
        Это обходит 99% защит, так как запрос делает реальный браузер.
        """
        logger.info(f"API Request via Browser: {url}")
        driver.get(url)
        
        # Проверка на блокировку
        if "Kaspersky" in driver.page_source or "Access denied" in driver.title:
            logger.warning("Блокировка доступа к API.")
            return None

        # Извлекаем текст из body
        content = driver.find_element(By.TAG_NAME, "body").text
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.error(f"Не удалось распарсить JSON. Content start: {content[:100]}")
            return None

    def _extract_digits(self, text):
        if not text: return 0
        text = str(text).replace('&nbsp;', '').replace(u'\xa0', '')
        digits = re.sub(r'[^\d]', '', text)
        return int(digits) if digits else 0

    def get_product_data(self, sku: int):
        """Парсинг цен через JSON API (самый точный метод)"""
        logger.info(f"--- АНАЛИЗ ЦЕН SKU: {sku} ---")
        
        driver = None
        try:
            driver = self._init_driver()
            
            # Используем API карточки товара (dest=-1257786 это Москва)
            # Это тот же API, что и в вашем примере (wb_client), но через Selenium
            api_url = f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&nm={sku}"
            
            data = self._get_json_from_browser(driver, api_url)
            
            if not data or 'data' not in data:
                raise Exception("API карточки вернул пустой результат")

            products = data['data']['products']
            if not products:
                raise Exception("Товар не найден (пустой список products)")
            
            product = products[0]
            
            # Извлекаем цены
            # clientPriceU - цена с СПП (кошелек)
            # salePriceU - цена со скидкой
            # priceU - базовая цена
            
            wallet = self._extract_digits(product.get('clientPriceU', 0)) // 100
            standard = self._extract_digits(product.get('salePriceU', 0)) // 100
            base = self._extract_digits(product.get('priceU', 0)) // 100
            
            # Если кошелька нет, он равен стандарту
            if wallet == 0: wallet = standard
            
            # Извлекаем названия
            brand = product.get('brand', 'Unknown')
            name = product.get('name', f"Товар {sku}")
            
            # Rating
            rating = float(product.get('reviewRating', 0) or product.get('rating', 0))

            logger.info(f"Успех (API): {brand} | {name} | {wallet}₽")
            
            return {
                "id": sku, 
                "name": name, 
                "brand": brand,
                "rating": rating,
                "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Price Parse Error: {e}")
            return {"id": sku, "status": "error", "message": str(e)}
        finally:
            if driver: driver.quit()

    def get_full_product_info(self, sku: int, limit: int = 50):
        """
        Сбор отзывов.
        1. Получаем imtId (root) через API карточки (в браузере).
        2. Получаем отзывы через API отзывов (в браузере).
        """
        logger.info(f"--- АНАЛИЗ ОТЗЫВОВ SKU: {sku} ---")
        driver = None
        try:
            driver = self._init_driver()
            
            # 1. Получаем imtId (root)
            card_url = f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&nm={sku}"
            card_data = self._get_json_from_browser(driver, card_url)
            
            if not card_data or not card_data.get('data', {}).get('products'):
                 raise Exception("Не удалось загрузить карточку товара")
            
            product = card_data['data']['products'][0]
            root_id = product.get('root') # Он же imtId
            
            if not root_id:
                raise Exception("Root ID (imtId) не найден в API карточки")
            
            # Картинка и рейтинг
            img_url = f"https://basket-01.wbbasket.ru/vol{sku//100000}/part{sku//1000}/{sku}/images/c246x328/1.webp"
            rating = float(product.get('reviewRating', 0))

            logger.info(f"Root ID: {root_id}. Запрос отзывов...")

            # 2. Запрашиваем отзывы
            # Используем feedbacks1.wb.ru (или feedbacks2)
            feed_url = f"https://feedbacks1.wb.ru/feedbacks/v1/{root_id}"
            feed_data = self._get_json_from_browser(driver, feed_url)
            
            # Если 1-й шард не ответил, пробуем 2-й (резерв)
            if not feed_data:
                logger.info("Шард 1 пуст, пробуем feedbacks2...")
                feed_url = f"https://feedbacks2.wb.ru/feedbacks/v1/{root_id}"
                feed_data = self._get_json_from_browser(driver, feed_url)

            if not feed_data:
                raise Exception("API отзывов не вернул данные")

            raw_feedbacks = feed_data.get('feedbacks', [])
            if not raw_feedbacks:
                 logger.info("У товара нет отзывов.")
            
            # Сортировка: Сначала берем отзывы с текстом
            reviews_data = []
            for f in raw_feedbacks:
                txt = f.get('text', '').strip()
                if txt:
                    reviews_data.append({
                        "text": txt,
                        "rating": f.get('productValuation', 5)
                    })
                if len(reviews_data) >= limit: break

            logger.info(f"Успешно собрано {len(reviews_data)} отзывов")
            
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