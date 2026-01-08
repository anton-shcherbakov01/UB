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

# Загрузка настроек из .env
load_dotenv()

# Настройка расширенного логирования для отображения в docker logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | [%(name)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("WB-Parser")

class SeleniumWBParser:
    """
    Микросервис парсинга Wildberries. 
    Версия адаптирована для работы в Docker с детальным логированием и глубоким сканированием.
    """
    def __init__(self):
        self.headless = os.getenv("HEADLESS", "True").lower() == "true"
        self.proxy_user = os.getenv("PROXY_USER")
        self.proxy_pass = os.getenv("PROXY_PASS")
        self.proxy_host = os.getenv("PROXY_HOST")
        self.proxy_port = os.getenv("PROXY_PORT")
        logger.info("Инициализация сервиса парсинга завершена")

    def _create_proxy_auth_extension(self, user, pw, host, port):
        """Создает расширение для авторизации прокси с уникальной сессией."""
        logger.info(f"Создание расширения прокси для {host}:{port}")
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
        try:
            with zipfile.ZipFile(extension_path, 'w') as zp:
                zp.writestr("manifest.json", manifest_json)
                zp.writestr("background.js", background_js)
            logger.info("Файл расширения прокси успешно создан")
        except Exception as e:
            logger.error(f"Ошибка при создании архива расширения: {e}")
        return extension_path

    def _init_driver(self):
        """Инициализация драйвера с использованием локального пути в Docker."""
        logger.info("Запуск инициализации Selenium драйвера...")
        edge_options = EdgeOptions()
        if self.headless:
            edge_options.add_argument("--headless=new")
        
        # Обязательные флаги для стабильной работы в Docker
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-dev-shm-usage")
        edge_options.add_argument("--disable-gpu")
        
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
            # Путь берется из Dockerfile
            driver_bin = '/usr/local/bin/msedgedriver'
            service = EdgeService(executable_path=driver_bin)
            driver = webdriver.Edge(service=service, options=edge_options)
            logger.info("Драйвер Selenium успешно запущен")
        except Exception as e:
            logger.error(f"Критическая ошибка инициализации драйвера: {e}")
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
                    logger.info(f"Извлечена цена по селектору '{selector}': {val}")
                return val
        except Exception as e:
            logger.debug(f"Не удалось извлечь цену по селектору '{selector}': {e}")
            return 0
        return 0

    def get_product_data(self, sku: int):
        """Основной метод парсинга с ретраями и глубоким поиском."""
        logger.info(f"--- ЗАПРОС НА АНАЛИЗ SKU: {sku} ---")
        max_attempts = 3
        last_error = ""

        # Актуальные селекторы WB
        sel = {
            "wallet": ".price-block__wallet-price, [class*='WalletPrice'], .product-line__price-wallet",
            "final": "ins.price-block__final-price, .price-block__final-price, [class*='FinalPrice']",
            "old": "del.price-block__old-price, .price-block__old-price, [class*='OldPrice']",
            "brand": ".product-page__header-brand, .product-page__brand, span.brand, .product-page__brand-name",
            "name": ".product-page__header-title, h1.product-page__title, .product-page__name"
        }

        for attempt in range(1, max_attempts + 1):
            driver = None
            try:
                logger.info(f"Попытка {attempt}/{max_attempts}...")
                driver = self._init_driver()
                
                # Установка региона Москва (x-city-id: 77)
                driver.get("https://www.wildberries.ru/")
                driver.add_cookie({"name": "x-city-id", "value": "77"})
                
                # Параметр dest=-1257786 гарантирует московскую выдачу
                url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP&dest=-1257786"
                logger.info(f"Загрузка страницы: {url}")
                driver.get(url)
                
                # Ожидание загрузки (проверка блокировок)
                if "Kaspersky" in driver.page_source or "Остановлен переход" in driver.title:
                    logger.warning("Блокировка. Смена сессии...")
                    driver.quit(); continue

                # Даем время на ленивую загрузку
                time.sleep(3)
                driver.execute_script("window.scrollTo(0, 500);")
                
                # Ожидание появления контента
                try:
                    WebDriverWait(driver, 25).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".product-page__price-block, .price-block"))
                    )
                except:
                    logger.warning("Контейнер цены не появился вовремя.")

                # Извлечение цен через селекторы
                wallet = self._extract_price(driver, sel["wallet"])
                standard = self._extract_price(driver, sel["final"])
                base = self._extract_price(driver, sel["old"])

                # Глубокий JS-сканер, если селекторы не сработали
                if not standard and not wallet:
                    logger.info("Стандартные селекторы не сработали. Запуск JS-сканера...")
                    js_prices = driver.execute_script("""
                        let res = [];
                        document.querySelectorAll('.price-block__content, [class*="price"]').forEach(el => {
                            let t = el.innerText || el.textContent;
                            let m = t.match(/\\d[\\d\\s]{2,}/g);
                            if (m) m.forEach(val => {
                                let n = parseInt(val.replace(/\\s/g, ''));
                                if (n > 100 && n < 1000000) res.push(n);
                            });
                        });
                        return [...new Set(res)].sort((a,b) => a-b);
                    """)
                    if js_prices:
                        logger.info(f"JS-сканер нашел: {js_prices}")
                        wallet = js_prices[0]
                        standard = js_prices[1] if len(js_prices) > 1 else js_prices[0]
                        base = js_prices[-1] if len(js_prices) > 2 else 0

                # Если цен нет — ошибка
                if not wallet and not standard:
                    raise Exception("Цены не обнаружены на странице.")

                # Безопасное извлечение бренда и названия
                brand = "Не определен"
                name = f"Товар {sku}"
                
                for b_sel in sel["brand"].split(','):
                    els = driver.find_elements(By.CSS_SELECTOR, b_sel.strip())
                    if els:
                        brand = els[0].text.strip(); break
                
                for n_sel in sel["name"].split(','):
                    els = driver.find_elements(By.CSS_SELECTOR, n_sel.strip())
                    if els:
                        name = els[0].text.strip(); break

                logger.info(f"Успешно спарсено: {brand} | {name} | Wallet: {wallet}")
                return {
                    "id": sku, "name": name, "brand": brand,
                    "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                    "status": "success"
                }

            except Exception as e:
                last_error = str(e)
                logger.error(f"Ошибка на попытке {attempt}: {last_error}")
                continue
            finally:
                if driver: 
                    driver.quit()

        return {"id": sku, "status": "error", "message": f"Ошибка парсинга: {last_error}"}

parser_service = SeleniumWBParser()