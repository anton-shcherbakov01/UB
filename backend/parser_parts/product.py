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

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | [%(name)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ProductParser")
logging.getLogger('WDM').setLevel(logging.ERROR)

# Константы для Geo Tracking
GEO_ZONES = {
    "moscow": "-1257786",
    "spb": "-1257262",
    "kazan": "-1255942",
    "krasnodar": "-1257233",
    "novosibirsk": "-1257493"
}

class ProductParser:
    """
    Восстановленная логика парсинга Wildberries (Legacy/Stable).
    Использует перебор корзин для поиска card.json и Selenium для цен.
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
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        ]

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
        
        # Приоритет: расчетный хост, затем популярные, затем все остальные
        hosts_priority = [calc_host] + [f"{i:02d}" for i in range(1, 20)] + [f"{i:02d}" for i in range(20, 51)]
        hosts = list(dict.fromkeys(hosts_priority)) 

        async with aiohttp.ClientSession() as session:
            # Батчинг запросов по 15 штук
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

    # --- МЕТОДЫ ДЛЯ API / ROUTER ---

    async def get_review_stats(self, sku: int):
        """
        Метод для 'Check' этапа на фронтенде. 
        Возвращает метаданные и РЕАЛЬНОЕ кол-во отзывов из card.json.
        """
        logger.info(f"--- CHECK STATS SKU: {sku} ---")
        try:
            card_data = await self._find_card_json(sku)
            if not card_data: 
                return {"status": "error", "message": "Товар не найден (card.json not found)"}
            
            # Извлекаем кол-во отзывов
            feedbacks_count = card_data.get('feedbacks') or card_data.get('feedbackCount') or 0
            
            # Формируем URL изображения
            image_url = card_data.get('image_url')
            if not image_url:
                host = card_data.get('host', '01')
                vol = sku // 100000
                part = sku // 1000
                image_url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"
            
            return {
                "sku": sku,
                "name": card_data.get('imt_name') or card_data.get('subj_name', f"Товар {sku}"),
                "image": image_url,
                "total_reviews": feedbacks_count, # Это значение пойдет в Max ползунка
                "status": "success"
            }
        except Exception as e:
            logger.error(f"get_review_stats error for SKU {sku}: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def get_product_data(self, sku: int):
        """Парсинг цен (оставлен для совместимости с task)"""
        # (Код парсинга цен Selenium, идентичный вашему, для краткости опущен, 
        # но так как я должен вернуть полный файл - вставляю полную версию из вашего примера)
        logger.info(f"--- ПАРСИНГ ЦЕН SKU: {sku} ---")
        static_info = {"name": f"Товар {sku}", "brand": "WB", "image": ""}
        total_qty = 0

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
                    for s in stocks: total_qty += s.get('qty', 0)
        except Exception as e:
            logger.warning(f"Static fail: {e}")

        for attempt in range(1, 4):
            driver = None
            try:
                driver = self._init_driver()
                url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP"
                driver.get(url)
                time.sleep(15) 
                driver.execute_script("window.scrollTo(0, 400);")
                try:
                    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".price-block__wallet-price, .price-block__final-price, [class*='walletPrice']")))
                except: pass

                try:
                    p_json = driver.execute_script("return window.staticModel ? JSON.stringify(window.staticModel) : null;")
                    if p_json:
                        d = json.loads(p_json)
                        price = d.get('price') or (d['products'][0] if 'products' in d else {})
                        wallet = int(price.get('clientPriceU', 0)/100) or int(price.get('totalPrice', 0)/100)
                        if wallet > 0:
                            return {
                                "id": sku, "name": static_info["name"], "brand": static_info["brand"],
                                "image": static_info["image"], "stock_qty": total_qty,
                                "prices": {"wallet_purple": wallet, "standard_black": int(price.get('salePriceU',0)/100), "base_crossed": int(price.get('priceU',0)/100)},
                                "status": "success"
                            }
                except: pass
                wallet = self._extract_price(driver, ".price-block__wallet-price, [class*='walletPrice']")
                standard = self._extract_price(driver, ".price-block__final-price, [class*='priceBlockFinal']")
                base = self._extract_price(driver, ".price-block__old-price, [class*='priceBlockOld']")
                if wallet == 0 and standard > 0: wallet = standard
                if wallet > 0:
                    return {"id": sku, "name": static_info["name"], "brand": static_info["brand"], "image": static_info["image"], "stock_qty": total_qty, "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base}, "status": "success"}
            except Exception as e:
                logger.error(f"Price attempt {attempt} error: {e}")
            finally:
                if driver: driver.quit()
        return {"id": sku, "status": "error", "message": "Failed to parse prices after retries"}

    def get_full_product_info(self, sku: int, limit: int = 50):
        """
        Основной метод парсинга отзывов.
        Восстановлен из вашего файла.
        """
        logger.info(f"--- АНАЛИЗ ОТЗЫВОВ SKU: {sku} (Limit: {limit}) ---")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            static_data = loop.run_until_complete(self._find_card_json(sku))
            loop.close()

            if not static_data: return {"status": "error", "message": "Card not found"}
            root_id = static_data.get('root') or static_data.get('root_id') or static_data.get('imt_id')
            if not root_id: return {"status": "error", "message": "Root ID not found"}

            # Эндпоинты из старого файла
            endpoints = [
                f"https://feedbacks1.wb.ru/feedbacks/v1/{root_id}",
                f"https://feedbacks2.wb.ru/feedbacks/v1/{root_id}",
                f"https://feedbacks-api.wildberries.ru/api/v1/feedbacks?isAnswered=false&take={limit}&skip=0&nmId={sku}&imtId={root_id}"
            ]
            
            feed_data = None
            headers = {"User-Agent": random.choice(self.user_agents)}
            
            for url in endpoints:
                try:
                    r = requests.get(url, headers=headers, timeout=10)
                    if r.status_code == 200:
                        feed_data = r.json()
                        break
                except: continue
            
            if not feed_data: return {"status": "error", "message": "API отзывов недоступен"}

            raw_feedbacks = feed_data.get('feedbacks') or feed_data.get('data', {}).get('feedbacks') or []
            valuation = feed_data.get('valuation') or feed_data.get('data', {}).get('valuation', 0)
            
            reviews = []
            for f in raw_feedbacks:
                txt = f.get('text', '')
                if txt:
                    reviews.append({"text": txt, "rating": f.get('productValuation', 5)})
                if len(reviews) >= limit: break
            
            return {
                "sku": sku,
                "image": static_data.get('image_url'),
                "rating": float(valuation),
                "reviews": reviews,
                "reviews_count": len(reviews),
                "status": "success"
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def get_seo_data(self, sku: int):
            """
            Master SEO Extraction: Собирает семантическое ядро из карточки.
            Источники: Заголовок, Категория, Характеристики (выборочно), Описание.
            """
            logger.info(f"--- 💎 SEO MASTER PARSE SKU: {sku} ---")
            
            # 1. Базовые стоп-слова, которые не являются поисковыми запросами
            STOP_WORDS = {
                'нет', 'да', 'отсутствует', 'без рисунка', 'китай', 'россия', 'узбекистан', 
                'турция', 'корея', 'вид', 'тип', 'для', 'на', 'из', 'от', 'и', 'в', 'с', 'по', 
                'комплектация', 'описание', 'габариты', 'вес', 'упаковка', 'шт', 'г', 'кг', 'мл',
                'товар', 'изделие', 'объем', 'размер', 'рост'
            }

            # 2. Поля характеристик, которые реально содержат ключи (LSI)
            TARGET_PARAMS = {
                'назначение', 'рисунок', 'фактура', 'декоративные элементы', 
                'особенности модели', 'вид застежки', 'тип рукава', 'вырез горловины', 
                'любимые герои', 'стиль', 'сезон', 'пол'
            }

            try:
                # Получаем сырой JSON (предполагаем, что этот метод у вас есть)
                card_data = await self._find_card_json(sku)
                if not card_data: 
                    return {"status": "error", "message": "Card not found"}

                semantic_core = set()

                # --- A. ЗАГОЛОВОК И КАТЕГОРИЯ (High Priority) ---
                # На WB сейчас заголовок часто собирается из Name + Params, но если есть imt_name - берем его
                name = str(card_data.get('imt_name') or card_data.get('subj_name') or '').strip()
                subj = str(card_data.get('subj_name') or '').strip()

                if name: 
                    # Добавляем целиком и по словам
                    semantic_core.add(name.lower())
                    semantic_core.update(re.split(r'[\s,/-]+', name.lower()))
                
                if subj:
                    semantic_core.add(subj.lower())

                # --- B. ОБРАБОТКА ХАРАКТЕРИСТИК (Smart Specs) ---
                options = card_data.get('options', [])
                if not options:
                    # Фолбэк на grouped_options, если структура поменялась
                    grouped = card_data.get('grouped_options', [])
                    for group in grouped:
                        if group.get('options'): options.extend(group.get('options'))

                for opt in options:
                    param_name = str(opt.get('name', '')).lower()
                    val = str(opt.get('value', '')).strip().lower()

                    if not val or val in STOP_WORDS: continue

                    # Логика для состава (убираем проценты и лишние слова)
                    if 'состав' in param_name:
                        # "хлопок 95%, лайкра 5%" -> "хлопок", "лайкра"
                        materials = re.split(r'[,;]', val)
                        for mat in materials:
                            # Удаляем цифры и знаки %
                            clean_mat = re.sub(r'[\d%]', '', mat).strip()
                            if len(clean_mat) > 2: semantic_core.add(clean_mat)
                        continue

                    # Логика для целевых SEO-полей
                    if param_name in TARGET_PARAMS or any(p in param_name for p in ['назначение', 'особенност', 'декор']):
                        parts = re.split(r'[,;/]', val)
                        for p in parts:
                            p_clean = p.strip()
                            if len(p_clean) > 2 and p_clean not in STOP_WORDS:
                                semantic_core.add(p_clean)

                # --- C. ОПИСАНИЕ (Rich Keywords) ---
                # Описание - кладезь низкочастотных запросов. Вытаскиваем существительные и фразы.
                description = str(card_data.get('description', '')).lower()
                if description:
                    # Убираем HTML, если есть (грубая очистка)
                    description = re.sub(r'<[^>]+>', ' ', description)
                    # Убираем спецсимволы
                    description = re.sub(r'[^\w\s-]', ' ', description)
                    
                    words = description.split()
                    # Фильтруем совсем короткие слова и стоп-слова
                    valid_words = [w for w in words if len(w) > 3 and w not in STOP_WORDS]
                    # Добавляем в ядро (можно ограничить топ-50 уникальных слов из описания, чтобы не засорять)
                    semantic_core.update(valid_words[:50])

                # --- ФИНАЛЬНАЯ ЧИСТКА И РАНЖИРОВАНИЕ ---
                final_keywords = []
                seen_stems = set()

                # Сортируем: сначала фразы (они ценнее), потом одиночные слова
                sorted_candidates = sorted(list(semantic_core), key=lambda x: (len(x.split()), len(x)), reverse=True)

                for kw in sorted_candidates:
                    # Базовая очистка
                    clean_kw = re.sub(r'[^\w\s-]', '', kw).strip()
                    if not clean_kw or len(clean_kw) < 3: continue
                    if clean_kw in STOP_WORDS: continue
                    
                    # Простая дедупликация (чтобы не было "платье" и "платья" - грубый стемминг корня)
                    # Для идеального SEO тут нужен Pymorphy2, но сделаем "light" версию без тяжелых либ
                    root = clean_kw[:-1] if len(clean_kw) > 4 else clean_kw
                    
                    if root not in seen_stems:
                        final_keywords.append(clean_kw)
                        seen_stems.add(root)
                        seen_stems.add(clean_kw) # на всякий случай

                return {
                    "sku": sku,
                    "name": name,
                    "brand": card_data.get('selling', {}).get('brand_name', ''), # Полезно для SEO
                    "image": card_data.get('image_url') or card_data.get('img'),
                    # Возвращаем топ-40 самых жирных ключей
                    "keywords": final_keywords[:40],
                    "total_keys_found": len(final_keywords),
                    "status": "success"
                }

            except Exception as e:
                logger.error(f"SEO Master Parse Error: {e}")
                return {"status": "error", "message": str(e)}