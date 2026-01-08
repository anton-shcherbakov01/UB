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

# Настройка расширенного логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | [%(name)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("WB-Parser")

class SeleniumWBParser:
    """
    Микросервис парсинга Wildberries v2.5.
    Оптимизирован для Docker. Содержит логику глубокого сканирования и обхода региональных ограничений.
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
        """Инициализация драйвера с критическими флагами для Docker."""
        edge_options = EdgeOptions()
        if self.headless:
            edge_options.add_argument("--headless=new")
        
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-dev-shm-usage")
        edge_options.add_argument("--disable-gpu")
        edge_options.add_argument("--disable-blink-features=AutomationControlled")
        
        plugin_path = self._create_proxy_auth_extension(
            self.proxy_user, self.proxy_pass, self.proxy_host, self.proxy_port
        )
        edge_options.add_extension(plugin_path)
        
        edge_options.add_argument("--window-size=1920,1080")
        edge_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        try:
            driver_bin = '/usr/local/bin/msedgedriver'
            service = EdgeService(executable_path=driver_bin)
            driver = webdriver.Edge(service=service, options=edge_options)
        except Exception as e:
            logger.error(f"Ошибка запуска драйвера: {e}")
            raise e
            
        driver.set_page_load_timeout(120)
        return driver

    def _extract_price(self, driver, selector):
        """Надежное извлечение цифр из элемента через JS."""
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
        logger.info(f"--- АНАЛИЗ SKU: {sku} ---")
        max_attempts = 3
        
        # Актуальные селекторы WB
        sel = {
            "wallet": ".price-block__wallet-price, .product-line__price-wallet, [class*='WalletPrice'], .price-block__price-wallet",
            "final": "ins.price-block__final-price, .price-block__final-price, [class*='FinalPrice'], .price-block__price-now",
            "old": "del.price-block__old-price, .price-block__old-price, [class*='OldPrice'], .price-block__price-old",
            "brand": ".product-page__header-brand, .product-page__brand, span.brand, [data-link*='brandName'], .product-page__brand-name",
            "name": ".product-page__header-title, h1.product-page__title, h1, .product-page__name, .product-page__title"
        }

        for attempt in range(1, max_attempts + 1):
            driver = None
            try:
                driver = self._init_driver()
                
                # Установка региона через куки (Москва)
                driver.get("https://www.wildberries.ru/")
                driver.add_cookie({"name": "x-city-id", "value": "77"}) 
                
                # Формируем URL с привязкой к Москве (dest)
                url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP&dest=-1257786"
                logger.info(f"Попытка {attempt}: Загрузка {url}")
                driver.get(url)
                
                # Проверка блокировок
                if "Kaspersky" in driver.page_source or "Остановлен переход" in driver.title:
                    logger.warning("Обнаружена блокировка. Пробуем сменить сессию...")
                    driver.quit(); continue

                # Ожидание основного контейнера (ждем до 20 сек)
                try:
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".product-page__main-container, #container"))
                    )
                except:
                    logger.warning("Контейнер товара не появился. Скроллим для активации...")
                
                # Скролл для ленивой загрузки
                driver.execute_script("window.scrollTo(0, 400);")
                time.sleep(2)

                # Ждем появления цены
                start_wait = time.time()
                found_price = False
                while time.time() - start_wait < 30:
                    if any(driver.find_elements(By.CSS_SELECTOR, s) for s in [sel["wallet"], sel["final"]]):
                        found_price = True; break
                    time.sleep(2)

                # 1. Извлекаем цены
                wallet = self._extract_price(driver, sel["wallet"])
                final = self._extract_price(driver, sel["final"])
                old = self._extract_price(driver, sel["old"])

                # 2. Если селекторы не сработали — включаем JS-сканер
                if final == 0:
                    logger.info("Селекторы не нашли цену. Запуск глубокого JS-сканера...")
                    js_prices = driver.execute_script("""
                        let prices = [];
                        document.querySelectorAll('.price-block__content, .price-block, [class*="price"]').forEach(el => {
                            let text = el.innerText || el.textContent;
                            let matches = text.match(/\\d[\\d\\s]{2,}/g);
                            if (matches) {
                                matches.forEach(m => {
                                    let v = parseInt(m.replace(/\\s/g, ''));
                                    if (v > 100 && v < 1000000) prices.push(v);
                                });
                            }
                        });
                        return [...new Set(prices)].sort((a,b) => a-b);
                    """)
                    if js_prices:
                        logger.info(f"JS-сканер обнаружил: {js_prices}")
                        wallet = js_prices[0]
                        final = js_prices[1] if len(js_prices) > 1 else js_prices[0]
                        old = js_prices[-1] if len(js_prices) > 2 else 0

                # Валидация: если кошелька нет, он равен основной цене
                if wallet == 0: wallet = final
                if final == 0: raise Exception("Цена не найдена ни одним способом")

                # 3. Извлекаем бренд и название (безопасно)
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

                logger.info(f"Успех: {brand} | {name} | {wallet}₽")
                return {
                    "id": sku, "name": name, "brand": brand,
                    "prices": {"wallet_purple": wallet, "standard_black": final, "base_crossed": old},
                    "status": "success"
                }

            except Exception as e:
                logger.error(f"Ошибка на попытке {attempt}: {e}")
                continue
            finally:
                if driver: driver.quit()

        return {"id": sku, "status": "error", "message": "Не удалось спарсить товар. WB блокирует запрос или страница пуста."}

parser_service = SeleniumWBParser()