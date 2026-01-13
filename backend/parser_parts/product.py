import time
import json
import re
import asyncio
import requests
import logging
import urllib3
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .config import logger, get_random_ua
from .basket import BasketFinder
from .browser import BrowserManager

# Отключаем предупреждения SSL, так как WB иногда имеет проблемы с сертификатами при парсинге
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Настраиваем логгер
logger = logging.getLogger("ProductParser")
logger.setLevel(logging.INFO)

class ProductParser:
    def __init__(self):
        self.basket_finder = BasketFinder()
        self.browser_manager = BrowserManager()

    def _get_card_details_direct(self, sku: int):
        """
        Прямой запрос к API карточки (самый быстрый способ).
        """
        try:
            # Универсальный URL для карточки
            url = f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={sku}"
            headers = {
                "User-Agent": get_random_ua(),
                "Accept": "*/*",
                "Origin": "https://www.wildberries.ru",
                "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            }
            # verify=False для надежности в контейнерах
            resp = requests.get(url, headers=headers, timeout=5, verify=False)
            
            if resp.status_code == 200:
                data = resp.json()
                products = data.get('data', {}).get('products', [])
                if products:
                    prod = products[0]
                    return {
                        "root_id": prod.get('root'), 
                        "name": prod.get('name'),
                        "brand": prod.get('brand'),
                        "rating": prod.get('reviewRating'),
                        "feedbacks_count": prod.get('feedbacks'),
                        "image": None # Ссылку на картинку сложно собрать вручную, проще через basket
                    }
        except Exception as e:
            logger.warning(f"Direct API failed for {sku}: {e}")
        return None

    async def _resolve_root_id_and_meta(self, sku: int):
        """
        Внутренний метод для надежного поиска root_id и метаданных.
        Использует сначала API, потом BasketFinder.
        Возвращает dict или None.
        """
        # 1. Попытка через Direct API
        details = self._get_card_details_direct(sku)
        
        # 2. Попытка через BasketFinder (для картинки и если API упал)
        basket_data = None
        try:
            # BasketFinder может быть запущен в event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                 # Мы уже в async контексте
                 basket_data = await self.basket_finder.find_card_json(sku)
            else:
                 # Мы в sync контексте
                 basket_data = await self.basket_finder.find_card_json(sku)
        except Exception as e:
            logger.warning(f"Basket finder check warning: {e}")

        # Собираем итоговый результат
        result = {
            "root_id": None,
            "name": f"Товар {sku}",
            "image": "",
            "total_reviews": 0,
            "rating": 0.0
        }

        if details:
            result["root_id"] = details.get("root_id")
            result["name"] = details.get("name")
            result["total_reviews"] = details.get("feedbacks_count", 0)
            result["rating"] = details.get("rating", 0.0)
        
        if basket_data:
            # Если Direct API не дал root_id, берем из корзины
            if not result["root_id"]:
                result["root_id"] = basket_data.get('root') or basket_data.get('root_id') or basket_data.get('imt_id')
            
            # Если Direct API не дал отзывов (или 0), доверяем корзине
            if result["total_reviews"] == 0:
                result["total_reviews"] = basket_data.get('feedbacks', 0)

            # Картинку всегда лучше брать из корзины, там готовый URL
            result["image"] = basket_data.get('image_url')
            
            # Имя если API не справился
            if not details:
                result["name"] = basket_data.get('imt_name') or basket_data.get('subj_name')

        return result

    async def get_review_stats(self, sku: int):
        """
        Быстрое получение метаданных для UI.
        """
        logger.info(f"--- CHECK STATS SKU: {sku} ---")
        try:
            data = await self._resolve_root_id_and_meta(sku)
            
            if not data["root_id"]:
                 return {"status": "error", "message": "Товар не найден (Root ID unknown)"}

            # Если отзывов 0, но root_id есть, делаем контрольный выстрел в feedbacks-api
            # (иногда в карточке кешируется 0, а реально отзывы есть)
            if data["total_reviews"] == 0:
                try:
                    url = f"https://feedbacks-api.wildberries.ru/api/v1/feedbacks?isAnswered=false&take=0&skip=0&nmId={sku}&imtId={data['root_id']}"
                    r = requests.get(url, headers={"User-Agent": get_random_ua()}, timeout=3, verify=False)
                    if r.status_code == 200:
                        jd = r.json()
                        cnt = jd.get('data', {}).get('feedbackCount')
                        if cnt is None:
                            cnt = jd.get('feedbackCount')
                        if cnt:
                            data["total_reviews"] = cnt
                except: pass

            return {
                "sku": sku,
                "name": data["name"],
                "image": data["image"],
                "total_reviews": data["total_reviews"],
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Stats error: {e}")
            return {"status": "error", "message": str(e)}

    def get_product_data(self, sku: int):
        """
        Парсинг цен (Selenium + API). Оставлен совместимым.
        """
        # (Этот метод не меняем логику, так как вопрос был про отзывы, но для целостности файла он нужен)
        logger.info(f"--- ПАРСИНГ ЦЕН SKU: {sku} ---")
        static_info = {"name": f"Товар {sku}", "brand": "WB", "image": ""}
        total_qty = 0

        # Попытка 1: API Direct
        details = self._get_card_details_direct(sku)
        if details:
             static_info["name"] = details.get('name')
             static_info["brand"] = details.get('brand')
             # Считаем остатки из details если есть размеры
             # (тут упрощение, полная логика в get_full_product_info не требуется)

        # Попытка 2: Basket Finder (Async in Sync)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            b_data = loop.run_until_complete(self.basket_finder.find_card_json(sku))
            loop.close()
            if b_data:
                static_info["image"] = b_data.get('image_url')
                if not details:
                     static_info["name"] = b_data.get('imt_name')
                for size in b_data.get('sizes', []):
                    for s in size.get('stocks', []): total_qty += s.get('qty', 0)
        except: pass

        # Selenium часть для цен
        for attempt in range(1, 4):
            driver = None
            try:
                driver = self.browser_manager.init_driver()
                url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP"
                driver.get(url)
                time.sleep(8)
                driver.execute_script("window.scrollTo(0, 400);")
                try:
                    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".price-block__wallet-price, .price-block__final-price")))
                except: pass
                
                # JS Model
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

                # DOM parsing fallback
                wallet = self.browser_manager.extract_price(driver, ".price-block__wallet-price, [class*='walletPrice']")
                standard = self.browser_manager.extract_price(driver, ".price-block__final-price, [class*='priceBlockFinal']")
                base = self.browser_manager.extract_price(driver, ".price-block__old-price, [class*='priceBlockOld']")
                if wallet == 0 and standard > 0: wallet = standard
                if wallet > 0:
                     return {
                        "id": sku, "name": static_info["name"], "brand": static_info["brand"],
                        "image": static_info["image"], "stock_qty": total_qty, 
                        "prices": {"wallet_purple": wallet, "standard_black": standard, "base_crossed": base},
                        "status": "success"
                    }
            except Exception as e:
                logger.error(f"Price error attempt {attempt}: {e}")
            finally:
                if driver: driver.quit()
        return {"id": sku, "status": "error", "message": "Failed to parse prices"}

    def get_full_product_info(self, sku: int, limit: int = 100):
        logger.info(f"--- АНАЛИЗ ОТЗЫВОВ SKU: {sku} (TARGET: {limit}) ---")
        try:
            # 1. Resolve Root ID (Sync wrapper for Async helper)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            meta = loop.run_until_complete(self._resolve_root_id_and_meta(sku))
            loop.close()

            if not meta["root_id"]:
                return {"status": "error", "message": "Root ID not found (товар не найден)"}
            
            root_id = meta["root_id"]
            logger.info(f"Resolved root_id: {root_id} for sku: {sku}")

            all_reviews = []
            rating_value = meta["rating"]
            
            # 2. Fetch Reviews from API
            headers = {
                "User-Agent": get_random_ua(),
                "Accept": "*/*",
                "Origin": "https://www.wildberries.ru",
                "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            }
            
            batch_size = 100 
            current_skip = 0
            is_api_working = True
            
            while len(all_reviews) < limit and is_api_working:
                take = min(batch_size, limit - len(all_reviews))
                api_url = f"https://feedbacks-api.wildberries.ru/api/v1/feedbacks?isAnswered=false&take={take}&skip={current_skip}&nmId={sku}&imtId={root_id}"
                
                try:
                    r = requests.get(api_url, headers=headers, timeout=10, verify=False)
                    if r.status_code == 200:
                        data = r.json()
                        feedbacks = data.get('feedbacks') or data.get('data', {}).get('feedbacks') or []
                        
                        if current_skip == 0:
                            val = data.get('valuation') or data.get('data', {}).get('valuation')
                            if val: rating_value = val

                        if not feedbacks:
                            logger.info("API returned empty list, stopping.")
                            break
                            
                        for f in feedbacks:
                            txt = f.get('text', '')
                            if txt:
                                all_reviews.append({"text": txt, "rating": f.get('productValuation', 5)})
                        
                        current_skip += len(feedbacks)
                        time.sleep(0.2)
                    else:
                        logger.warning(f"Feedbacks API Error: {r.status_code}")
                        is_api_working = False
                except Exception as e:
                    logger.error(f"API Loop Error: {e}")
                    is_api_working = False
            
            # 3. Fallback to Static if API completely failed (0 reviews)
            if len(all_reviews) == 0:
                logger.info("Fallback to static feedbacks")
                static_endpoints = [
                    f"https://feedbacks1.wb.ru/feedbacks/v1/{root_id}",
                    f"https://feedbacks2.wb.ru/feedbacks/v1/{root_id}"
                ]
                for url in static_endpoints:
                    try:
                        r = requests.get(url, headers=headers, timeout=10, verify=False)
                        if r.status_code == 200:
                            raw = r.json()
                            feed_list = raw if isinstance(raw, list) else raw.get('feedbacks', [])
                            if not feed_list: continue
                            
                            for f in feed_list:
                                txt = f.get('text', '')
                                if txt:
                                    all_reviews.append({"text": txt, "rating": f.get('productValuation', 5)})
                                if len(all_reviews) >= limit: break
                            if len(all_reviews) > 0: break
                    except: continue

            return {
                "sku": sku,
                "image": meta["image"],
                "rating": float(rating_value),
                "reviews": all_reviews[:limit],
                "reviews_count": len(all_reviews),
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Full parse error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    async def get_seo_data(self, sku: int):
        # SEO logic remains unchanged
        logger.info(f"--- SEO PARSE SKU: {sku} ---")
        try:
            card_data = await self.basket_finder.find_card_json(sku)
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
                    if group.get('options'): options.extend(group.get('options'))
            stop_values = ['нет', 'да', 'отсутствует', 'без рисунка', 'китай', 'россия', '0', '1', '2', '3']
            for opt in options:
                val = str(opt.get('value', '')).strip()
                name_param = str(opt.get('name', '')).lower()
                if not val or val.lower() in stop_values or len(val) < 2: continue 
                if val.isdigit() and "год" not in name_param: continue
                if "состав" in name_param or "назначение" in name_param or "рисунок" in name_param or "фактура" in name_param:
                    parts = re.split(r'[,/]', val)
                    for p in parts: keywords.append(p.strip())
                else: keywords.append(val)
            clean_keywords = []
            seen = set()
            for k in keywords:
                k_clean = re.sub(r'[^\w\s-]', '', k).strip()
                if k_clean and k_clean.lower() not in seen:
                    seen.add(k_clean.lower())
                    clean_keywords.append(k_clean)
            return {"sku": sku, "name": name, "image": card_data.get('image_url'), "keywords": clean_keywords[:40], "status": "success"}
        except Exception as e:
            logger.error(f"SEO Parse Error: {e}")
            return {"status": "error", "message": str(e)}