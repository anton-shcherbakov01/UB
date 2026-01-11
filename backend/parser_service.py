import os
import logging
import json
import random
import asyncio
import re
from typing import Optional, Dict, List, Any, Union
from pydantic import BaseModel, Field, ValidationError

# Third-party imports
try:
    from curl_cffi.requests import AsyncSession
except ImportError:
    raise ImportError("curl_cffi is required. Install it via `pip install curl_cffi`")

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | [%(name)s] %(message)s'
)
logger = logging.getLogger("WB-HttpParser")

# Constants
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
WB_CARD_API_URL = "https://card.wb.ru/cards/v2/detail"
WB_SEARCH_API_URL = "https://search.wb.ru/exactmatch/ru/common/v7/search"
MAX_RETRIES = 5
BASE_DELAY = 1.0

# --- Pydantic Models for Input/Output Validation ---

class PriceData(BaseModel):
    wallet_purple: int
    standard_black: int
    base_crossed: int

class ProductData(BaseModel):
    id: int
    name: str = Field(default="Unknown")
    brand: str = Field(default="Unknown")
    image: str = Field(default="")
    stock_qty: int = Field(default=0)
    prices: PriceData
    status: str = Field(default="success")
    error: Optional[str] = None

class SeoData(BaseModel):
    sku: int
    name: str
    image: str
    keywords: List[str]
    status: str

# --- Proxy Manager ---

class ProxyManager:
    """
    Manages proxy rotation and formatting for curl_cffi.
    Expects PROXY_LIST env var as comma-separated list:
    format: protocol://user:pass@host:port (e.g. http://user:pass@1.2.3.4:8080)
    """
    def __init__(self):
        self.proxies = self._load_proxies()
        self.current_index = 0

    def _load_proxies(self) -> List[str]:
        proxy_str = os.getenv("PROXY_LIST", "")
        if not proxy_str:
            logger.warning("No proxies found in PROXY_LIST env. Running in direct mode.")
            return []
        
        proxies = [p.strip() for p in proxy_str.split(",") if p.strip()]
        logger.info(f"Loaded {len(proxies)} proxies.")
        return proxies

    def get_proxy(self) -> Optional[str]:
        if not self.proxies:
            return None
        return random.choice(self.proxies)

    def rotate(self) -> Optional[str]:
        """Returns a proxy using round-robin or random strategy."""
        return self.get_proxy()

# --- Main Parser Service ---

