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

    # ID популярных складов для fallback-запроса, если общий список пуст
    POPULAR_WAREHOUSES = [
        117901, # Коледино
        120762, # Электросталь
        117501, # Подольск
        121709, # Казань
        124731, # Тула
        130744, # Краснодар
        159402, # Санкт-Петербург (Уткина Заводь)
        119276, # Екатеринбург
        161404, # Новосибирск
        173295, # Невинномысск
        131615, # Астана
        131613, # Минск
    ]

    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }

    async def get_coefficients(self, warehouse_ids: Optional[List[int]] = None) -> List[Dict]:
        """
        Fetches acceptance coefficients.
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
                    
                    # Если данных мало, попробуем запросить конкретные склады (иногда это помогает)
                    if isinstance(data, list) and len(data) == 0 and not warehouse_ids:
                         logger.info("Slots API returned empty list, trying specific warehouses...")
                         return await self.get_coefficients(self.POPULAR_WAREHOUSES)

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