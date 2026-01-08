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

load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | [%(name)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("WB-Parser")
logging.getLogger('WDM').setLevel(logging.ERROR)

class SeleniumWBParser:
    """
    Микросервис парсинга Wildberries v3.0.
    Гибридный метод: DOM-сканирование + извлечение JSON-данных из скриптов страницы.
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
        edge_options.add_argument("--lang=ru-RU")
        
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
            
        driver.set_page_load_timeout(90)
        return driver

    def _try_extract_json_from_page(self, driver):
        """Пытается найти JSON с данными товара в исходном коде страницы (самый надежный метод)."""
        try:
            # WB часто хранит состояние в window.__INITIAL_STATE__ или похожих объектах
            data = driver.execute_script("return window.__INITIAL_STATE__ || window.__NUXT__ || null;")
            if not data: return None
            
            # Пытаемся найти продукт в этой структуре (структура меняется, ищем рекурсивно или по ключам)
            # Это упрощенный пример, нужно адаптировать под текущую структуру WB
            # Обычно это data.product или data.card
            return data
        except:
            return None

    def _extract_digits(self, text):
        if not text: return 0
        text = text.replace('&nbsp;', '').replace(u'\xa0', '')
        digits = re.sub(r'[^\d]', '', text)
        return int(digits) if digits else 0

    def get_product_data(self, sku: int):
        logger.info(f"--- АНАЛИЗ ЦЕН SKU: {sku} ---")
        max_attempts = 2
        
        for attempt in range(1, max_attempts + 1):
            driver = None
            try:
                driver = self._init_driver()
                
                # 1. Установка региона (Москва)
                driver.get("https://www.wildberries.ru/")
                driver.add_cookie({"name": "x-city-id", "value": "77"}) 
                
                url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP&dest=-1257786"
                logger.info(f"Попытка {attempt}: {url}")
                driver.get(url)
                
                # 2. Проверка антибота
                if "Kaspersky" in driver.page_source or "Остановлен переход" in driver.title:
                    logger.warning("Блокировка. Рестарт...")
                    driver.quit(); continue

                # 3. Ожидание и скролл
                time.sleep(3)
                driver.execute_script("window.scrollTo(0, 400);")
                
                # Ждем любой ценник
                try:
                    WebDriverWait(driver, 30).until(
                        lambda d: d.find_elements(By.CSS_SELECTOR, "[class*='price'], .price-block__content")
                    )
                except:
                    logger.warning("Элементы цен долго не появляются.")

                # 4. Сбор данных (Гибридный метод)
                wallet = 0
                standard = 0
                base = 0
                
                # Попытка 1: Через селекторы (визуальные)
                try:
                    wallet_el = driver.find_elements(By.CSS_SELECTOR, ".price-block__wallet-price, [class*='WalletPrice']")
                    final_el = driver.find_elements(By.CSS_SELECTOR, ".price-block__final-price, [class*='FinalPrice'], .price-block__price-now")
                    old_el = driver.find_elements(By.CSS_SELECTOR, ".price-block__old-price, [class*='OldPrice'], .price-block__price-old")
                    
                    if wallet_el: wallet = self._extract_digits(wallet_el[0].text)
                    if final_el: standard = self._extract_digits(final_el[0].text)
                    if old_el: base = self._extract_digits(old_el[0].text)
                except Exception as e:
                    logger.error(f"Selector parsing error: {e}")

                # Попытка 2: Если селекторы не сработали - Глубокий JS скан
                if standard == 0:
                    logger.info("Селекторы пусты. Запуск JS-сканера...")
                    js_prices = driver.execute_script("""
                        let res = [];
                        // Ищем в блоке цен
                        document.querySelectorAll('.price-block__content, .product-page__price-block').forEach(el => {
                            let txt = el.innerText;
                            let matches = txt.match(/\\d[\\d\\s]{1,10}/g);
                            if (matches) matches.forEach(m => res.push(parseInt(m.replace(/\\s/g, ''))));
                        });
                        // Если пусто, ищем по всей странице (осторожно)
                        if (res.length === 0) {
                            document.querySelectorAll('*').forEach(el => {
                                if (el.children.length === 0 && el.innerText.includes('₽')) {
                                    let d = el.innerText.replace(/[^0-9]/g, '');
                                    if (d.length > 2 && d.length < 8) res.push(parseInt(d));
                                }
                            });
                        }
                        return [...new Set(res)].sort((a,b) => a-b);
                    """)
                    
                    if js_prices:
                        valid_prices = [p for p in js_prices if p > 50] # Фильтр мусора
                        if valid_prices:
                            logger.info(f"JS нашел: {valid_prices}")
                            wallet = valid_prices[0]
                            standard = valid_prices[1] if len(valid_prices) > 1 else valid_prices[0]
                            base = valid_prices[-1] if len(valid_prices) > 1 else 0

                if wallet == 0: wallet = standard
                if standard == 0: raise Exception("Цена не найдена")

                # Бренд и название
                brand = "Не определен"
                name = f"Товар {sku}"
                try:
                    b_els = driver.find_elements(By.CSS_SELECTOR, ".product-page__header-brand, .brand-name")
                    if b_els: brand = b_els[0].text.strip()
                    n_els = driver.find_elements(By.CSS_SELECTOR, "h1, .product-page__title")
                    if n_els: name = n_els[0].text.strip()
                except: pass

                logger.info(f"Успех: {brand} | {wallet}₽")
                return {
                    "id": sku, "name": name, "brand": brand,
                    "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                    "status": "success"
                }

            except Exception as e:
                logger.error(f"Ошибка попытки {attempt}: {e}")
                continue
            finally:
                if driver: driver.quit()

        return {"id": sku, "status": "error", "message": "Не удалось определить цену. Попробуйте позже."}

    def get_full_product_info(self, sku: int, limit: int = 50):
        """
        Сбор данных для ИИ. Парсинг отзывов через DOM (без API-инъекций).
        """
        logger.info(f"--- ОТЗЫВЫ SKU: {sku} ---")
        driver = None
        try:
            driver = self._init_driver()
            # Идем сразу в отзывы
            url = f"https://www.wildberries.ru/catalog/{sku}/feedbacks?targetUrl=GP&dest=-1257786"
            driver.get(url)
            
            time.sleep(5)
            if "Kaspersky" in driver.page_source: raise Exception("Blocked")

            # Агрессивный скроллинг для подгрузки отзывов
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5)

            # Статика
            img_url = ""
            try:
                img = driver.find_elements(By.CSS_SELECTOR, "img.photo-container__photo")
                if img: img_url = img[0].get_attribute("src")
            except: pass

            rating = 0.0
            try:
                rate = driver.find_elements(By.CSS_SELECTOR, ".product-review__rating")
                if rate: rating = float(rate[0].text.strip())
            except: pass

            # Сбор отзывов из HTML
            reviews_data = []
            # Используем самые широкие селекторы для карточек отзывов
            cards = driver.find_elements(By.CSS_SELECTOR, "li.comments__item, div.feedback__item")
            
            logger.info(f"Найдено карточек: {len(cards)}")
            
            for card in cards[:limit]:
                try:
                    # Ищем текст
                    text_els = card.find_elements(By.CSS_SELECTOR, ".comments__text, .feedback__text")
                    if not text_els: continue
                    text = text_els[0].text.strip()
                    
                    # Ищем звезды (класс star--active)
                    stars = len(card.find_elements(By.CSS_SELECTOR, ".star.star--active"))
                    if stars == 0: stars = 5 # Дефолт, если звезды не распарсились
                    
                    if len(text) > 5:
                        reviews_data.append({"text": text, "rating": stars})
                except: continue

            if not reviews_data:
                raise Exception("Отзывы не прогрузились или отсутствуют")

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
            return {"status": "error", "message": "Не удалось собрать отзывы"}
        finally:
            if driver: driver.quit()

parser_service = SeleniumWBParser()