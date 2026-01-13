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
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | [%(name)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("WB-Parser")
logging.getLogger('WDM').setLevel(logging.ERROR)

# Константы для Geo Tracking
GEO_ZONES = {
    "moscow": "-1257786",
    "spb": "-1257262",
    "kazan": "-1255942",
    "krasnodar": "-1257233",
    "novosibirsk": "-1257493"
}

class SeleniumWBParser:
    """
    Микросервис парсинга Wildberries v14.5.
    - [UPD] Переход на API search.wb.ru для трекинга позиций (вместо Selenium).
    - [NEW] Geo Tracking (поддержка параметра dest).
    - [NEW] Разделение Органической и Рекламной выдачи.
    - [UPD] Поддержка пагинации отзывов (Parse All).
    """
    def __init__(self):
        self.headless = os.getenv("HEADLESS", "True").lower() == "true"
        self.proxy_user = os.getenv("PROXY_USER")
        self.proxy_pass = os.getenv("PROXY_PASS")
        self.proxy_host = os.getenv("PROXY_HOST")
        self.proxy_port = os.getenv("PROXY_PORT")
        
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        ]

    def _get_aiohttp_proxy(self, rotate: bool = False) -> Optional[str]:
        """
        Формирует строку прокси для aiohttp.
        Если rotate=True, добавляет session-ID к юзернейму (для резистентных прокси).
        """
        if self.proxy_host and self.proxy_port:
            if self.proxy_user and self.proxy_pass:
                user = self.proxy_user
                if rotate:
                    # Генерируем случайную сессию для ротации IP
                    session_id = ''.join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=8))
                    user = f"{user}-session-{session_id}"
                return f"http://{user}:{self.proxy_pass}@{self.proxy_host}:{self.proxy_port}"
            return f"http://{self.proxy_host}:{self.proxy_port}"
        return None

    # --- ЛОГИКА ПОИСКА КОРЗИН (Legacy/Core) ---
    
    def _calc_basket_static(self, sku: int) -> str:
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

    async def _find_card_json(self, sku: int):
        """Поиск card.json brute-force методом (до 50 корзины)"""
        vol = sku // 100000
        part = sku // 1000
        
        calc_host = self._calc_basket_static(sku)
        
        hosts_priority = [calc_host] + [f"{i:02d}" for i in range(18, 51)] + [f"{i:02d}" for i in range(1, 18)]
        hosts = list(dict.fromkeys(hosts_priority)) 

        async with aiohttp.ClientSession() as session:
            for i in range(0, len(hosts), 15):
                batch = hosts[i:i+15]
                tasks = []
                for host in batch:
                    url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
                    tasks.append(self._check_url(session, url, host))
                
                results = await asyncio.gather(*tasks)
                for res in results:
                    if res: return res
        return None

    async def _check_url(self, session, url, host):
        try:
            async with session.get(url, timeout=1.5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    vol = url.split('vol')[1].split('/')[0]
                    part = url.split('part')[1].split('/')[0]
                    sku = url.split('/')[5]
                    data['image_url'] = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"
                    return data
        except: pass
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
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-dev-shm-usage")
        edge_options.add_argument("--disable-gpu")
        edge_options.add_argument("--disable-blink-features=AutomationControlled")
        
        if self.proxy_host:
            plugin_path = self._create_proxy_auth_extension(self.proxy_user, self.proxy_pass, self.proxy_host, self.proxy_port)
            edge_options.add_extension(plugin_path)
            
        edge_options.add_argument("--window-size=1920,1080")
        ua = random.choice(self.user_agents)
        edge_options.add_argument(f"user-agent={ua}")
        
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
            for el in elements:
                text = el.get_attribute('textContent')
                if not text: continue
                text = text.replace('\xa0', '').replace('&nbsp;', '').replace(' ', '').replace('₽', '')
                digits = re.sub(r'[^\d]', '', text)
                if digits: return int(digits)
        except: pass
        return 0

    # --- MAIN METHODS ---

    async def get_product_meta(self, sku: int) -> Dict[str, Any]:
        """
        Быстрое получение метаданных товара (кол-во отзывов, имя, фото).
        Используется для превью перед анализом.
        """
        card_data = await self._find_card_json(sku)
        if not card_data:
            return {"status": "error", "message": "Товар не найден"}

        return {
            "status": "success",
            "sku": sku,
            "name": card_data.get('imt_name') or card_data.get('subj_name'),
            "image": card_data.get('image_url'),
            "feedbacks_count": card_data.get('feedbacks', 0),
            "rating": card_data.get('valuation', 0)
        }

    def get_product_data(self, sku: int):
        logger.info(f"--- ПАРСИНГ ЦЕН SKU: {sku} ---")
        
        static_info = {"name": f"Товар {sku}", "brand": "WB", "image": ""}
        total_qty = 0

        # 1. Получаем статику + ОСТАТКИ из card.json
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(self._find_card_json(sku))
            loop.close()
            
            if data:
                static_info["name"] = data.get('imt_name') or data.get('subj_name')
                static_info["brand"] = data.get('selling', {}).get('brand_name')
                static_info["image"] = data.get('image_url')
                
                sizes = data.get('sizes', [])
                for size in sizes:
                    stocks = size.get('stocks', [])
                    for s in stocks:
                        total_qty += s.get('qty', 0)
        except Exception as e:
            logger.warning(f"Static fail: {e}")

        # 2. Парсим цены (Selenium)
        for attempt in range(1, 4):
            driver = None
            try:
                driver = self._init_driver()
                url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP"
                driver.get(url)
                time.sleep(15) 
                driver.execute_script("window.scrollTo(0, 400);")
                
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".price-block__wallet-price, .price-block__final-price, [class*='walletPrice']"))
                    )
                except:
                    logger.warning(f"Wait timeout for price selector attempt {attempt}")

                try:
                    p_json = driver.execute_script("return window.staticModel ? JSON.stringify(window.staticModel) : null;")
                    if p_json:
                        d = json.loads(p_json)
                        price = d.get('price') or (d['products'][0] if 'products' in d else {})
                        wallet = int(price.get('clientPriceU', 0)/100) or int(price.get('totalPrice', 0)/100)
                        
                        if wallet > 0:
                            if total_qty == 0:
                                try:
                                    sizes = d.get('sizes', [])
                                    for size in sizes:
                                        stocks = size.get('stocks', [])
                                        for s in stocks:
                                            total_qty += s.get('qty', 0)
                                except: pass

                            return {
                                "id": sku, 
                                "name": static_info["name"], 
                                "brand": static_info["brand"],
                                "image": static_info["image"],
                                "stock_qty": total_qty,
                                "prices": {"wallet_purple": wallet, "standard_black": int(price.get('salePriceU',0)/100), "base_crossed": int(price.get('priceU',0)/100)},
                                "status": "success"
                            }
                except: pass

                wallet = self._extract_price(driver, ".price-block__wallet-price, [class*='walletPrice']")
                standard = self._extract_price(driver, ".price-block__final-price, [class*='priceBlockFinal']")
                base = self._extract_price(driver, ".price-block__old-price, [class*='priceBlockOld']")

                if wallet == 0 and standard > 0: wallet = standard
                if wallet > 0:
                    return {
                        "id": sku, 
                        "name": static_info["name"], 
                        "brand": static_info["brand"],
                        "image": static_info["image"],
                        "stock_qty": total_qty, 
                        "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                        "status": "success"
                    }
                else:
                    logger.warning(f"Prices not found in DOM attempt {attempt}")

            except Exception as e:
                logger.error(f"Price attempt {attempt} error: {e}")
            finally:
                if driver: driver.quit()
        
        return {"id": sku, "status": "error", "message": "Failed to parse prices after retries"}

    def get_full_product_info(self, sku: int, limit: int = 100):
        logger.info(f"--- АНАЛИЗ ОТЗЫВОВ SKU: {sku} (Limit: {limit}) ---")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            static_data = loop.run_until_complete(self._find_card_json(sku))
            loop.close()

            if not static_data: return {"status": "error", "message": "Card not found"}
            root_id = static_data.get('root') or static_data.get('root_id') or static_data.get('imt_id')
            if not root_id: return {"status": "error", "message": "Root ID not found"}

            all_reviews = []
            
            # Если лимит маленький (<100), используем стандартные эндпоинты статики
            # Если лимит большой, используем пагинацию через API v1
            
            headers = {"User-Agent": random.choice(self.user_agents)}
            
            # Стратегия: идем по пагинации пока не соберем limit
            fetched = 0
            batch_size = 100 # WB отдает по 100
            
            while fetched < limit:
                take = min(batch_size, limit - fetched)
                url = f"https://feedbacks-api.wildberries.ru/api/v1/feedbacks?isAnswered=false&take={take}&skip={fetched}&nmId={sku}&imtId={root_id}"
                
                try:
                    r = requests.get(url, headers=headers, timeout=10)
                    if r.status_code != 200:
                        logger.warning(f"Review fetch error {r.status_code} at skip {fetched}")
                        break
                        
                    data = r.json()
                    feedbacks = data.get('feedbacks') or data.get('data', {}).get('feedbacks') or []
                    
                    if not feedbacks:
                        break # Больше нет отзывов
                    
                    for f in feedbacks:
                        txt = f.get('text', '')
                        if txt:
                            all_reviews.append({"text": txt, "rating": f.get('productValuation', 5)})
                    
                    fetched += len(feedbacks)
                    
                    # Если вернулось меньше чем просили, значит это конец
                    if len(feedbacks) < take:
                        break
                        
                    time.sleep(0.5) # Вежливость
                    
                except Exception as e:
                    logger.error(f"Review iteration error: {e}")
                    break
            
            valuation = static_data.get('valuation') or 0
            
            return {
                "sku": sku,
                "name": static_data.get('imt_name') or static_data.get('subj_name'),
                "image": static_data.get('image_url'),
                "rating": float(valuation),
                "reviews": all_reviews,
                "reviews_count": len(all_reviews),
                "status": "success"
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def get_seo_data(self, sku: int):
        logger.info(f"--- SEO PARSE SKU: {sku} ---")
        try:
            card_data = await self._find_card_json(sku)
            if not card_data: return {"status": "error", "message": "Card not found"}

            keywords = []
            name = card_data.get('imt_name') or card_data.get('subj_name')
            if name: keywords.append(name)
            subj = card_data.get('subj_name')
            if subj and subj != name: keywords.append(subj)
            
            options = card_data.get('options', [])
            if not options:
                grouped = card_data.get('grouped_options', [])
                for group in grouped:
                    if group.get('options'):
                        options.extend(group.get('options'))

            stop_values = ['нет', 'да', 'отсутствует', 'без рисунка', 'китай', 'россия', '0', '1', '2', '3']
            
            for opt in options:
                val = str(opt.get('value', '')).strip()
                name_param = str(opt.get('name', '')).lower()
                
                if not val: continue
                if val.lower() in stop_values: continue
                if len(val) < 2: continue 
                if val.isdigit() and "год" not in name_param: continue
                
                if "состав" in name_param or "назначение" in name_param or "рисунок" in name_param or "фактура" in name_param:
                    parts = re.split(r'[,/]', val)
                    for p in parts:
                        keywords.append(p.strip())
                else:
                    keywords.append(val)

            clean_keywords = []
            seen = set()
            for k in keywords:
                k_clean = re.sub(r'[^\w\s-]', '', k).strip()
                if k_clean and k_clean.lower() not in seen:
                    seen.add(k_clean.lower())
                    clean_keywords.append(k_clean)

            return {
                "sku": sku,
                "name": name,
                "image": card_data.get('image_url'),
                "keywords": clean_keywords[:40],
                "status": "success"
            }
        except Exception as e:
            logger.error(f"SEO Parse Error: {e}")
            return {"status": "error", "message": str(e)}

    # --- ADVANCED GEO SEARCH (HYBRID: API + SELENIUM FALLBACK) ---

    async def get_search_position_selenium_fallback(self, query: str, target_sku: int):
        """
        Медленный, но надежный метод через Selenium (если API заблокирован).
        """
        logger.info(f"⚡ FALLBACK: Starting Selenium Search for '{query}'...")
        driver = None
        try:
            # Запускаем в отдельном потоке, так как Selenium синхронный
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._run_selenium_search_sync, query, target_sku)
        except Exception as e:
            logger.error(f"Selenium Fallback Error: {e}")
            return {"organic_pos": 0, "ad_pos": 0, "is_boosted": False}

    def _run_selenium_search_sync(self, query: str, target_sku: int):
        driver = None
        try:
            driver = self._init_driver()
            # Прямой URL поиска
            url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}"
            driver.get(url)
            
            # Ждем загрузки карточек
            try:
                WebDriverWait(driver, 25).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".product-card, .product-card__wrapper"))
                )
                time.sleep(3) # Небольшая пауза для рендеринга JS
            except:
                logger.warning("Selenium: Timeout waiting for cards")
                return {"organic_pos": 0, "ad_pos": 0, "is_boosted": False}

            # Парсим DOM
            cards = driver.find_elements(By.CSS_SELECTOR, ".product-card__wrapper, .product-card")
            
            organic_counter = 0
            for i, card in enumerate(cards):
                try:
                    # Пытаемся найти ID
                    link = card.find_element(By.TAG_NAME, "a")
                    href = link.get_attribute("href")
                    
                    # Извлекаем ID из ссылки (catalog/12345/detail)
                    match = re.search(r'catalog/(\d+)/detail', href)
                    if not match: continue
                    
                    sku_found = int(match.group(1))
                    
                    # Проверяем на рекламу (метка "Реклама" или класс)
                    text_content = card.get_attribute("textContent").lower()
                    is_ad = "реклама" in text_content
                    
                    if not is_ad:
                        organic_counter += 1
                        
                    if sku_found == int(target_sku):
                        logger.info(f"✅ Selenium Found SKU {target_sku} at pos {i+1}")
                        return {
                            "organic_pos": organic_counter if not is_ad else 0,
                            "ad_pos": (i + 1) if is_ad else 0,
                            "is_boosted": is_ad,
                            "total_pos": i + 1
                        }
                    
                    # Ограничиваем глубину (топ 100)
                    if i > 100: break
                    
                except Exception as inner_e:
                    continue

            return {"organic_pos": 0, "ad_pos": 0, "is_boosted": False}
            
        except Exception as e:
            logger.error(f"Selenium Sync Error: {e}")
            return {"organic_pos": 0, "ad_pos": 0, "is_boosted": False}
        finally:
            if driver:
                try: driver.quit()
                except: pass

    async def get_search_position_v2(self, query: str, target_sku: int, dest: str = GEO_ZONES["moscow"]):
        """
        Гибридный поиск: API (с ротацией прокси) -> если Fail/429 -> Selenium
        """
        target_sku = int(target_sku)
        url = "https://search.wb.ru/exactmatch/ru/common/v7/search"
        params = {"ab_testing": "false", "appType": "1", "curr": "rub", "dest": dest, "query": query, "resultset": "catalog", "sort": "popular", "spp": "30", "suppressSpellcheck": "false"}
        
        # 1. Попытка через API (быстро)
        max_retries = 3
        api_failed = False
        
        for attempt in range(max_retries):
            # Включаем ротацию IP для каждого запроса
            proxy_url = self._get_aiohttp_proxy(rotate=True)
            headers = {"User-Agent": random.choice(self.user_agents), "Accept": "*/*"}
            
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, headers=headers, proxy=proxy_url, timeout=12) as resp:
                        
                        if resp.status == 429:
                            logger.warning(f"API 429 (Att {attempt+1}).")
                            await asyncio.sleep(random.uniform(2, 4))
                            continue
                            
                        if resp.status != 200:
                            logger.warning(f"API Bad Status {resp.status}. Switching to fallback.")
                            api_failed = True
                            break
                        
                        data = await resp.json()
                        products = data.get("data", {}).get("products") or data.get("products", [])
                        
                        if not products:
                            # Пустой ответ API часто означает бот-блок
                            logger.warning("API returned empty products list. Switching to Fallback.")
                            api_failed = True
                            break

                        organic_counter = 0
                        
                        for index, item in enumerate(products):
                            item_id = int(item.get("id", 0))
                            is_ad = bool(item.get("log") or item.get("adId") or item.get("cpm"))
                            
                            if not is_ad: organic_counter += 1
                            
                            if item_id == target_sku:
                                return {
                                    "organic_pos": organic_counter if not is_ad else 0,
                                    "ad_pos": (index + 1) if is_ad else 0,
                                    "is_boosted": is_ad,
                                    "total_pos": index + 1
                                }
                        
                        return {"organic_pos": 0, "ad_pos": 0, "is_boosted": False}

            except Exception as e:
                logger.error(f"API Connection Error: {e}")
                await asyncio.sleep(1)
                continue
        
        logger.info("API attempts exhausted or failed. Executing Selenium Fallback.")
        return await self.get_search_position_selenium_fallback(query, target_sku)

    def get_search_position(self, query: str, target_sku: int):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.get_search_position_v2(query, target_sku))
            loop.close()
            return result["organic_pos"] if result["organic_pos"] > 0 else (result["ad_pos"] if result["ad_pos"] > 0 else 0)
        except Exception as e:
            logger.error(f"Legacy Search Error: {e}")
            return 0

parser_service = SeleniumWBParser()