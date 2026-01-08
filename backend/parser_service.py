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

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | [%(name)s] %(message)s', handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("WB-Parser")
logging.getLogger('WDM').setLevel(logging.ERROR)

class SeleniumWBParser:
    """
    Микросервис парсинга Wildberries.
    Цены: Selenium (Старая надежная версия).
    Отзывы: API (Вдохновлено WBClient).
    """
    def __init__(self):
        self.headless = os.getenv("HEADLESS", "True").lower() == "true"
        self.proxy_user = os.getenv("PROXY_USER")
        self.proxy_pass = os.getenv("PROXY_PASS")
        self.proxy_host = os.getenv("PROXY_HOST")
        self.proxy_port = os.getenv("PROXY_PORT")

    # --- ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ (API) ---
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
        """Получение данных из card.json (нужен для rootId и бренда)"""
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
        except Exception as e:
            logger.warning(f"Static API Warning: {e}")
        return None

    # --- SELENIUM SETUP ---
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
        
        # --- ФЛАГИ ДЛЯ DOCKER (ОБЯЗАТЕЛЬНО) ---
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-dev-shm-usage")
        edge_options.add_argument("--disable-gpu")
        # -------------------------------------

        plugin_path = self._create_proxy_auth_extension(self.proxy_user, self.proxy_pass, self.proxy_host, self.proxy_port)
        edge_options.add_extension(plugin_path)
        
        edge_options.add_argument("--log-level=3")
        edge_options.add_argument("--disable-blink-features=AutomationControlled")
        edge_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
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

    def get_product_data(self, sku: int):
        """
        Парсинг цен (Твой старый рабочий код + фиксы для Docker).
        """
        logger.info(f"--- АНАЛИЗ ЦЕН SKU: {sku} ---")
        max_attempts = 2
        
        # Получаем бренд/название из статики (чтобы не падать, если селекторы сломались)
        static_data = self._get_static_card_data(sku)
        brand = static_data.get('selling', {}).get('brand_name') if static_data else "Unknown"
        name = static_data.get('imt_name') or static_data.get('subj_name') if static_data else f"Товар {sku}"

        for attempt in range(1, max_attempts + 1):
            driver = None
            try:
                driver = self._init_driver()
                
                # Заходим на главную для куки (Москва)
                driver.get("https://www.wildberries.ru/")
                driver.add_cookie({"name": "x-city-id", "value": "77"}) 
                
                # Открываем карточку
                url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP&dest=-1257786"
                logger.info(f"Load: {url}")
                driver.get(url)
                
                # Проверка Касперского
                if "Kaspersky" in driver.page_source or "Остановлен переход" in driver.title:
                    logger.warning("Kaspersky Block. Retry...")
                    driver.quit(); continue

                # Ожидание (твоя старая логика)
                start_wait = time.time()
                found = False
                while time.time() - start_wait < 60:
                    if driver.find_elements(By.CSS_SELECTOR, "[class*='priceBlockFinalPrice']"): 
                        found = True; break
                    time.sleep(2)

                # Селекторы из твоего старого кода
                wallet = self._extract_price(driver, "[class*='productLinePriceWallet'], [class*='priceBlockWalletPrice']")
                standard = self._extract_price(driver, "[class*='productLinePriceNow'], [class*='priceBlockFinalPrice']")
                base = self._extract_price(driver, "[class*='productLinePriceOld'], [class*='priceBlockOldPrice']")

                # Твой JS-сканер (Fallback)
                if not standard and not wallet:
                    logger.info("Selenium selectors failed. Running JS Scanner...")
                    fallback_script = """
                    let results = [];
                    document.querySelectorAll('*').forEach(el => {
                        let text = el.innerText || el.textContent;
                        if (text && /\\d/.test(text) && text.length < 30) {
                            let d = text.replace(/[^\\d]/g, '');
                            if (d.length >= 3 && d.length <= 6) results.push(parseInt(d));
                        }
                    });
                    return results;
                    """
                    all_nums = driver.execute_script(fallback_script)
                    if all_nums:
                        clean_nums = sorted(list(set([n for n in all_nums if n > 400])))
                        logger.info(f"JS Found: {clean_nums}")
                        if clean_nums:
                            wallet = clean_nums[0]
                            base = clean_nums[-1]
                            standard = clean_nums[1] if len(clean_nums) > 2 else clean_nums[0]

                if not wallet and not standard:
                    raise Exception("Prices not found")

                logger.info(f"Success: {wallet}₽")
                return {
                    "id": sku, "name": name, "brand": brand,
                    "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                    "status": "success"
                }

            except Exception as e:
                logger.error(f"Attempt {attempt} Error: {e}")
                continue
            finally:
                if driver: driver.quit()

        return {"id": sku, "status": "error", "message": "Failed to parse prices"}

    def get_full_product_info(self, sku: int, limit: int = 50):
        """
        Сбор отзывов.
        1. Берем rootId из статического card.json (без браузера).
        2. Качаем отзывы через официальный feedbacks-api (requests).
        """
        logger.info(f"--- АНАЛИЗ ОТЗЫВОВ SKU: {sku} ---")
        try:
            # 1. Получаем rootId и картинку
            static_data = self._get_static_card_data(sku)
            if not static_data: 
                raise Exception("Не удалось получить данные о товаре (card.json)")
            
            root_id = static_data.get('root_id') or static_data.get('root') or static_data.get('imt_id')
            if not root_id: raise Exception("Root ID не найден")
            
            img_url = static_data.get('image_url', '')

            # 2. Качаем отзывы через API (как в WBClient)
            logger.info(f"Root ID: {root_id}. Запрос к API...")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Origin": "https://www.wildberries.ru",
                "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            }
            
            # Используем тот же endpoint, что и в твоем примере
            url = f"https://feedbacks-api.wildberries.ru/api/v1/feedbacks?isAnswered=false&take={limit}&skip=0&nmId={sku}&imtId={root_id}"
            
            resp = requests.get(url, headers=headers, timeout=15)
            
            # Если основной API не сработал, пробуем зеркала
            if resp.status_code != 200:
                logger.warning(f"Feedbacks API Error {resp.status_code}. Trying backup...")
                url = f"https://feedbacks1.wb.ru/feedbacks/v1/{root_id}"
                resp = requests.get(url, headers=headers, timeout=15)

            if resp.status_code != 200:
                raise Exception(f"API отзывов недоступен (Код {resp.status_code})")

            data = resp.json()
            feedbacks = data.get('feedbacks') or data.get('data', {}).get('feedbacks', [])
            
            reviews_data = []
            for f in feedbacks:
                txt = f.get('text', '').strip()
                rating = f.get('productValuation', 5)
                if txt:
                    reviews_data.append({"text": txt, "rating": rating})

            rating_val = float(data.get('valuation', 0))

            logger.info(f"Собрано {len(reviews_data)} отзывов")
            
            return {
                "sku": sku,
                "image": img_url,
                "rating": rating_val,
                "reviews": reviews_data,
                "reviews_count": len(reviews_data),
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Reviews Error: {e}")
            return {"status": "error", "message": str(e)}

parser_service = SeleniumWBParser()