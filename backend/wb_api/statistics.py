import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .base import WBBaseClient, WBEndpoint

logger = logging.getLogger("WB-API-Stats")

class WBStatisticsMixin(WBBaseClient):

    async def get_new_orders_since(self, token: str, last_check_dt: datetime) -> List[Dict]:
        """Получение заказов с момента последней проверки"""
        # API отдает заказы по дате обновления. Берем с запасом 2 дня, фильтруем в коде.
        date_from = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S")
        
        params = {"dateFrom": date_from, "flag": 0}
        data = await self._request("GET", WBEndpoint.STATS_ORDERS.value, token, params=params)
        
        if not data:
            return []
            
        new_orders = []
        last_ts = last_check_dt.timestamp() if last_check_dt else 0
        
        for order in data:
            # lastChangeDate - строка вида 2023-01-01T12:00:00
            try:
                # Отсекаем секунды если есть доли
                date_str = order.get('lastChangeDate', '').split('.')[0] 
                order_dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S")
                if order_dt.timestamp() > last_ts:
                    new_orders.append(order)
            except ValueError:
                continue
                
        return new_orders

    async def get_stocks(self, token: str) -> List[Dict]:
        """Получение остатков"""
        date_from = datetime.now().strftime("%Y-%m-%dT00:00:00")
        params = {"dateFrom": date_from}
        return await self._request("GET", WBEndpoint.STATS_STOCKS.value, token, params=params) or []