import os
import time
import random
import logging
import zipfile
import json
import re
import sys
import uuid
import shutil
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from webdriver_manager.microsoft import EdgeChromiumDriverManager

# Загрузка настроек из .env
load_dotenv()

# Настройка расширенного логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | [%(name)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("WB-Parser")

class SeleniumWBParser:
    def __init__(self):
        self.headless = os.getenv("HEADLESS", "True").lower() == "true"
        self.proxy_user = os.getenv("PROXY_USER")
        self.proxy_pass = os.getenv("PROXY_PASS")
        self.proxy_host = os.getenv("PROXY_HOST")
        self.proxy_port = os.getenv("PROXY_PORT")
        # Создаем общую папку для временных расширений, если её нет
        self.proxy_base_path = "proxy_exts"
        if not os.path.exists(self.proxy_base_path):
            os.makedirs(self.proxy_base_path)
        logger.info("Инициализация сервиса парсинга завершена (Parallel Ready)")

    def _create_proxy_auth_extension(self, user, pw, host, port):
        """Создает УНИКАЛЬНОЕ расширение для каждой сессии во избежание конфликтов."""
        unique_id = str(uuid.uuid4())[:8]
        extension_path = os.path.join(self.proxy_base_path, f"proxy_auth_{unique_id}.zip")
        
        manifest_json = json.dumps({
            "version": "1.0.0", "manifest_version": 2, "name": f"Edge Proxy {unique_id}",
            "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"],
            "background": {"scripts": ["background.js"]}
        })
        
        session_id = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=10))
        auth_user = f"{user}-session-{session_id};country-ru"
        
        background_js = """
        var config = { mode: "fixed_servers", rules: { singleProxy: { scheme: "http", host: "%s", port: parseInt(%s) }, bypassList: ["localhost"] } };
        chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
        chrome.webRequest.onAuthRequired.addListener(function(details) {
            return { authCredentials: { username: "%s", password: "%s" } };
        }, {urls: ["<all_urls>"]}, ['blocking']);
        """ % (host, port, auth_user, pw)

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
        
        # Создаем расширение и сохраняем путь для последующего удаления
        plugin_path = self._create_proxy_auth_extension(self.proxy_user, self.proxy_pass, self.proxy_host, self.proxy_port)
        edge_options.add_extension(plugin_path)
        
        edge_options.add_argument("--window-size=1920,1080")
        edge_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        try:
            os.environ['WDM_LOG_LEVEL'] = '0'
            system_driver = '/usr/local/bin/msedgedriver'
            if os.path.exists(system_driver): 
                service = EdgeService(executable_path=system_driver)
            else: 
                service = EdgeService(EdgeChromiumDriverManager().install())
            
            driver = webdriver.Edge(service=service, options=edge_options)
            driver.set_page_load_timeout(120)
            return driver, plugin_path
        except Exception as e:
            # Если не удалось запустить, пытаемся удалить файл плагина
            if os.path.exists(plugin_path): os.remove(plugin_path)
            logger.error(f"Ошибка Selenium: {e}")
            raise e

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
        logger.info(f"--- АНАЛИЗ SKU: {sku} ---")
        max_attempts = 3
        last_error = ""
        price_selectors = ["[class*='productLinePriceWallet']", "[class*='priceBlockWalletPrice']", "[class*='productLinePriceNow']", "[class*='priceBlockFinalPrice']"]

        for attempt in range(1, max_attempts + 1):
            driver = None
            plugin_file = None
            try:
                logger.info(f"Попытка {attempt}/{max_attempts} (SKU {sku})...")
                driver, plugin_file = self._init_driver()
                driver.get(f"https://www.wildberries.ru/catalog/{sku}/detail.aspx")
                
                time.sleep(3)
                driver.execute_script("window.scrollTo(0, 400);")
                
                if "Kaspersky" in driver.page_source or "Остановлен переход" in driver.title:
                    driver.quit()
                    if plugin_file and os.path.exists(plugin_file): os.remove(plugin_file)
                    continue

                logger.info(f"Ожидание цен для {sku}...")
                found = False
                start_wait = time.time()
                while time.time() - start_wait < 60:
                    if any(driver.find_elements(By.CSS_SELECTOR, s) for s in price_selectors):
                        found = True; break
                    time.sleep(2)

                wallet = self._extract_price(driver, "[class*='productLinePriceWallet'], [class*='priceBlockWalletPrice']")
                standard = self._extract_price(driver, "[class*='productLinePriceNow'], [class*='priceBlockFinalPrice']")
                base = self._extract_price(driver, "[class*='productLinePriceOld'], [class*='priceBlockOldPrice']")

                if not standard and not wallet:
                    logger.info(f"Запуск JS-сканера для {sku}...")
                    all_nums = driver.execute_script("let res = []; document.querySelectorAll('*').forEach(el => { let t = el.innerText; if (t && /\\d/.test(t) && t.length < 30) { let d = t.replace(/[^\\d]/g, ''); if (d.length >= 3 && d.length <= 6) res.push(parseInt(d)); } }); return res;")
                    if all_nums:
                        clean = sorted(list(set([n for n in all_nums if n > 400])))
                        if clean:
                            wallet = clean[0]
                            standard = clean[1] if len(clean) > 1 else clean[0]
                            base = clean[-1]

                if not wallet and not standard:
                    raise Exception("Цены не обнаружены")

                brand_els = driver.find_elements(By.CLASS_NAME, "product-page__header-brand")
                name_els = driver.find_elements(By.CLASS_NAME, "product-page__header-title")
                brand = brand_els[0].text.strip() if brand_els else "Не определен"
                name = name_els[0].text.strip() if name_els else f"Товар {sku}"

                logger.info(f"Успешно спарсено: {sku} | {wallet}₽")
                return {
                    "id": sku, "name": name, "brand": brand,
                    "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                    "status": "success"
                }
            except Exception as e:
                last_error = str(e)
                logger.error(f"Ошибка {attempt} для {sku}: {last_error}")
                continue
            finally:
                if driver: driver.quit()
                if plugin_file and os.path.exists(plugin_file):
                    try: os.remove(plugin_file)
                    except: pass

        return {"id": sku, "status": "error", "message": last_error}

parser_service = SeleniumWBParser()