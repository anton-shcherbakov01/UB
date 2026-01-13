import re
import time
import random
import asyncio
import aiohttp
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .config import logger, GEO_ZONES, get_random_ua
from .proxy import ProxyManager
from .browser import BrowserManager

class SearchParser:
    def __init__(self):
        self.proxy_manager = ProxyManager()
        self.browser_manager = BrowserManager()

    async def get_search_position_v2(self, query: str, target_sku: int, dest: str = GEO_ZONES["moscow"]):
        """Гибридный поиск: API -> Fallback to Selenium"""
        target_sku = int(target_sku)
        url = "https://search.wb.ru/exactmatch/ru/common/v7/search"
        params = {
            "ab_testing": "false", "appType": "1", "curr": "rub", "dest": dest, 
            "query": query, "resultset": "catalog", "sort": "popular", 
            "spp": "30", "suppressSpellcheck": "false"
        }
        
        max_retries = 3
        api_failed = False
        
        for attempt in range(max_retries):
            proxy_url = self.proxy_manager.get_aiohttp_proxy(rotate=True)
            headers = {"User-Agent": get_random_ua(), "Accept": "*/*"}
            
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
                        
                        # Если не нашли - значит позиция 0
                        return {"organic_pos": 0, "ad_pos": 0, "is_boosted": False}

            except Exception as e:
                logger.error(f"API Connection Error: {e}")
                await asyncio.sleep(1)
                continue
        
        logger.info("API attempts exhausted or failed. Executing Selenium Fallback.")
        return await self._get_search_position_selenium_fallback(query, target_sku)

    async def _get_search_position_selenium_fallback(self, query: str, target_sku: int):
        logger.info(f"⚡ FALLBACK: Starting Selenium Search for '{query}'...")
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._run_selenium_search_sync, query, target_sku)
        except Exception as e:
            logger.error(f"Selenium Fallback Error: {e}")
            return {"organic_pos": 0, "ad_pos": 0, "is_boosted": False}

    def _run_selenium_search_sync(self, query: str, target_sku: int):
        driver = None
        try:
            driver = self.browser_manager.init_driver()
            url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}"
            driver.get(url)
            
            try:
                WebDriverWait(driver, 25).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".product-card, .product-card__wrapper"))
                )
                time.sleep(3)
            except:
                logger.warning("Selenium: Timeout waiting for cards")
                return {"organic_pos": 0, "ad_pos": 0, "is_boosted": False}

            cards = driver.find_elements(By.CSS_SELECTOR, ".product-card__wrapper, .product-card")
            organic_counter = 0
            
            for i, card in enumerate(cards):
                try:
                    link = card.find_element(By.TAG_NAME, "a")
                    href = link.get_attribute("href")
                    match = re.search(r'catalog/(\d+)/detail', href)
                    if not match: continue
                    
                    sku_found = int(match.group(1))
                    text_content = card.get_attribute("textContent").lower()
                    is_ad = "реклама" in text_content
                    
                    if not is_ad: organic_counter += 1
                        
                    if sku_found == int(target_sku):
                        logger.info(f"✅ Selenium Found SKU {target_sku} at pos {i+1}")
                        return {
                            "organic_pos": organic_counter if not is_ad else 0,
                            "ad_pos": (i + 1) if is_ad else 0,
                            "is_boosted": is_ad,
                            "total_pos": i + 1
                        }
                    
                    if i > 100: break
                except: continue

            return {"organic_pos": 0, "ad_pos": 0, "is_boosted": False}
        except Exception as e:
            logger.error(f"Selenium Sync Error: {e}")
            return {"organic_pos": 0, "ad_pos": 0, "is_boosted": False}
        finally:
            if driver:
                try: driver.quit()
                except: pass