class WBHttpParser:
    """
    High-performance, Async HTTP-based parser for Wildberries.
    Replaces Selenium with curl_cffi to mimic Chrome TLS fingerprints.
    """
    def __init__(self):
        self.proxy_manager = ProxyManager()
        self.dest_coords = "-1257786" # Moscow/Central region identifier
        self.currency = "rub"

    # --- Basket & Host Logic ---

    def _calc_basket_static(self, sku: int) -> str:
        """Calculates the likely basket host based on SKU volume."""
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
        return "18" # Default fallback, actual lookup may be needed for >18

    def _get_basket_hosts_priority(self, sku: int) -> List[str]:
        """Returns a prioritized list of basket hosts to check."""
        calc_host = self._calc_basket_static(sku)
        # Priority: Calculated -> New hosts (18-25) -> Standard (01-17)
        hosts = [calc_host] + [f"{i:02d}" for i in range(18, 26)] + [f"{i:02d}" for i in range(1, 18)]
        # Remove duplicates while preserving order
        seen = set()
        unique_hosts = []
        for h in hosts:
            if h not in seen:
                unique_hosts.append(h)
                seen.add(h)
        return unique_hosts

    # --- Core HTTP Methods ---

    async def _fetch_with_retry(
        self, 
        url: str, 
        params: Optional[Dict] = None, 
        headers: Optional[Dict] = None,
        use_proxy: bool = True
    ) -> Optional[Dict]:
        """
        Executes HTTP GET with exponential backoff for 429/5xx errors.
        Rotates proxy on failure if enabled.
        """
        retries = 0
        current_proxy = self.proxy_manager.get_proxy() if use_proxy else None
        
        while retries < MAX_RETRIES:
            try:
                async with AsyncSession(impersonate="chrome124") as session:
                    # Configure proxy if available
                    if current_proxy:
                        session.proxies = {"http": current_proxy, "https": current_proxy}
                    
                    response = await session.get(
                        url, 
                        params=params, 
                        headers=headers, 
                        timeout=10
                    )

                    if response.status_code == 200:
                        try:
                            return response.json()
                        except json.JSONDecodeError:
                            logger.error(f"JSON Decode Error for {url}")
                            return None
                    
                    elif response.status_code in [429, 502, 503, 504]:
                        wait_time = BASE_DELAY * (2 ** retries) + random.uniform(0, 1)
                        logger.warning(f"Got {response.status_code} for {url}. Retrying in {wait_time:.2f}s...")
                        await asyncio.sleep(wait_time)
                        retries += 1
                        # Rotate proxy on error
                        if use_proxy:
                            current_proxy = self.proxy_manager.rotate()
                    
                    elif response.status_code == 404:
                        # Resource not found, no need to retry
                        return None
                    
                    else:
                        logger.error(f"HTTP {response.status_code} for {url}")
                        return None

            except Exception as e:
                logger.error(f"Request Exception: {str(e)} for {url}")
                retries += 1
                await asyncio.sleep(BASE_DELAY)
                if use_proxy:
                    current_proxy = self.proxy_manager.rotate()
        
        logger.error(f"Max retries reached for {url}")
        return None

    # --- API Implementation ---

    async def get_product_json(self, sku: int) -> Optional[Dict]:
        """
        Fetches the raw card.json from basket hosts.
        Brute-forces hosts if the static calculation fails.
        """
        vol = sku // 100000
        part = sku // 1000
        hosts = self._get_basket_hosts_priority(sku)

        # Batch requests to find the correct host quickly
        # We process in small chunks to avoid spamming 50 requests at once
        chunk_size = 5
        for i in range(0, len(hosts), chunk_size):
            chunk = hosts[i:i + chunk_size]
            tasks = []
            
            for host in chunk:
                url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
                tasks.append(self._fetch_with_retry(url, use_proxy=True))
            
            results = await asyncio.gather(*tasks)
            
            for res, host in zip(results, chunk):
                if res:
                    # Inject image URL helper since it depends on the resolved host
                    res['__host'] = host 
                    res['__image_url'] = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"
                    return res
        
        logger.warning(f"card.json not found for SKU {sku} on any host.")
        return None

    async def get_current_price_data(self, sku: int) -> Optional[Dict]:
        """
        Fetches real-time price and stock data from the Client API (card.wb.ru).
        This source is more reliable for prices than card.json.
        """
        params = {
            "appType": "1",
            "curr": self.currency,
            "dest": self.dest_coords,
            "spp": "30",
            "nm": str(sku)
        }
        
        data = await self._fetch_with_retry(WB_CARD_API_URL, params=params)
        
        if not data or not data.get("data") or not data["data"].get("products"):
            return None
            
        return data["data"]["products"][0]

    def parse_seo_tags(self, json_data: Dict) -> List[str]:
        """
        Extracts relevant keywords from card.json structure.
        Looks into name, subject, options, and grouped_options.
        """
        keywords = set()
        
        # 1. Basic Fields
        if json_data.get("imt_name"): keywords.add(json_data["imt_name"])
        if json_data.get("subj_name"): keywords.add(json_data["subj_name"])
        
        # 2. Options (Flat list)
        options = json_data.get("options", [])
        
        # 3. Grouped Options (New structure)
        if not options and "grouped_options" in json_data:
            for group in json_data["grouped_options"]:
                if "options" in group:
                    options.extend(group["options"])
        
        # Filter and process options
        stop_words = {'нет', 'да', 'отсутствует', 'китай', 'россия', 'корея', 'узбекистан'}
        
        for opt in options:
            name = opt.get("name", "").lower()
            value = str(opt.get("value", "")).strip()
            
            if not value or value.lower() in stop_words:
                continue
            
            # Skip pure numbers unless it's specific like '100% cotton'
            if value.isdigit() and "год" not in name:
                continue
                
            # Split comma/slash separated values
            parts = re.split(r'[,/]', value)
            for part in parts:
                cleaned = part.strip()
                if len(cleaned) > 1:
                    keywords.add(cleaned)
                    
        return list(keywords)

    # --- Public Methods ---

    async def get_product_data(self, sku: int) -> Dict[str, Any]:
        """
        Main entry point for product parsing.
        Combines static data (card.json) and dynamic data (Client API).
        """
        logger.info(f"Parsing SKU: {sku}")
        
        try:
            # Parallel fetch of Static Data and Price Data
            json_task = self.get_product_json(sku)
            price_task = self.get_current_price_data(sku)
            
            card_json, price_api_data = await asyncio.gather(json_task, price_task)
            
            # --- Construct Result ---
            result = {
                "id": sku,
                "name": "Unknown",
                "brand": "Unknown",
                "image": "",
                "stock_qty": 0,
                "prices": {
                    "wallet_purple": 0,
                    "standard_black": 0,
                    "base_crossed": 0
                },
                "status": "error"
            }

            # Fill from Static Data
            if card_json:
                result["name"] = card_json.get("imt_name") or card_json.get("subj_name", "Unknown")
                result["brand"] = card_json.get("selling", {}).get("brand_name", "Unknown")
                result["image"] = card_json.get("__image_url", "")
                
                # Fallback stocks from card.json if API fails
                if not price_api_data:
                    total_qty = 0
                    for size in card_json.get("sizes", []):
                        for stock in size.get("stocks", []):
                            total_qty += stock.get("qty", 0)
                    result["stock_qty"] = total_qty

            # Fill from Price API (Preferred)
            if price_api_data:
                # Name override (sometimes API has better formatted name)
                if not result["name"] or result["name"] == "Unknown":
                    result["name"] = price_api_data.get("name", "Unknown")
                if not result["brand"] or result["brand"] == "Unknown":
                    result["brand"] = price_api_data.get("brand", "Unknown")
                
                # Prices are usually in kopecks (cents), need to divide by 100
                # "priceU" = Base Price (Crossed out)
                # "salePriceU" = Standard Sale Price
                # "clientPriceU" = WB Wallet Price
                
                # Fallbacks if clientPriceU is missing (sometimes it is 0)
                base = int(price_api_data.get("priceU", 0) / 100)
                sale = int(price_api_data.get("salePriceU", 0) / 100)
                # clientPriceU is sometimes hidden in extended props, logic:
                # usually extended object is needed, but assuming basic access:
                wallet = int(price_api_data.get("clientPriceU", 0) / 100)
                
                # If wallet price is 0, it usually means it equals sale price or user not logged in
                if wallet == 0:
                    wallet = sale

                result["prices"] = {
                    "wallet_purple": wallet,
                    "standard_black": sale,
                    "base_crossed": base
                }
                
                # Stocks from API
                total_qty = 0
                for size in price_api_data.get("sizes", []):
                    for stock in size.get("stocks", []):
                        total_qty += stock.get("qty", 0)
                result["stock_qty"] = total_qty

            # Check success
            if card_json or price_api_data:
                result["status"] = "success"
                
            return result

        except Exception as e:
            logger.error(f"Critical error parsing SKU {sku}: {str(e)}", exc_info=True)
            return {"id": sku, "status": "error", "message": str(e)}

    async def get_batch_product_data(self, skus: List[int]) -> List[Dict]:
        """
        High-performance batch fetching using asyncio.gather.
        """
        tasks = [self.get_product_data(sku) for sku in skus]
        return await asyncio.gather(*tasks)

    async def get_seo_data(self, sku: int) -> Dict[str, Any]:
        """
        Public method to get SEO tags for a product.
        """
        card_json = await self.get_product_json(sku)
        if not card_json:
            return {"sku": sku, "status": "error", "message": "Card not found"}
        
        keywords = self.parse_seo_tags(card_json)
        
        return {
            "sku": sku,
            "name": card_json.get("imt_name") or card_json.get("subj_name"),
            "image": card_json.get("__image_url"),
            "keywords": list(keywords)[:50], # Top 50 keywords
            "status": "success"
        }

    async def get_full_product_info(self, sku: int, limit: int = 50) -> Dict[str, Any]:
        """
        Fetches reviews (feedbacks) for AI analysis.
        Uses HTTP instead of Requests for consistency and proxy support.
        """
        # We need root_id (imt_id) to fetch reviews
        card_json = await self.get_product_json(sku)
        if not card_json:
            return {"status": "error", "message": "Product not found"}
        
        root_id = card_json.get("root") or card_json.get("imt_id")
        if not root_id:
             return {"status": "error", "message": "Root ID not found"}

        # Review API Endpoints (WB has multiple, we try them in order)
        endpoints = [
            f"https://feedbacks1.wb.ru/feedbacks/v1/{root_id}",
            f"https://feedbacks2.wb.ru/feedbacks/v1/{root_id}",
            f"https://feedbacks-api.wildberries.ru/api/v1/feedbacks?isAnswered=false&take={limit}&skip=0&nmId={sku}&imtId={root_id}"
        ]

        for url in endpoints:
            data = await self._fetch_with_retry(url)
            if data:
                raw_feedbacks = data.get("feedbacks") or data.get("data", {}).get("feedbacks") or []
                valuation = data.get("valuation") or data.get("data", {}).get("valuation", "0")
                
                reviews = []
                for f in raw_feedbacks:
                    text = f.get("text", "")
                    if text:
                        reviews.append({
                            "text": text,
                            "rating": f.get("productValuation", 5),
                            "date": f.get("createdDate")
                        })
                    if len(reviews) >= limit:
                        break
                
                return {
                    "sku": sku,
                    "image": card_json.get("__image_url"),
                    "rating": float(valuation),
                    "reviews": reviews,
                    "reviews_count": len(reviews),
                    "status": "success"
                }
        
        return {"status": "error", "message": "Reviews not available"}

    async def get_search_position(self, query: str, target_sku: int) -> int:
        """
        Determines product position in search results via API (Catalog/Search).
        Iterates through pages until found or limit reached.
        """
        # URL encoding for query
        # Using simple replace for basic needs, or create a helper if complex symbols arise
        # curl_cffi handles encoding in params usually, but manual encoding ensures WB format
        
        # WB Search API parameters
        base_params = {
            "appType": "1",
            "curr": self.currency,
            "dest": self.dest_coords,
            "query": query,
            "resultset": "catalog",
            "sort": "popular",
            "spp": "30",
            "suppressSpellcheck": "false"
        }
        
        page = 1
        found = False
        
        # Check first 5 pages (500 items)
        while page <= 5 and not found:
            # Note: page param might be required even for page 1
            # WB API uses 'page' parameter for pagination
            # Items per page is usually 100
            
            # Clone params for this page
            params = base_params.copy()
            if page > 1:
                params["page"] = str(page)
            
            # Attempt to fetch search results
            data = await self._fetch_with_retry(WB_SEARCH_API_URL, params=params)
            
            if not data or not data.get("data") or not data["data"].get("products"):
                break # No more results
            
            products = data["data"]["products"]
            
            for index, product in enumerate(products):
                # Check ID
                pid = product.get("id")
                if pid == target_sku:
                    # Position = (Page - 1) * 100 + Index + 1
                    return (page - 1) * 100 + index + 1
            
            page += 1
            # Small delay between pages to be polite
            await asyncio.sleep(0.2)
            
        return 0 # Not found in top 500

# Singleton instance
parser_service = WBHttpParser()