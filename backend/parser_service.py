import os
import time
import random
import logging
import json
import re
import sys
import requests
import asyncio
import aiohttp
import zipfile
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By

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
    Микросервис парсинга Wildberries v11.0.
    - Асинхронный Brute-force поиск корзин (поддержка новых SKU > 4000 vol).
    - Гибридный парсинг (API для статики/отзывов, Selenium для цен).
    """
    def __init__(self):
        self.headless = os.getenv("HEADLESS", "True").lower() == "true"
        self.proxy_user = os.getenv("PROXY_USER")
        self.proxy_pass = os.getenv("PROXY_PASS")
        self.proxy_host = os.getenv("PROXY_HOST")
        self.proxy_port = os.getenv("PROXY_PORT")

    # --- ЛОГИКА ПОИСКА КОРЗИН И JSON ---

    async def _check_basket_url(self, session, host, vol, part, sku):
        """Проверка одного хоста корзины"""
        url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
        try:
            async with session.get(url, timeout=2.0) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Формируем ссылку на фото
                    data['image_url'] = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"
                    data['host'] = host # Запоминаем рабочий хост
                    return data
        except:
            return None
        return None

    async def _find_card_json(self, sku: int):
        """
        Ищет card.json. Параллельно проверяет все возможные корзины.
        Это решает проблему с новыми артикулами (например 474906054).
        """
        vol = sku // 100000
        part = sku // 1000
        
        # Список хостов для проверки (от 01 до 25 и спец. хосты)
        # Приоритет: новые хосты (15-25), затем старые (01-14)
        hosts = [f"{i:02d}" for i in range(1, 26)]
        
        # Сортируем: сначала вероятные для больших vol (15+), потом остальные
        hosts.sort(key=lambda x: int(x) < 13) 

        async with aiohttp.ClientSession() as session:
            tasks = [self._check_basket_url(session, host, vol, part, sku) for host in hosts]
            
            # Ждем завершения первой успешной задачи (as_completed не совсем то, используем gather и фильтр)
            # Для скорости используем gather, так как таймаут маленький (2с)
            results = await asyncio.gather(*tasks)
            
            for res in results:
                if res:
                    return res
                    
        return None

    # --- SELENIUM SETUP ---
    def _create_proxy_auth_extension(self, user, pw, host, port):
        folder_path = "proxy_ext"
        if not os.path.exists(folder_path): os.makedirs(folder_path)
        
        manifest_json = json.dumps({
            "version": "1.0.0", 
            "manifest_version": 2, 
            "name": "Edge Proxy", 
            "permissions": ["proxy", "tabs", "unlimitedStorage", "storage", "<all_urls>", "webRequest", "webRequestBlocking"], 
            "background": {"scripts": ["background.js"]}
        })
        
        session_id = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=10))
        # Ротация сессии для обхода защиты
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
        if self.headless: 
            edge_options.add_argument("--headless=new")
        
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-dev-shm-usage")
        edge_options.add_argument("--disable-gpu")
        edge_options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Proxy setup
        if self.proxy_host and self.proxy_user:
            plugin_path = self._create_proxy_auth_extension(self.proxy_user, self.proxy_pass, self.proxy_host, self.proxy_port)
            edge_options.add_extension(plugin_path)
            
        edge_options.add_argument("--window-size=1920,1080")
        edge_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
        
        try:
            # Путь к драйверу внутри Docker контейнера
            driver_bin = '/usr/local/bin/msedgedriver'
            service = EdgeService(executable_path=driver_bin)
            driver = webdriver.Edge(service=service, options=edge_options)
        except Exception as e:
            logger.error(f"Driver Init Error: {e}")
            raise e
            
        driver.set_page_load_timeout(90)
        return driver

    def _extract_price(self, driver, selector):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                text = el.get_attribute('textContent') or el.text
                if not text: continue
                # Чистим текст от nbsp и прочего
                text = text.replace('\xa0', '').replace('&nbsp;', '').replace(' ', '')
                digits = re.sub(r'[^\d]', '', text)
                if digits:
                    return int(digits)
        except:
            pass
        return 0

    # --- MAIN METHODS ---

    def get_product_data(self, sku: int):
        """
        Основной метод парсинга цен и статики.
        """
        logger.info(f"--- ПАРСИНГ ЦЕН SKU: {sku} ---")
        
        # 1. Получаем статику через API (асинхронный вызов в синхронном коде)
        static_info = {"name": f"Товар {sku}", "brand": "WB", "image": ""}
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(self._find_card_json(sku))
            loop.close()
            
            if data:
                static_info["name"] = data.get('imt_name') or data.get('subj_name') or static_info["name"]
                static_info["brand"] = data.get('selling', {}).get('brand_name') or static_info["brand"]
                static_info["image"] = data.get('image_url')
                logger.info(f"Статика найдена: {static_info['brand']}")
        except Exception as e:
            logger.warning(f"Static API fail: {e}")

        # 2. Парсим цены через Selenium (так как API цен часто защищено)
        for attempt in range(1, 3):
            driver = None
            try:
                driver = self._init_driver()
                
                # Сначала на главную для куки
                try:
                    driver.get("https://www.wildberries.ru/")
                    driver.add_cookie({"name": "x-city-id", "value": "77"}) # Москва
                except: pass

                url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP"
                driver.get(url)
                
                time.sleep(3)
                driver.execute_script("window.scrollTo(0, 400);")
                
                # Проверка защиты
                if "Kaspersky" in driver.page_source: 
                    logger.warning(f"Kaspersky detected attempt {attempt}")
                    driver.quit()
                    continue

                # Попытка 1: JSON со страницы (самый надежный)
                try:
                    p_json = driver.execute_script("return typeof window.staticModel !== 'undefined' ? JSON.stringify(window.staticModel) : null;")
                    if p_json:
                        d = json.loads(p_json)
                        # Ищем цену в разных местах структуры
                        price_obj = d.get('price') or (d.get('products', [{}])[0])
                        
                        wallet = int(price_obj.get('clientPriceU', 0) / 100) or int(price_obj.get('totalPrice', 0) / 100)
                        standard = int(price_obj.get('salePriceU', 0) / 100)
                        base = int(price_obj.get('priceU', 0) / 100)

                        if wallet > 0:
                            return {
                                "id": sku, 
                                "name": static_info["name"], 
                                "brand": static_info["brand"],
                                "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                                "status": "success"
                            }
                except Exception as e:
                    logger.debug(f"JSON extraction failed: {e}")

                # Попытка 2: DOM селекторы
                wallet = self._extract_price(driver, ".price-block__wallet-price, [class*='walletPrice']")
                standard = self._extract_price(driver, ".price-block__final-price, [class*='priceBlockFinal']")
                base = self._extract_price(driver, ".price-block__old-price, [class*='priceBlockOld']")

                if wallet == 0 and standard > 0: wallet = standard # Если нет кошелька, берем обычную

                if wallet > 0:
                    return {
                        "id": sku, 
                        "name": static_info["name"], 
                        "brand": static_info["brand"],
                        "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                        "status": "success"
                    }
                
                logger.warning(f"Prices not found attempt {attempt}")

            except Exception as e:
                logger.error(f"Selenium Error {attempt}: {e}")
            finally:
                if driver: driver.quit()
                
        return {"id": sku, "status": "error", "message": "Failed to parse prices after retries"}

    def get_full_product_info(self, sku: int, limit: int = 50):
        """
        Сбор отзывов. Исправлено для работы с новым API отзывов.
        """
        logger.info(f"--- АНАЛИЗ ОТЗЫВОВ SKU: {sku} ---")
        try:
            # 1. Сначала ищем card.json чтобы получить root_id (imt_id)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            static_data = loop.run_until_complete(self._find_card_json(sku))
            loop.close()

            if not static_data: 
                return {"status": "error", "message": "Товар не найден (card.json unavailable)"}

            # Извлекаем imt_id (root)
            root_id = static_data.get('imt_id') or static_data.get('root') or static_data.get('root_id')
            if not root_id:
                return {"status": "error", "message": "Не удалось определить Root ID товара"}

            # 2. Запрос к API отзывов
            # Используем актуальный endpoint
            url = f"https://feedbacks-api.wildberries.ru/api/v1/feedbacks?isAnswered=false&take={limit}&skip=0&nmId={sku}&imtId={root_id}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*",
                "Origin": "https://www.wildberries.ru",
                "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            }
            
            resp = requests.get(url, headers=headers, timeout=15)
            
            if resp.status_code != 200:
                logger.error(f"Feedbacks API Error: {resp.status_code} {resp.text}")
                return {"status": "error", "message": "Ошибка API отзывов"}

            feed_json = resp.json()
            feedbacks = feed_json.get('feedbacks', [])
            
            reviews = []
            for f in feedbacks:
                text = f.get('text', '')
                if text:
                    reviews.append({
                        "text": text,
                        "rating": f.get('productValuation', 5)
                    })
            
            return {
                "sku": sku, 
                "image": static_data.get('image_url'),
                "rating": float(feed_json.get('valuation', 0)),
                "reviews": reviews, 
                "reviews_count": feed_json.get('feedbackCount', 0),
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Full info error: {e}")
            return {"status": "error", "message": str(e)}

parser_service = SeleniumWBParser()