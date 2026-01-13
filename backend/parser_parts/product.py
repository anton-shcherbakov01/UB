import time
import json
import re
import asyncio
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .config import logger, get_random_ua
from .basket import BasketFinder
from .browser import BrowserManager

class ProductParser:
    def __init__(self):
        self.basket_finder = BasketFinder()
        self.browser_manager = BrowserManager()

    def get_product_data(self, sku: int):
        logger.info(f"--- ПАРСИНГ ЦЕН SKU: {sku} ---")
        
        static_info = {"name": f"Товар {sku}", "brand": "WB", "image": ""}
        total_qty = 0

        # 1. Получаем статику + ОСТАТКИ из card.json (Async in Sync wrapper)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(self.basket_finder.find_card_json(sku))
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
                driver = self.browser_manager.init_driver()
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

                # Попытка 1: Через JS модель
                try:
                    p_json = driver.execute_script("return window.staticModel ? JSON.stringify(window.staticModel) : null;")
                    if p_json:
                        d = json.loads(p_json)
                        price = d.get('price') or (d['products'][0] if 'products' in d else {})
                        wallet = int(price.get('clientPriceU', 0)/100) or int(price.get('totalPrice', 0)/100)
                        
                        if wallet > 0:
                            # Допарсиваем остатки если не нашли через API
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

                # Попытка 2: Через DOM
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
                else:
                    logger.warning(f"Prices not found in DOM attempt {attempt}")

            except Exception as e:
                logger.error(f"Price attempt {attempt} error: {e}")
            finally:
                if driver: driver.quit()
        
        return {"id": sku, "status": "error", "message": "Failed to parse prices after retries"}

    def get_full_product_info(self, sku: int, limit: int = 50):
        logger.info(f"--- АНАЛИЗ ОТЗЫВОВ SKU: {sku} (LIMIT: {limit}) ---")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            static_data = loop.run_until_complete(self.basket_finder.find_card_json(sku))
            loop.close()

            if not static_data: 
                return {"status": "error", "message": "Card not found"}
            root_id = static_data.get('root') or static_data.get('root_id') or static_data.get('imt_id')
            if not root_id: return {"status": "error", "message": "Root ID not found"}

            endpoints = [
                f"https://feedbacks1.wb.ru/feedbacks/v1/{root_id}",
                f"https://feedbacks2.wb.ru/feedbacks/v1/{root_id}",
                f"https://feedbacks-api.wildberries.ru/api/v1/feedbacks?isAnswered=false&take={limit}&skip=0&nmId={sku}&imtId={root_id}"
            ]
            
            feed_data = None
            headers = {"User-Agent": get_random_ua()}
            
            for url in endpoints:
                try:
                    r = requests.get(url, headers=headers, timeout=10)
                    if r.status_code == 200:
                        feed_data = r.json()
                        # Если получили данные и их достаточно (или это feedbacks-api который отдает сколько просили), то ок
                        # Для feedbacks1 обычно отдается много, проверим длину ниже
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
                # Break only if we strictly reached the limit
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