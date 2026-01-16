import logging
import aiohttp
import asyncio
import json
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger("SlotsService")

class SlotsService:
    """
    Service for managing WB Warehouse Slots and Acceptance Coefficients.
    API: https://supplies-api.wildberries.ru/api/v1/acceptance/coefficients
    """
    BASE_URL = "https://supplies-api.wildberries.ru/api/v1"

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }

    async def get_coefficients(self, warehouse_ids: Optional[List[int]] = None) -> List[Dict]:
        """
        Fetches acceptance coefficients.
        Returns a list of dicts:
        {
            "date": "2023-10-25T00:00:00Z",
            "coefficient": 0,
            "warehouseID": 117901,
            "warehouseName": "Коледино",
            "boxTypeName": "Короба",
            "boxTypeID": 1
        }
        """
        url = f"{self.BASE_URL}/acceptance/coefficients"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=15) as resp:
                    if resp.status == 401:
                        logger.warning("WB API Unauthorized (Slots)")
                        return []
                    if resp.status != 200:
                        logger.error(f"WB Slots API Error: {resp.status} - {await resp.text()}")
                        return []
                    
                    data = await resp.json()
                    if not isinstance(data, list):
                        return []
                        
                    # Filter by warehouse_ids if provided
                    if warehouse_ids:
                        data = [x for x in data if x.get("warehouseID") in warehouse_ids]
                        
                    return data
        except Exception as e:
            logger.error(f"Failed to fetch slots: {e}")
            return []

    async def get_warehouses(self) -> List[Dict]:
        """Get static list of warehouses."""
        url = f"{self.BASE_URL}/warehouses"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=10) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return []
        except Exception:
            return []