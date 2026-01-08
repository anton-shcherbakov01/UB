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
from webdriver_manager.microsoft import EdgeChromiumDriverManager

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
    Оптимизирован для работы внутри Docker с балансом между стабильностью и скоростью ответа.
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
        """Инициализация драйвера с настройками для Docker."""
        logger.info("Запуск инициализации Selenium драйвера...")
        edge_options = EdgeOptions()
        if self.headless:
            edge_options.add_argument("--headless=new")
        
        # --- КРИТИЧЕСКИЕ ПРАВКИ ДЛЯ DOCKER ---
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-dev-shm-usage")
        edge_options.add_argument("--disable-gpu")
        # -------------------------------------------------------------------
        
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
            os.environ['WDM_LOG_LEVEL'] = '0'
            system_driver = '/usr/local/bin/msedgedriver'
            if os.path.exists(system_driver):
                service = EdgeService(executable_path=system_driver)
            else:
                service = EdgeService(EdgeChromiumDriverManager().install())
            
            driver = webdriver.Edge(service=service, options=edge_options)
            logger.info("Драйвер Selenium успешно запущен")
        except Exception as e:
            logger.error(f"Ошибка инициализации драйвера: {e}")
            raise e
            
        # Устанавливаем разумный таймаут загрузки страницы (45 сек), 
        # чтобы успеть ответить фронтенду до обрыва связи (60 сек).
        driver.set_page_load_timeout(45)
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
        """Основной метод парсинга с ограничением по времени для предотвращения таймаутов HTTP."""
        logger.info(f"--- ЗАПРОС НА АНАЛИЗ SKU: {sku} ---")
        # Сокращаем количество попыток до 2, чтобы уложиться в лимит ожидания клиента (60-90 сек)
        max_attempts = 2
        last_error = ""

        price_selectors_list = [
            "[class*='productLinePriceWallet']", "[class*='priceBlockWalletPrice']",
            "[class*='productLinePriceNow']", "[class*='priceBlockFinalPrice']"
        ]

        for attempt in range(1, max_attempts + 1):
            driver = None
            try:
                logger.info(f"Попытка {attempt}/{max_attempts}...")
                driver = self._init_driver()
                url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
                
                logger.info(f"Загрузка страницы: {url}")
                driver.get(url)
                
                # Сокращаем паузы
                time.sleep(2)
                driver.execute_script("window.scrollTo(0, 400);")
                
                # Проверка на блокировки
                page_title = driver.title
                if "Kaspersky" in driver.page_source or "Остановлен переход" in page_title:
                    logger.warning(f"Попытка {attempt}: Обнаружена блокировка. Смена сессии...")
                    driver.quit()
                    continue

                logger.info("Ожидание появления цен...")
                
                # Сокращаем время ожидания появления элементов до 30 секунд
                found = False
                start_wait = time.time()
                while time.time() - start_wait < 30:
                    if any(driver.find_elements(By.CSS_SELECTOR, s) for s in price_selectors_list):
                        found = True
                        break
                    time.sleep(1)

                if found:
                    logger.info(f"Цены обнаружены через {int(time.time() - start_wait)} сек.")
                else:
                    logger.warning("Цены не появились за отведенное время.")

                wallet = self._extract_price(driver, "[class*='productLinePriceWallet'], [class*='priceBlockWalletPrice']")
                standard = self._extract_price(driver, "[class*='productLinePriceNow'], [class*='priceBlockFinalPrice']")
                base = self._extract_price(driver, "[class*='productLinePriceOld'], [class*='priceBlockOldPrice']")

                # Глубокий сканер (если стандартные классы не сработали)
                if not standard and not wallet:
                    logger.info("Стандартные классы цен не сработали. Запуск JS-сканера...")
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
                        logger.info(f"JS-сканер нашел числа: {clean_nums}")
                        if clean_nums:
                            wallet = clean_nums[0]
                            base = clean_nums[-1]
                            standard = clean_nums[1] if len(clean_nums) > 2 else clean_nums[0]

                if not wallet and not standard:
                    logger.error("Парсинг не удался: цены не обнаружены даже глубоким сканером.")
                    raise Exception("Цены не обнаружены.")

                logger.info("Извлечение информации о бренде и названии...")
                
                # Используем find_elements, чтобы не падать с ошибкой, если WB изменил классы
                brand_els = driver.find_elements(By.CLASS_NAME, "product-page__header-brand")
                name_els = driver.find_elements(By.CLASS_NAME, "product-page__header-title")
                
                brand = brand_els[0].text.strip() if brand_els else "Не определен"
                name = name_els[0].text.strip() if name_els else f"Товар {sku}"

                logger.info(f"Успешно спарсено: {brand} | {name} | Wallet: {wallet}")
                return {
                    "id": sku, "name": name, "brand": brand,
                    "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                    "status": "success"
                }

            except Exception as e:
                last_error = str(e)
                logger.error(f"Ошибка во время попытки {attempt}: {last_error}")
                # Если первая попытка заняла слишком много времени, сразу выходим, чтобы успеть ответить клиенту
                if attempt == 1 and (time.time() - start_wait) > 40:
                    break
                continue
            finally:
                if driver: 
                    logger.info("Закрытие драйвера")
                    driver.quit()

        logger.error(f"Финальная ошибка: {last_error}")
        return {"id": sku, "status": "error", "message": f"Ошибка на сервере: {last_error}"}

parser_service = SeleniumWBParser()