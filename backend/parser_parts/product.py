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

# Отключаем ворнинги SSL, часто бывают в докере при запросах к WB
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Настраиваем логгер
logger = logging.getLogger("ProductParser")
logger.setLevel(logging.INFO)

class ProductParser:
    def __init__(self):
        self.basket_finder = BasketFinder()
        self.browser_manager = BrowserManager()

    async def _get_basket_data(self, sku: int):
        """
        Единая точка входа для получения метаданных через корзины (BasketFinder).
        Никаких левых API, только хардкорный перебор basket-хостов.
        """
        try:
            # BasketFinder ищет card.json по всем вольюмам
            card_data = await self.basket_finder.find_card_json(sku)
            
            if not card_data:
                logger.error(f"BasketFinder returned None for SKU {sku}")
                return None

            # Извлекаем критически важные данные
            # imt_id (он же root) нужен для отзывов
            root_id = card_data.get('root') or card_data.get('root_id') or card_data.get('imt_id')
            
            # Количество отзывов (иногда поле feedbacks, иногда feedbackCount)
            reviews_count = card_data.get('feedbacks', 0)
            
            # Если в json 0, иногда это ошибка кеша WB, но imt_id у нас уже есть!
            
            return {
                "root_id": root_id,
                "name": card_data.get('imt_name') or card_data.get('subj_name') or f"Товар {sku}",
                "image": card_data.get('image_url'),
                "rating": float(card_data.get('valuation', 0)),
                "total_reviews": reviews_count,
                # Сохраняем размеры для подсчета остатков (если нужно)
                "sizes": card_data.get('sizes', [])
            }
        except Exception as e:
            logger.error(f"Basket extraction error: {e}")
            return None

    async def get_review_stats(self, sku: int):
        """
        Получение данных для UI (Слайдер) через корзины.
        """
        logger.info(f"--- CHECK STATS SKU (BASKET): {sku} ---")
        
        data = await self._get_basket_data(sku)
        
        if not data:
            return {"status": "error", "message": "Не удалось найти card.json в корзинах WB"}

        # Проверка на случай, если в card.json записано 0 отзывов, но root_id есть
        # (Пробуем уточнить кол-во через API отзывов, если уж card.json подвел, но ID верный)
        if data['total_reviews'] == 0 and data['root_id']:
            try:
                url = f"https://feedbacks-api.wildberries.ru/api/v1/feedbacks?isAnswered=false&take=0&skip=0&nmId={sku}&imtId={data['root_id']}"
                r = requests.get(url, headers={"User-Agent": get_random_ua()}, timeout=5, verify=False)
                if r.status_code == 200:
                    jd = r.json()
                    cnt = jd.get('data', {}).get('feedbackCount')
                    if cnt: data['total_reviews'] = cnt
            except: pass

        return {
            "sku": sku,
            "name": data['name'],
            "image": data['image'],
            "total_reviews": data['total_reviews'],
            "status": "success"
        }

    def get_full_product_info(self, sku: int, limit: int = 100):
        """
        Основной метод парсинга отзывов.
        1. Ищем root_id через Basket.
        2. Качаем отзывы (API > Static).
        """
        logger.info(f"--- АНАЛИЗ ОТЗЫВОВ SKU: {sku} (LIMIT: {limit}) ---")
        try:
            # 1. Получаем данные из корзины (Async wrapper)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            meta = loop.run_until_complete(self._get_basket_data(sku))
            loop.close()

            if not meta or not meta.get('root_id'):
                return {"status": "error", "message": "Root ID (imt_id) не найден в card.json"}
            
            root_id = meta['root_id']
            logger.info(f"Found Root ID via Basket: {root_id}")

            all_reviews = []
            rating_value = meta['rating']
            
            # 2. Скачивание отзывов
            # Используем API как основной канал, так как он поддерживает пагинацию
            # Если API не работает у вас, сработает Fallback ниже
            headers = {
                "User-Agent": get_random_ua(),
                "Accept": "*/*",
                "Origin": "https://www.wildberries.ru",
                "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            }

            batch_size = 100
            current_skip = 0
            is_api_working = True
            
            # Цикл сбора через API
            while len(all_reviews) < limit and is_api_working:
                take = min(batch_size, limit - len(all_reviews))
                
                # Важно: передаем и nmId и imtId
                api_url = f"https://feedbacks-api.wildberries.ru/api/v1/feedbacks?isAnswered=false&take={take}&skip={current_skip}&nmId={sku}&imtId={root_id}"
                
                try:
                    r = requests.get(api_url, headers=headers, timeout=10, verify=False)
                    if r.status_code == 200:
                        data = r.json()
                        feedbacks = data.get('feedbacks') or data.get('data', {}).get('feedbacks') or []
                        
                        if current_skip == 0:
                            # Уточняем рейтинг
                            val = data.get('valuation') or data.get('data', {}).get('valuation')
                            if val: rating_value = val

                        if not feedbacks:
                            break # Кончились отзывы
                            
                        for f in feedbacks:
                            txt = f.get('text', '')
                            if txt:
                                all_reviews.append({"text": txt, "rating": f.get('productValuation', 5)})
                        
                        current_skip += len(feedbacks)
                        time.sleep(0.3)
                    else:
                        logger.warning(f"Feedbacks API Error: {r.status_code}")
                        is_api_working = False
                except Exception as e:
                    logger.error(f"API Loop Exception: {e}")
                    is_api_working = False
            
            # 3. FALLBACK: Если API отдал 0 отзывов или упал, используем статику (feedbacks1/2)
            if len(all_reviews) == 0:
                logger.info("API failed/empty. Switching to STATIC feedbacks (v1/v2).")
                static_endpoints = [
                    f"https://feedbacks1.wb.ru/feedbacks/v1/{root_id}",
                    f"https://feedbacks2.wb.ru/feedbacks/v1/{root_id}"
                ]
                
                for url in static_endpoints:
                    try:
                        logger.info(f"Trying static: {url}")
                        r = requests.get(url, headers=headers, timeout=10, verify=False)
                        if r.status_code == 200:
                            raw = r.json()
                            feed_list = raw if isinstance(raw, list) else raw.get('feedbacks', [])
                            
                            if not feed_list:
                                continue

                            logger.info(f"Static file has {len(feed_list)} reviews")
                            for f in feed_list:
                                txt = f.get('text', '')
                                if txt:
                                    all_reviews.append({"text": txt, "rating": f.get('productValuation', 5)})
                                if len(all_reviews) >= limit: break
                            
                            if len(all_reviews) > 0: break
                    except Exception as ex:
                        logger.error(f"Static fetch error: {ex}")

            if not all_reviews:
                logger.warning("No reviews found via API or Static.")

            return {
                "sku": sku,
                "image": meta['image'],
                "rating": float(rating_value),
                "reviews": all_reviews[:limit],
                "reviews_count": len(all_reviews),
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Full parse error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def get_product_data(self, sku: int):
        """
        Парсинг цен (Selenium + Basket).
        Используем Basket для названия/бренда/остатков.
        """
        logger.info(f"--- ПАРСИНГ ЦЕН SKU: {sku} ---")
        static_info = {"name": f"Товар {sku}", "brand": "WB", "image": ""}
        total_qty = 0

        # Получаем статику ТОЛЬКО через Basket
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            b_data = loop.run_until_complete(self.basket_finder.find_card_json(sku))
            loop.close()
            
            if b_data:
                static_info["name"] = b_data.get('imt_name') or b_data.get('subj_name')
                static_info["brand"] = b_data.get('selling', {}).get('brand_name')
                static_info["image"] = b_data.get('image_url')
                
                # Считаем остатки
                for size in b_data.get('sizes', []):
                    for s in size.get('stocks', []):
                        total_qty += s.get('qty', 0)
        except Exception as e:
            logger.error(f"Basket data error for prices: {e}")

        # Selenium для цен (Wallet и СПП)
        for attempt in range(1, 4):
            driver = None
            try:
                driver = self.browser_manager.init_driver()
                url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP"
                driver.get(url)
                time.sleep(10)
                driver.execute_script("window.scrollTo(0, 400);")
                
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".price-block__wallet-price, .price-block__final-price, [class*='walletPrice']"))
                    )
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
                                "id": sku, 
                                "name": static_info["name"], 
                                "brand": static_info["brand"],
                                "image": static_info["image"],
                                "stock_qty": total_qty,
                                "prices": {"wallet_purple": wallet, "standard_black": int(price.get('salePriceU',0)/100), "base_crossed": int(price.get('priceU',0)/100)},
                                "status": "success"
                            }
                except: pass

                # DOM fallback
                wallet = self.browser_manager.extract_price(driver, ".price-block__wallet-price, [class*='walletPrice']")
                standard = self.browser_manager.extract_price(driver, ".price-block__final-price, [class*='priceBlockFinal']")
                base = self.browser_manager.extract_price(driver, ".price-block__old-price, [class*='priceBlockOld']")

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
            except Exception as e:
                logger.error(f"Price attempt {attempt} error: {e}")
            finally:
                if driver: driver.quit()
        
        return {"id": sku, "status": "error", "message": "Failed to parse prices"}

    async def get_seo_data(self, sku: int):
        # SEO без изменений
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