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

# Загрузка настроек из .env
load_dotenv()

# Настройка логирования для Docker
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | [%(name)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("WB-Parser")
# Глушим лишний шум от библиотек
logging.getLogger('WDM').setLevel(logging.ERROR)
logging.getLogger('selenium').setLevel(logging.WARNING)

class SeleniumWBParser:
    """
    Микросервис парсинга Wildberries. 
    Оптимизирован для работы внутри Docker с локальным драйвером.
    """
    def __init__(self):
        self.headless = os.getenv("HEADLESS", "True").lower() == "true"
        self.proxy_user = os.getenv("PROXY_USER")
        self.proxy_pass = os.getenv("PROXY_PASS")
        self.proxy_host = os.getenv("PROXY_HOST")
        self.proxy_port = os.getenv("PROXY_PORT")
        logger.info("Инициализация сервиса парсинга завершена")

    def _create_proxy_auth_extension(self, user, pw, host, port):
        """Создает расширение для авторизации прокси."""
        folder_path = "proxy_ext"
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        
        manifest_json = json.dumps({
            "version": "1.0.0", "manifest_version": 2, "name": "Edge Proxy",
            "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"],
            "background": {"scripts": ["background.js"]}
        })
        
        session_id = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=10))
        # Фильтрация по РФ для скорости и правильных цен
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
        try:
            with zipfile.ZipFile(extension_path, 'w') as zp:
                zp.writestr("manifest.json", manifest_json)
                zp.writestr("background.js", background_js)
        except Exception as e:
            logger.error(f"Ошибка создания прокси-плагина: {e}")
        return extension_path

    def _init_driver(self):
        """Инициализация драйвера с использованием локального пути в Docker."""
        edge_options = EdgeOptions()
        if self.headless:
            edge_options.add_argument("--headless=new")
        
        # --- ФЛАГИ ДЛЯ DOCKER (Обязательные) ---
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-dev-shm-usage")
        edge_options.add_argument("--disable-gpu")
        edge_options.add_argument("--remote-debugging-port=9222")
        # ---------------------------------------
        
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
            # Путь берется из Dockerfile: /usr/local/bin/msedgedriver
            # Это обходит проблемы с загрузкой из интернета
            driver_bin = '/usr/local/bin/msedgedriver'
            service = EdgeService(executable_path=driver_bin)
            driver = webdriver.Edge(service=service, options=edge_options)
            logger.info("Драйвер Selenium успешно запущен (локальный)")
        except Exception as e:
            logger.error(f"Ошибка запуска драйвера: {e}")
            raise e
            
        driver.set_page_load_timeout(120)
        return driver

    def _extract_price(self, driver, selector):
        """Надежное извлечение цифр из элемента."""
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            if elements:
                txt = driver.execute_script("return arguments[0].textContent;", elements[0])
                if not txt:
                    txt = driver.execute_script("return arguments[0].innerText;", elements[0])
                digits = re.sub(r'[^\d]', '', txt)
                val = int(digits) if digits else 0
                if val > 0:
                    logger.info(f"Найдена цена ({selector}): {val}")
                return val
        except:
            return 0
        return 0

    def get_product_data(self, sku: int):
        """Основной метод парсинга с ретраями и глубоким поиском."""
        logger.info(f"--- АНАЛИЗ SKU: {sku} ---")
        max_attempts = 3
        last_error = ""

        # Актуальные селекторы WB
        price_selectors_list = [
            "[class*='productLinePriceWallet']", "[class*='priceBlockWalletPrice']",
            "[class*='productLinePriceNow']", "[class*='priceBlockFinalPrice']",
            "[class*='productLinePriceOld']", "[class*='priceBlockOldPrice']"
        ]

        for attempt in range(1, max_attempts + 1):
            driver = None
            try:
                logger.info(f"Попытка {attempt}/{max_attempts}...")
                driver = self._init_driver()
                url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
                
                driver.get(url)
                
                # Проверка на блокировки
                if "Kaspersky" in driver.page_source or "Остановлен переход" in driver.title:
                    logger.warning(f"Попытка {attempt}: Блокировка Касперским. Смена IP...")
                    driver.quit()
                    continue

                # Ожидание загрузки цен
                found = False
                start_wait = time.time()
                while time.time() - start_wait < 60:
                    if any(driver.find_elements(By.CSS_SELECTOR, s) for s in price_selectors_list):
                        found = True
                        break
                    time.sleep(2)
                
                if found:
                    logger.info(f"Элементы цен обнаружены за {int(time.time() - start_wait)}с")

                # Извлечение цен по целевым классам
                wallet = self._extract_price(driver, "[class*='productLinePriceWallet'], [class*='priceBlockWalletPrice']")
                standard = self._extract_price(driver, "[class*='productLinePriceNow'], [class*='priceBlockFinalPrice']")
                base = self._extract_price(driver, "[class*='productLinePriceOld'], [class*='priceBlockOldPrice']")

                # Глубокий сканер (ВАШ КОД)
                if not standard and not wallet:
                    logger.info("Классы не сработали. Запуск глубокого JS-сканера...")
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
                        logger.info(f"JS-сканер нашел: {clean_nums}")
                        if clean_nums:
                            wallet = clean_nums[0]
                            base = clean_nums[-1]
                            standard = clean_nums[1] if len(clean_nums) > 2 else clean_nums[0]

                if not wallet and not standard:
                    raise Exception("Цены не обнаружены на странице.")

                # Данные о товаре (безопасно)
                brand = "Не определен"
                name = f"Товар {sku}"
                try:
                    b_el = driver.find_elements(By.CLASS_NAME, "product-page__header-brand")
                    if b_el: brand = b_el[0].text.strip()
                    n_el = driver.find_elements(By.CLASS_NAME, "product-page__header-title")
                    if n_el: name = n_el[0].text.strip()
                except: pass

                logger.info(f"Успех: {brand} | {name} | {wallet}₽")
                return {
                    "id": sku, "name": name, "brand": brand,
                    "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                    "status": "success",
                    "attempts": attempt
                }

            except Exception as e:
                last_error = str(e)
                logger.error(f"Ошибка на попытке {attempt}: {last_error}")
                continue
            finally:
                if driver: driver.quit()

        return {"id": sku, "status": "error", "message": f"Ошибка парсинга: {last_error}"}

parser_service = SeleniumWBParser()