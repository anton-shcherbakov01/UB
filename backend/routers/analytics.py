# backend/routers/analytics.py

from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from datetime import datetime, timedelta
# Импортируем нашу функцию расчета
from analysis_parts.economics import calculate_abc_xyz 
# Импорт зависимостей БД (примерный)
from database import get_db, User, get_current_user 
from sqlalchemy import text # Или использование ORM

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

@router.get("/abc-xyz")
async def get_abc_xyz_stats(
    days: int = Query(30, ge=7, le=365),
    user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """
    Эндпоинт для получения матрицы ABC/XYZ.
    """
    # 1. Определяем диапазон дат
    date_from = datetime.now() - timedelta(days=days)
    
    # 2. SQL запрос для получения "сырых" данных: SKU, Дата, Выручка, Штуки
    # Группируем по дням, чтобы XYZ мог посчитать стабильность спроса
    query = text("""
        SELECT 
            sku, 
            date(created_at) as date, 
            SUM(price_final) as revenue, 
            SUM(quantity) as qty
        FROM orders
        WHERE user_id = :uid 
          AND created_at >= :date_from
        GROUP BY sku, date(created_at)
    """)
    
    # Выполняем запрос (синтаксис зависит от вашей ORM/Драйвера, здесь пример для SQLAlchemy)
    try:
        result = await db.execute(query, {"uid": user.id, "date_from": date_from})
        raw_data = [dict(row) for row in result.mappings().all()]
    except Exception as e:
        # Если данных нет или ошибка БД, можно вернуть пустой список для теста
        print(f"DB Error: {e}")
        raw_data = [] 

    # 3. Передаем данные в наш калькулятор
    # calculate_abc_xyz ожидает List[dict] с ключами: sku, date, revenue, qty
    analysis_result = calculate_abc_xyz(raw_data)
    
    return analysis_result