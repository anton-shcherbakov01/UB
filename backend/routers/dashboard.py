from fastapi import APIRouter, Depends
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db, User
from dependencies import get_current_user
from wb_api.statistics import WBStatisticsAPI # Предполагаем наличие этого класса из ваших файлов
from wb_api.promotion import WBPromotionMixin

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/summary")
async def get_dashboard_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    if not user.wb_api_token:
        return {"status": "no_token"}

    # Инициализация API клиентов
    stats_api = WBStatisticsAPI(user.wb_api_token)
    # Предполагаем, что миксины подключены к сервису, здесь упрощенная логика
    
    # 1. Получаем заказы и продажи за сегодня и вчера
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    
    # В реальном коде лучше кэшировать этот тяжелый запрос
    orders = await stats_api.get_orders(days=2) 
    sales = await stats_api.get_sales(days=30) # Для расчета % выкупа берем месяц
    
    # Фильтрация данных
    orders_today = [o for o in orders if o['date'].startswith(str(today)) and not o.get('isCancel')]
    orders_yesterday = [o for o in orders if o['date'].startswith(str(yesterday)) and not o.get('isCancel')]
    
    # Расчет метрик
    sum_today = sum(x['priceWithDiscount'] for x in orders_today)
    count_today = len(orders_today)
    
    sum_yesterday = sum(x['priceWithDiscount'] for x in orders_yesterday)
    
    # Расчет выкупа (Buyout Rate) за 30 дней
    total_orders_30 = len(orders) # Упрощенно, если get_orders возвращает 30 дней
    total_sales_30 = len(sales)
    buyout_rate = round((total_sales_30 / total_orders_30 * 100), 1) if total_orders_30 > 0 else 0

    # 2. Генерация "Историй" (Stories) на основе данных
    stories = []
    
    # История 1: Пульс продаж
    if sum_today > sum_yesterday:
        stories.append({
            "id": 1, "title": "Рост", "val": f"+{int(((sum_today - sum_yesterday)/sum_yesterday)*100)}%", 
            "color": "bg-gradient-to-tr from-emerald-400 to-teal-500", "icon": "trending-up"
        })
    else:
        stories.append({
            "id": 1, "title": "Динамика", "val": "Спад", 
            "color": "bg-slate-200", "icon": "trending-down"
        })

    # История 2: Выкуп
    stories.append({
        "id": 2, "title": "Выкуп", "val": f"{buyout_rate}%", 
        "color": "bg-gradient-to-tr from-violet-500 to-purple-500", "icon": "percent"
    })

    # История 3: Топ товар
    if orders_today:
        top_item = max(orders_today, key=lambda x: x['priceWithDiscount'])
        stories.append({
            "id": 3, "title": "Хит дня", "val": f"{int(top_item['priceWithDiscount'])}₽", 
            "color": "bg-gradient-to-tr from-amber-400 to-orange-500", "icon": "star"
        })

    return {
        "status": "success",
        "header": {
            "balance": int(sum_today),
            "orders_count": count_today,
            "growth": sum_today > sum_yesterday
        },
        "cards": [
            {"label": "Заказы сегодня", "value": count_today, "sub": "шт", "color": "blue"},
            {"label": "Сумма заказов", "value": f"{int(sum_today):,}".replace(',', ' '), "sub": "₽", "color": "emerald"},
            {"label": "Процент выкупа", "value": buyout_rate, "sub": "%", "color": "violet"},
            {"label": "Логистика (est)", "value": count_today * 50, "sub": "₽", "color": "slate"} # Примерный расчет
        ],
        "stories": stories,
        "last_updated": datetime.now().strftime("%H:%M")
    }