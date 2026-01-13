import aiohttp
import asyncio
from typing import Optional, Dict, Any

class BasketFinder:
    @staticmethod
    def _calc_basket_static(sku: int) -> str:
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
        return "18"

    async def _check_url(self, session, url, host, sku):
        try:
            async with session.get(url, timeout=1.5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    vol = url.split('vol')[1].split('/')[0]
                    part = url.split('part')[1].split('/')[0]
                    data['image_url'] = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/images/c246x328/1.webp"
                    return data
        except:
            pass
        return None

    async def find_card_json(self, sku: int) -> Optional[Dict[str, Any]]:
        """Поиск card.json brute-force методом (до 50 корзины)"""
        vol = sku // 100000
        part = sku // 1000
        
        calc_host = self._calc_basket_static(sku)
        
        # Приоритет: расчетный хост -> новые хосты (18-50) -> старые (1-17)
        hosts_priority = [calc_host] + [f"{i:02d}" for i in range(18, 51)] + [f"{i:02d}" for i in range(1, 18)]
        hosts = list(dict.fromkeys(hosts_priority)) 

        async with aiohttp.ClientSession() as session:
            # Батчинг запросов по 15 штук
            for i in range(0, len(hosts), 15):
                batch = hosts[i:i+15]
                tasks = []
                for host in batch:
                    url = f"https://basket-{host}.wbbasket.ru/vol{vol}/part{part}/{sku}/info/ru/card.json"
                    tasks.append(self._check_url(session, url, host, sku))
                
                results = await asyncio.gather(*tasks)
                for res in results:
                    if res: return res
        return None