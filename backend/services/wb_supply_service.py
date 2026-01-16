import logging
import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger("WBSupplyService")

class WBSupplyService:
    """
    Service for interacting with WB Supplies API (Acceptance Coefficients, Warehouses).
    Endpoint: https://supplies-api.wildberries.ru
    """
    BASE_URL = "https://supplies-api.wildberries.ru/api/v1"

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }

    async def get_warehouses_coefficients(self) -> List[Dict]:
        """
        Fetches acceptance coefficients for all warehouses.
        """
        url = f"{self.BASE_URL}/acceptance/coefficients"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=10) as resp:
                    if resp.status == 401:
                        logger.warning("WB API Unauthorized (Supplies)")
                        return []
                    if resp.status != 200:
                        logger.error(f"WB Supplies API Error: {resp.status}")
                        return []
                    
                    data = await resp.json()
                    # Data format is usually a list of warehouses with dates and coeffs
                    return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to fetch coefficients: {e}")
            return []

    async def get_warehouses_list(self) -> List[Dict]:
        """
        Get list of all warehouses to map IDs to Names if necessary.
        """
        url = f"{self.BASE_URL}/warehouses"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=10) as resp:
                    if resp.status != 200:
                        return []
                    return await resp.json()
        except Exception:
            return []

# Singleton factory is not needed here as we need per-user token