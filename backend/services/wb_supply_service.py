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

class WBSupplyBookingService(WBSupplyService):
    """
    Расширенный сервис для работы с API Поставок (v1/planning).
    Позволяет бронировать слоты.
    """
    
    async def get_coefficients_v2(self, warehouse_ids: List[int]):
        """Получение коэффициентов для конкретных складов (оптимизация)"""
        url = f"{self.BASE_URL}/acceptance/coefficients"
        # API может принимать список в query params
        params = {"warehouseIDs": ",".join(map(str, warehouse_ids))}
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except Exception as e:
                logger.error(f"Error fetching coeffs v2: {e}")
        return []

    async def book_slot(self, pre_order_id: int, date_str: str, coefficient: int, warehouse_id: int):
        """
        Попытка забронировать слот для созданного плана (pre_order_id).
        date_str format: '2024-01-25T00:00:00Z'
        """
        # Эндпоинт для постановки плана в таймслот
        url = f"{self.BASE_URL}/planning/{pre_order_id}/slots"
        
        payload = {
            "warehouseId": warehouse_id,
            "date": date_str,
            "coefficient": coefficient
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                # Обычно это PUT или POST запрос (зависит от версии API WB, сейчас чаще PUT)
                async with session.put(url, headers=self.headers, json=payload) as resp:
                    if resp.status in [200, 204]:
                        logger.info(f"✅ Slot booked! Plan {pre_order_id} -> {date_str} (x{coefficient})")
                        return True
                    
                    text = await resp.text()
                    logger.error(f"❌ Booking failed for {pre_order_id}: {resp.status} - {text}")
                    return False
            except Exception as e:
                logger.error(f"Booking exception: {e}")
                return False