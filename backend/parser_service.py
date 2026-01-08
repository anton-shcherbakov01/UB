import os
import time
import random
import logging
import zipfile
import json
import re
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By

# Загрузка настроек из .env
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

class SeleniumWBParser:
    """
    Микросервис парсинга Wildberries. 
    РАБОТАЕТ БЕЗ ИНТЕРНЕТА (использует локальный драйвер сервера).
    """
    def __init__(self):
        self.headless = os.getenv("HEADLESS", "True").lower() == "true"
        self.proxy_user = os.getenv("PROXY_USER")
        self.proxy_pass = os.getenv("PROXY_PASS")
        self.proxy_host = os.getenv("PROXY_HOST")
        self.proxy_port = os.getenv("PROXY_PORT")

    def _create_proxy_auth_extension(self, user, pw, host, port):
        folder_path = "proxy_ext"
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        
        manifest_json = json.dumps({
            "version": "1.0.0", "manifest_version": 2, "name": "Edge Proxy",
            "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"],
            "background": {"scripts": ["background.js"]}
        })
        
        session_id = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=10))
        auth_user = f"{user}-session-{session_id};country-ru"

        background_js = """
        var config = { 
            mode: "fixed_servers", 
            rules: { singleProxy: { scheme: "http", host: "%s", port: parseInt(%s) }, bypassList: ["localhost"] } 
        };
        chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});
        chrome.webRequest.onAuthRequired.addListener(function(details) {
            return { authCredentials: { username: "%s", password: "%s" } };
        }, {urls: ["<all_urls>"]}, ['blocking']);
        """ % (host, port, auth_user, pw)

        extension_path = os.path.join(folder_path, "proxy_auth_plugin.zip")
        with zipfile.ZipFile(extension_path, 'w') as zp:
            zp.writestr("manifest.json", manifest_json)
            zp.writestr("background.js", background_js)
        return extension_path

    def _init_driver(self):
        edge_options = EdgeOptions()
        
        # Флаги для стабильной работы в Docker
        edge_options.add_argument("--headless=new")
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-dev-shm-usage")
        edge_options.add_argument("--disable-gpu")
        edge_options.add_argument("--remote-debugging-port=9222")
        
        plugin_path = self._create_proxy_auth_extension(
            self.proxy_user, self.proxy_pass, self.proxy_host, self.proxy_port
        )
        edge_options.add_extension(plugin_path)
        
        edge_options.add_argument("--log-level=3")
        edge_options.add_argument("--disable-blink-features=AutomationControlled")
        edge_options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        edge_options.add_argument("--window-size=1920,1080")
        edge_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        try:
            # ПРЯМОЙ ПУТЬ К ДРАЙВЕРУ (установленному в Dockerfile)
            service = EdgeService(executable_path='/usr/local/bin/msedgedriver')
            driver = webdriver.Edge(service=service, options=edge_options)
        except Exception as e:
            logging.error(f"Ошибка инициализации драйвера: {e}")
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
        except:
            return 0
        return 0

    def get_product_data(self, sku: int):
        max_attempts = 3
        price_selectors_list = [
            "[class*='productLinePriceWallet']", "[class*='priceBlockWalletPrice']",
            "[class*='productLinePriceNow']", "[class*='priceBlockFinalPrice']"
        ]

        for attempt in range(1, max_attempts + 1):
            driver = None
            try:
                logging.info(f"--- Попытка {attempt}/{max_attempts} | SKU: {sku} ---")
                driver = self._init_driver()
                driver.get(f"https://www.wildberries.ru/catalog/{sku}/detail.aspx")
                
                if "Kaspersky" in driver.page_source or "Остановлен переход" in driver.title:
                    logging.warning("Блокировка. Смена IP...")
                    driver.quit(); continue

                start_wait = time.time()
                while time.time() - start_wait < 45:
                    if any(driver.find_elements(By.CSS_SELECTOR, s) for s in price_selectors_list): break
                    time.sleep(2)

                brand = driver.find_element(By.CLASS_NAME, "product-page__header-brand").text
                name = driver.find_element(By.CLASS_NAME, "product-page__header-title").text
                
                return {
                    "id": sku, "name": name, "brand": brand,
                    "prices": {
                        "wallet_purple": self._extract_price(driver, "[class*='priceBlockWalletPrice']"),
                        "standard_black": self._extract_price(driver, "[class*='priceBlockFinalPrice']"),
                        "base_crossed": self._extract_price(driver, "[class*='priceBlockOldPrice']")
                    },
                    "status": "success"
                }
            except Exception as e:
                logging.error(f"Ошибка: {e}")
                continue
            finally:
                if driver: driver.quit()

        return {"id": sku, "status": "error", "message": "Браузер на сервере не смог загрузить данные."}

parser_service = SeleniumWBParser()