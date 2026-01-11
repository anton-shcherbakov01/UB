import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from prophet import Prophet

logger = logging.getLogger("Forecasting")

def forecast_demand(sales_history: List[int], horizon_days: int = 30) -> Dict:
    """
    Генерирует прогноз спроса используя Facebook Prophet.
    
    Args:
        sales_history: Список продаж (int) за последние N дней (от старых к новым).
                       Предполагается, что последний элемент - это "вчера" или "сегодня".
        horizon_days: На сколько дней вперед строить прогноз.
        
    Returns:
        Dict: {
            "forecast_value": float, (сумма прогноза на горизонт)
            "daily_forecast": List[Dict], (детализация по дням)
            "sigma": float (стандартное отклонение остатков/прогноза для расчета SS)
        }
    """
    # 1. Проверка данных
    # Prophet требует минимум 2 точки, но для адекватности нужно хотя бы 14-30 дней
    if not sales_history or len(sales_history) < 14:
        logger.warning(f"Not enough data for Prophet ({len(sales_history)} days). Fallback to mean.")
        avg = sum(sales_history) / len(sales_history) if sales_history else 0
        return {
            "forecast_avg_daily": avg,
            "forecast_total": avg * horizon_days,
            "sigma": avg * 0.5, # Грубая эвристика, если данных мало
            "status": "fallback"
        }

    try:
        # 2. Подготовка DataFrame для Prophet (ds, y)
        # Генерируем даты назад от сегодняшнего дня
        today = datetime.now().date()
        dates = [today - timedelta(days=i) for i in range(len(sales_history), 0, -1)]
        
        df = pd.DataFrame({
            'ds': dates,
            'y': sales_history
        })

        # 3. Настройка модели
        # yearly_seasonality=False (если истории < 1 года), weekly=True (важно для WB)
        m = Prophet(
            daily_seasonality=False,
            weekly_seasonality=True, 
            yearly_seasonality=len(sales_history) > 365,
            interval_width=0.95 # 95% доверительный интервал
        )
        
        # Добавляем праздники РФ (важно для гендерных праздников, НГ)
        m.add_country_holidays(country_name='RU')

        # 4. Обучение
        m.fit(df)

        # 5. Прогноз
        future = m.make_future_dataframe(periods=horizon_days)
        forecast = m.predict(future)

        # Выделяем только будущий период
        future_forecast = forecast.tail(horizon_days)
        
        # Расчет метрик
        forecast_total = future_forecast['yhat'].sum()
        forecast_avg_daily = future_forecast['yhat'].mean()
        
        # Оценка неопределенности (sigma) для Safety Stock
        # Можно взять среднее ширины доверительного интервала или std прошлых остатков
        # Здесь берем вариативность прогноза как прокси риска
        sigma = future_forecast['yhat'].std()
        if pd.isna(sigma) or sigma == 0:
            sigma = forecast_avg_daily * 0.2

        # Формируем ответ
        daily_details = []
        for _, row in future_forecast.iterrows():
            daily_details.append({
                "date": row['ds'].strftime("%Y-%m-%d"),
                "yhat": max(0, row['yhat']), # Не может быть отрицательных продаж
                "yhat_lower": max(0, row['yhat_lower']),
                "yhat_upper": max(0, row['yhat_upper'])
            })

        return {
            "forecast_total": max(0, forecast_total),
            "forecast_avg_daily": max(0, forecast_avg_daily),
            "sigma": sigma,
            "daily_forecast": daily_details,
            "status": "success"
        }

    except Exception as e:
        logger.error(f"Prophet error: {e}")
        # Fallback
        avg = sum(sales_history) / len(sales_history) if sales_history else 0
        return {
            "forecast_avg_daily": avg,
            "forecast_total": avg * horizon_days,
            "sigma": avg * 0.5,
            "status": "error"
        }