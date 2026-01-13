import time
import json
import re
import asyncio
import requests
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .config import logger, get_random_ua
from .basket import BasketFinder
from .browser import BrowserManager

# Настраиваем логгер для этого модуля, чтобы видеть детали
logger = logging.getLogger("ProductParser")
logger.setLevel(logging.INFO)

class ProductParser:
    def __init__(self):
        self.basket_finder = BasketFinder()
        self.browser_manager = BrowserManager()

    def _get_card_details_direct(self, sku: int):
        """
        Прямой запрос к API карточки для получения точного root_id (imtId).
        Это надежнее, чем искать basket-файл.
        """
        try:
            # Актуальный эндпоинт WB для карточек (используется мобильным приложением и сайтом)
            url = f"https://card.wb.ru/cards/v2/detail?appType=1&curr=rub&dest=-1257786&spp=30&nm={sku}"
            headers = {
                "User-Agent": get_random_ua(),
                "Accept": "*/*",
                "Origin": "https://www.wildberries.ru",
                "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            }
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                products = data.get('data', {}).get('products', [])
                if products:
                    prod = products[0]
                    return {
                        "root_id": prod.get('root'), # Самое важное поле для отзывов
                        "name": prod.get('name'),
                        "brand": prod.get('brand'),
                        "rating": prod.get('reviewRating'),
                        "feedbacks_count": prod.get('feedbacks'),
                        "sizes": prod.get('sizes', []),
                        "subject_root_id": prod.get('subjectRootId') # Иногда нужно
                    }
        except Exception as e:
            logger.error(f"Error fetching card details direct: {e}")
        return None

    async def get_review_stats(self, sku: int):
        """
        Быстрое получение метаданных для UI.
        """
        logger.info(f"--- CHECK STATS SKU: {sku} ---")
        try:
            # 1. Сначала пробуем надежный API
            details = self._get_card_details_direct(sku)
            
            if details:
                total_reviews = details.get('feedbacks_count', 0)
                # Для картинки все равно используем basket_finder, так как там логика сборки URL
                image_url = ""
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    c_data = loop.run_until_complete(self.basket_finder.find_card_json(sku))
                    loop.close()
                    if c_data: image_url = c_data.get('image_url')
                except: pass

                return {
                    "sku": sku,
                    "name": details.get('name', 'Товар'),
                    "image": image_url,
                    "total_reviews": total_reviews,
                    "status": "success"
                }
            
            # Fallback к старой логике если API карточки отвалился
            return {"status": "error", "message": "Не удалось получить данные о товаре (API error)"}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_product_data(self, sku: int):
        """
        Парсинг цен и остатков (Selenium + API).
        """
        logger.info(f"--- ПАРСИНГ ЦЕН SKU: {sku} ---")
        
        static_info = {"name": f"Товар {sku}", "brand": "WB", "image": ""}
        total_qty = 0

        # Получаем данные через direct API для надежности имени и бренда
        details = self._get_card_details_direct(sku)
        if details:
             static_info["name"] = details.get('name')
             static_info["brand"] = details.get('brand')
             for size in details.get('sizes', []):
                 for stock in size.get('stocks', []):
                     total_qty += stock.get('qty', 0)
        
        # Получаем картинку через BasketFinder (так как генерация URL сложная)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            b_data = loop.run_until_complete(self.basket_finder.find_card_json(sku))
            loop.close()
            if b_data: 
                static_info["image"] = b_data.get('image_url')
                if not details: # Если direct не сработал, берем отсюда остатки
                     static_info["name"] = b_data.get('imt_name')
                     for size in b_data.get('sizes', []):
                        for s in size.get('stocks', []): total_qty += s.get('qty', 0)
        except: pass

        # Парсинг цены через Selenium (так как API часто скрывает СПП/Wallet)
        for attempt in range(1, 4):
            driver = None
            try:
                driver = self.browser_manager.init_driver()
                url = f"https://www.wildberries.ru/catalog/{sku}/detail.aspx?targetUrl=GP"
                driver.get(url)
                time.sleep(10) # Чуть меньше ждем, 15 много
                driver.execute_script("window.scrollTo(0, 400);")
                
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".price-block__wallet-price, .price-block__final-price, [class*='walletPrice']"))
                    )
                except: pass

                # Попытка 1: JS Model
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

                # Попытка 2: DOM
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
                logger.error(f"Price parsing attempt {attempt} failed: {e}")
            finally:
                if driver: driver.quit()
        
        return {"id": sku, "status": "error", "message": "Не удалось спарсить цены"}

    def get_full_product_info(self, sku: int, limit: int = 100):
        logger.info(f"--- АНАЛИЗ ОТЗЫВОВ SKU: {sku} (TARGET: {limit}) ---")
        try:
            # 1. Получаем точный Root ID (imtId)
            details = self._get_card_details_direct(sku)
            root_id = None
            image_url = ""
            
            if details:
                root_id = details.get('root_id')
            
            # Если прямой запрос не дал root_id, пробуем через BasketFinder
            if not root_id:
                logger.warning("Direct card details failed, trying basket finder...")
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    static_data = loop.run_until_complete(self.basket_finder.find_card_json(sku))
                    loop.close()
                    if static_data:
                        root_id = static_data.get('root') or static_data.get('root_id') or static_data.get('imt_id')
                        image_url = static_data.get('image_url')
                except Exception as e:
                    logger.error(f"Basket finder error: {e}")

            if not root_id: 
                logger.error(f"CRITICAL: Root ID not found for SKU {sku}")
                return {"status": "error", "message": "Root ID not found (товар не найден)"}
            
            logger.info(f"Resolved root_id: {root_id} for sku: {sku}")

            all_reviews = []
            rating_value = details.get('rating') if details else 0.0
            
            # 2. Пытаемся получить через API (feedbacks-api)
            # Этот API лучше всего работает с пагинацией
            headers = {
                "User-Agent": get_random_ua(),
                "Accept": "*/*",
                "Origin": "https://www.wildberries.ru",
                "Referer": f"https://www.wildberries.ru/catalog/{sku}/detail.aspx"
            }
            
            batch_size = 100 
            is_api_working = True
            current_skip = 0
            
            # Если лимит маленький (<100), пробуем взять за один запрос
            while len(all_reviews) < limit and is_api_working:
                take = min(batch_size, limit - len(all_reviews))
                
                # IMPORTANT: WB API is capricious. 
                # Sometimes it wants 'nmId', sometimes 'imtId'. Providing both is safer.
                api_url = f"https://feedbacks-api.wildberries.ru/api/v1/feedbacks?isAnswered=false&take={take}&skip={current_skip}&nmId={sku}&imtId={root_id}"
                
                try:
                    r = requests.get(api_url, headers=headers, timeout=10)
                    if r.status_code == 200:
                        data = r.json()
                        feedbacks = data.get('feedbacks') or data.get('data', {}).get('feedbacks') or []
                        
                        if current_skip == 0:
                            # Обновляем рейтинг из ответа API отзывов (он точнее)
                            rating_value = data.get('valuation') or data.get('data', {}).get('valuation', rating_value)

                        if not feedbacks:
                            logger.info(f"API returned empty list at skip {current_skip}. Stopping.")
                            break
                            
                        for f in feedbacks:
                            txt = f.get('text', '')
                            if txt:
                                all_reviews.append({"text": txt, "rating": f.get('productValuation', 5)})
                        
                        logger.info(f"Fetched {len(feedbacks)} reviews via API (Total: {len(all_reviews)})")
                        current_skip += len(feedbacks)
                        time.sleep(0.3)
                    else:
                        logger.warning(f"Feedbacks API Error: {r.status_code}")
                        is_api_working = False
                except Exception as e:
                    logger.error(f"API Exception: {e}")
                    is_api_working = False
            
            # 3. Fallback: Статические JSON файлы
            # Если API вернул 0 отзывов, но мы знаем что они есть (или API сдох), пробуем статику
            if len(all_reviews) == 0:
                logger.info("Main API failed or returned 0. Trying static fallback endpoints.")
                
                static_endpoints = [
                    f"https://feedbacks1.wb.ru/feedbacks/v1/{root_id}",
                    f"https://feedbacks2.wb.ru/feedbacks/v1/{root_id}"
                ]
                
                for url in static_endpoints:
                    try:
                        logger.info(f"Trying static url: {url}")
                        r = requests.get(url, headers=headers, timeout=10)
                        if r.status_code == 200:
                            feed_data = r.json()
                            
                            # Статика может возвращать список напрямую или объект с полем feedbacks
                            raw = []
                            if isinstance(feed_data, list):
                                raw = feed_data
                            elif isinstance(feed_data, dict):
                                raw = feed_data.get('feedbacks') or []
                            
                            if not raw:
                                logger.info("Static file empty.")
                                continue
                            
                            logger.info(f"Static file found with {len(raw)} reviews.")
                            
                            # Статика не поддерживает skip/take, она отдает все сразу (или последние N)
                            # Нам нужно отсортировать (обычно там старые в начале или хаос, но WB отдает свежие первыми часто)
                            # Просто берем сколько надо
                            count_added = 0
                            for f in raw:
                                txt = f.get('text', '')
                                if txt:
                                    all_reviews.append({"text": txt, "rating": f.get('productValuation', 5)})
                                    count_added += 1
                                if len(all_reviews) >= limit: break
                            
                            if len(all_reviews) > 0: break # Если нашли в первом зеркале, выходим
                    except Exception as ex:
                        logger.error(f"Static fallback error {url}: {ex}")

            # Финальная проверка
            if not all_reviews:
                 logger.warning("No reviews found anywhere.")
            
            return {
                "sku": sku,
                "image": image_url or details.get('image'), # Если basket_finder упал, картинки может не быть
                "rating": float(rating_value),
                "reviews": all_reviews[:limit],
                "reviews_count": len(all_reviews),
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Full info parse error: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    async def get_seo_data(self, sku: int):
        # SEO метод оставляем без изменений, он не влияет на отзывы
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