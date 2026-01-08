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

# Настройка расширенного логирования
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
    Версия адаптирована для работы в Docker с детальным логированием каждого шага.
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
            driver_bin = '/usr/local/bin/msedgedriver'
            service = EdgeService(executable_path=driver_bin)
            driver = webdriver.Edge(service=service, options=edge_options)
            logger.info("Драйвер Selenium успешно запущен")
        except Exception as e:
            logger.error(f"Критическая ошибка инициализации драйвера: {e}", exc_info=True)
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

        # Расширенный список селекторов (WB часто меняет классы)
        price_selectors_list = [
            ".price-block__wallet-price", ".price-block__final-price",
            "[class*='productLinePriceWallet']", "[class*='priceBlockWalletPrice']",
            "[class*='productLinePriceNow']", "[class*='priceBlockFinalPrice']"
        ]

        brand_selectors = [
            ".product-page__header-brand", ".product-page__brand", 
            "span.brand", "[data-link*='brandName']", ".product-page__brand-name"
        ]

        name_selectors = [
            ".product-page__header-title", "h1.product-page__title",
            "h1", ".product-page__name", ".product-page__title"
        ]

        for attempt in range(1, max_attempts + 1):
            driver = None
            try:
                logger.info(f"Попытка {attempt}/{max_attempts}...")
                driver = self._init_driver()
                url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
                
                logger.info(f"Загрузка страницы: {url}")
                driver.get(url)
                
                # Имитация активности пользователя для подгрузки контента
                time.sleep(3)
                driver.execute_script("window.scrollTo(0, 400);")
                
                page_title = driver.title
                if "Kaspersky" in driver.page_source or "Остановлен переход" in page_title:
                    logger.warning(f"Попытка {attempt}: Обнаружена блокировка. Смена сессии...")
                    driver.quit()
                    continue

                # Проверка, что страница вообще загрузила хоть какой-то контент товара
                if not driver.find_elements(By.CLASS_NAME, "product-page__main-container") and \
                   not driver.find_elements(By.ID, "container"):
                    logger.warning("Контейнер товара не найден. Страница могла не прогрузиться.")

                logger.info("Ожидание появления цен...")
                
                found = False
                start_wait = time.time()
                while time.time() - start_wait < 35:
                    if any(driver.find_elements(By.CSS_SELECTOR, s) for s in price_selectors_list):
                        found = True
                        break
                    time.sleep(2)

                if found:
                    logger.info(f"Цены обнаружены через {int(time.time() - start_wait)} сек.")
                else:
                    logger.warning("Цены не появились за отведенное время через селекторы.")

                # Сбор цен
                wallet = self._extract_price(driver, ".price-block__wallet-price, [class*='productLinePriceWallet'], [class*='priceBlockWalletPrice']")
                standard = self._extract_price(driver, ".price-block__final-price, [class*='productLinePriceNow'], [class*='priceBlockFinalPrice']")
                base = self._extract_price(driver, ".price-block__old-price, [class*='productLinePriceOld'], [class*='priceBlockOldPrice']")

                # Глубокий сканер (если стандартные классы не сработали)
                if not standard and not wallet:
                    logger.info("Запуск JS-сканера (поиск по текстовым шаблонам)...")
                    fallback_script = """
                    let results = [];
                    // Ищем все элементы, содержащие цифры и символ рубля или просто цифры в блоке цены
                    document.querySelectorAll('.price-block__content, .product-page__price-block, .price-block').forEach(block => {
                        let text = block.innerText || block.textContent;
                        let matches = text.match(/\\d[\\d\\s]{2,}/g);
                        if (matches) {
                            matches.forEach(m => {
                                let val = parseInt(m.replace(/\\s/g, ''));
                                if (val > 100 && val < 1000000) results.push(val);
                            });
                        }
                    });
                    // Если ничего не нашли в блоках, ищем вообще везде короткие числа
                    if (results.length === 0) {
                        document.querySelectorAll('*').forEach(el => {
                            if (el.children.length === 0) {
                                let text = el.innerText || el.textContent;
                                if (text && /^\\d[\\d\\s]{2,7}$/.test(text.trim())) {
                                    let val = parseInt(text.replace(/\\s/g, ''));
                                    if (val > 100 && val < 1000000) results.push(val);
                                }
                            }
                        });
                    }
                    return [...new Set(results)];
                    """
                    all_nums = driver.execute_script(fallback_script)
                    if all_nums:
                        # Сортируем: самая маленькая - кошелек, средняя - обычная, большая - зачеркнутая
                        clean_nums = sorted([n for n in all_nums if n > 100])
                        logger.info(f"JS-сканер нашел числа: {clean_nums}")
                        if len(clean_nums) >= 1:
                            wallet = clean_nums[0]
                            standard = clean_nums[1] if len(clean_nums) > 1 else clean_nums[0]
                            base = clean_nums[-1] if len(clean_nums) > 1 else 0

                if not wallet and not standard:
                    logger.error("Парсинг не удался: цены не обнаружены.")
                    raise Exception("Цены не обнаружены.")

                logger.info("Извлечение информации о бренде и названии...")
                brand = "Не определен"
                name = f"Товар {sku}"

                for s in brand_selectors:
                    els = driver.find_elements(By.CSS_SELECTOR, s)
                    if els:
                        brand = els[0].text.strip()
                        break
                
                for s in name_selectors:
                    els = driver.find_elements(By.CSS_SELECTOR, s)
                    if els:
                        name = els[0].text.strip()
                        break

                logger.info(f"Успешно спарсено: {brand} | {name} | Wallet: {wallet}")
                return {
                    "id": sku, "name": name, "brand": brand,
                    "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                    "status": "success"
                }

            except Exception as e:
                last_error = str(e)
                logger.error(f"Ошибка во время попытки {attempt}: {last_error}")
                continue
            finally:
                if driver: 
                    logger.info("Закрытие драйвера")
                    driver.quit()

        logger.error(f"Все попытки исчерпаны. Финальная ошибка: {last_error}")
        return {"id": sku, "status": "error", "message": f"Ошибка на сервере: {last_error}"}

parser_service = SeleniumWBParser()