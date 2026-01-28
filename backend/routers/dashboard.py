from fastapi import APIRouter, Depends
from datetime import datetime, timedelta
import time
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db, User
from dependencies import get_current_user
from wb_api.statistics import WBStatisticsAPI
from mock_service import mock_service

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# Простой кэш в оперативной памяти: {user_id: {"data": dict, "timestamp": float}}
_dashboard_cache = {}
CACHE_TTL = 300  # 5 минут (в секундах)

@router.get("/summary")
async def get_dashboard_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not user.wb_api_token:
        return {"status": "no_token"}
    
    if user.wb_api_token == "DEMO":
        return mock_service.get_dashboard_summary()

    # 1. Проверяем кэш
    current_time = time.time()
    if user.id in _dashboard_cache:
        cached_entry = _dashboard_cache[user.id]
        # Если прошло меньше 5 минут, отдаем из памяти
        if current_time - cached_entry["timestamp"] < CACHE_TTL:
            return cached_entry["data"]

    try:
        stats_api = WBStatisticsAPI(user.wb_api_token)
        
        # Запрашиваем данные (тяжелый запрос)
        orders = await stats_api.get_orders(days=3) 
        
        if not isinstance(orders, list): orders = []

        today_str = datetime.now().strftime("%Y-%m-%d")
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        def get_price(item):
            val = item.get('priceWithDiscount')
            if val is not None: return float(val)
            return float(item.get('totalPrice', 0)) * (1 - float(item.get('discountPercent', 0))/100)

        orders_today = [o for o in orders if o.get('date', '').startswith(today_str) and not o.get('isCancel')]
        orders_yesterday = [o for o in orders if o.get('date', '').startswith(yesterday_str) and not o.get('isCancel')]
        
        sum_today = sum(get_price(x) for x in orders_today)
        sum_yesterday = sum(get_price(x) for x in orders_yesterday)
        count_today = len(orders_today)

        # Логика историй
        diff_percent = 0
        if sum_yesterday > 0:
            diff_percent = int(((sum_today - sum_yesterday) / sum_yesterday) * 100)

        stories = []
        
        # Story 1: Динамика
        stories.append({
            "id": 1, 
            "title": "Динамика", 
            "val": f"{'+' if diff_percent > 0 else ''}{diff_percent}%", 
            "color": "bg-gradient-to-tr from-emerald-400 to-teal-500" if diff_percent >= 0 else "bg-rose-500", 
            "icon": "trending-up" if diff_percent >= 0 else "trending-down",
            "details": f"Вчера было {int(sum_yesterday)}₽. {'Мы растем!' if diff_percent >=0 else 'Нужно поднажать.'}"
        })

        # Story 2: Средний чек
        avg_check = int(sum_today / count_today) if count_today > 0 else 0
        stories.append({
            "id": 2, 
            "title": "Ср. чек", 
            "val": f"{avg_check}₽", 
            "color": "bg-gradient-to-tr from-blue-400 to-indigo-500", 
            "icon": "wallet",
            "details": "Средняя стоимость одного заказа сегодня."
        })

        # Story 3: Хит
        if orders_today:
            top = max(orders_today, key=lambda x: get_price(x))
            stories.append({
                "id": 3, "title": "Хит", "val": f"{int(get_price(top))}₽", 
                "color": "bg-gradient-to-tr from-amber-400 to-orange-500", "icon": "star",
                "details": "Самый дорогой заказ за сегодня."
            })

        msk_time = datetime.utcnow() + timedelta(hours=3)

        result = {
            "status": "success",
            "header": {
                "balance": int(sum_today),
                "orders_count": count_today,
                "growth": sum_today >= sum_yesterday
            },
            "stories": stories,
            "last_updated": msk_time.strftime("%H:%M")
        }

        # Сохраняем в кэш
        _dashboard_cache[user.id] = {
            "data": result,
            "timestamp": current_time
        }

        return result

    except Exception as e:
        print(f"Dashboard Error: {e}")
        return {"status": "error", "message": str(e), "header": {"balance": 0, "orders_count": 0}, "stories": []}