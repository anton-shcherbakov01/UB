import random
from datetime import datetime, timedelta
from typing import List, Dict, Any

class MockService:
    """
    Генератор красивых фейковых данных для Демо-режима.
    """
    
    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Фейковая сводка для главной"""
        return {
            "status": "success",
            "header": {
                "balance": 452890,
                "orders_count": 142,
                "growth": True
            },
            "stories": [
                {"id": 1, "title": "Динамика", "val": "+18%", "color": "bg-gradient-to-tr from-emerald-400 to-teal-500", "icon": "trending-up", "details": "Отличный рост! Вчера было на 18% меньше."},
                {"id": 2, "title": "Ср. чек", "val": "3189₽", "color": "bg-gradient-to-tr from-blue-400 to-indigo-500", "icon": "wallet", "details": "Средний чек вырос за счет допродаж."},
                {"id": 3, "title": "Хит", "val": "12500₽", "color": "bg-gradient-to-tr from-amber-400 to-orange-500", "icon": "star", "details": "Топ продаж: Платье вечернее черное."}
            ],
            "last_updated": datetime.now().strftime("%H:%M")
        }

    def get_pnl_data(self, days: int = 30) -> List[Dict[str, Any]]:
        """Фейковый P&L отчет (График прибыли)"""
        data = []
        now = datetime.now()
        
        # Генерируем красивый растущий тренд с небольшими просадками
        base_revenue = 50000
        
        for i in range(days):
            date = (now - timedelta(days=days-i-1))
            date_str = date.strftime("%Y-%m-%d")
            
            # Симуляция волн продаж
            factor = 1 + (math.sin(i / 3) * 0.2) + (random.uniform(-0.1, 0.1))
            revenue = base_revenue * factor * (1 + i/100) # Небольшой рост к концу
            
            net_sales = revenue * 0.85
            cogs = revenue * 0.30
            logistics = revenue * 0.15
            commission = revenue * 0.10
            tax = revenue * 0.06
            penalties = 0 if random.random() > 0.1 else random.randint(100, 5000)
            
            cm3 = net_sales - logistics - penalties - cogs - tax
            
            data.append({
                "date": date_str,
                "gross_sales": int(revenue),
                "net_sales": int(net_sales),
                "cogs": int(cogs),
                "commission": int(commission),
                "logistics": int(logistics),
                "penalties": int(penalties),
                "adjustments": 0,
                "tax": int(tax),
                "cm3": int(cm3)
            })
            
        return data

    def get_funnel(self, days: int = 30) -> Dict[str, Any]:
        """Фейковая воронка продаж"""
        chart = []
        visitors_total = 0
        orders_total = 0
        
        now = datetime.now()
        for i in range(days):
            date = (now - timedelta(days=days-i-1)).strftime("%Y-%m-%d")
            vis = random.randint(3000, 5000) + (i * 50)
            ord_count = int(vis * random.uniform(0.03, 0.05)) # 3-5% конверсия
            
            chart.append({
                "date": date,
                "visitors": vis,
                "cart": int(vis * 0.15),
                "orders": ord_count,
                "orders_sum": ord_count * 2500
            })
            visitors_total += vis
            orders_total += ord_count

        return {
            "period": f"{days} дн.",
            "totals": {
                "visitors": visitors_total,
                "cart": int(visitors_total * 0.15),
                "orders": orders_total,
                "buyouts": int(orders_total * 0.90),
                "revenue": orders_total * 2500,
                "buyouts_revenue": int(orders_total * 0.90 * 2500)
            },
            "conversions": {
                "view_to_cart": 15.0,
                "cart_to_order": 25.0,
                "order_to_buyout": 90.0
            },
            "chart": chart,
            "is_exact": True
        }

    def get_unit_economy(self) -> List[Dict[str, Any]]:
        """Фейковые товары для Юнит-экономики"""
        return [
            {
                "sku": 12345678,
                "quantity": 450,
                "price_structure": {"basic": 5000, "discount": 40, "selling": 3000},
                "cost_price": 1000,
                "logistics": 80,
                "commission_percent": 19,
                "unit_economy": {"profit": 1150, "roi": 115, "margin": 38},
                "supply": {"status": "ok", "recommendation": "Запаса достаточно"},
                "meta": {"photo": "https://basket-05.wbbasket.ru/vol777/part77777/77777777/images/c246x328/1.webp", "name": "Платье женское вечернее", "brand": "JuicyBrand"}
            },
            {
                "sku": 87654321,
                "quantity": 12,
                "price_structure": {"basic": 2000, "discount": 50, "selling": 1000},
                "cost_price": 600,
                "logistics": 50,
                "commission_percent": 25,
                "unit_economy": {"profit": 50, "roi": 8, "margin": 5},
                "supply": {"status": "critical", "recommendation": "Срочно пополнить!"},
                "meta": {"photo": "https://basket-05.wbbasket.ru/vol777/part77777/77777778/images/c246x328/1.webp", "name": "Футболка базовая", "brand": "JuicyBrand"}
            }
        ]

import math
# Создаем синглтон
mock_service = MockService()