# backend/services/wb_supply_v2.py
import logging
import aiohttp
from datetime import datetime

logger = logging.getLogger("WB-Supply-Booking")

class WBSupplyBookingService:
    BASE_URL = "https://supplies-api.wildberries.ru/api/v1"

    def __init__(self, token: str):
        self.headers = {
            "Authorization": token,
            "Content-Type": "application/json"
        }

    async def get_coefficients(self, warehouse_ids: list):
        """Получение коэффициентов (существующий метод)"""
        url = f"{self.BASE_URL}/acceptance/coefficients"
        params = {"warehouseIDs": ",".join(map(str, warehouse_ids))}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
        return []

    async def create_supply_plan(self, name: str):
        """Создание плана поставки"""
        url = f"{self.BASE_URL}/planning"
        payload = {"name": name}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload) as resp:
                if resp.status == 201:
                    return await resp.json() # вернет {id: ...}
                raise Exception(f"Err create plan: {await resp.text()}")

    async def book_slot(self, plan_id: int, warehouse_id: int, date: str, coefficient: int):
        """
        БРОНИРОВАНИЕ СЛОТА (Самая важная функция)
        date format: '2024-05-20'
        """
        url = f"{self.BASE_URL}/planning/{plan_id}/slots"
        payload = {
            "warehouseId": warehouse_id,
            "date": date,
            "coefficient": coefficient
        }
        
        async with aiohttp.ClientSession() as session:
            # Используем PUT или POST в зависимости от актуальной доки, 
            # сейчас WB часто использует PUT для назначения слота
            async with session.put(url, headers=self.headers, json=payload) as resp:
                if resp.status in [200, 204]:
                    logger.info(f"✅ Slot booked! Plan {plan_id}, Date {date}, Coeff {coefficient}")
                    return True
                
                text = await resp.text()
                logger.error(f"❌ Booking failed: {text}")
                return False