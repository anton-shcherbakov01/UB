import logging
import pandas as pd
from prophet import Prophet
from typing import List, Dict, Any, Optional

logger = logging.getLogger("ForecastingService")

# Отключаем лишний шум от Prophet/Stan
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)
logging.getLogger("prophet").setLevel(logging.ERROR)

def forecast_demand(
    sales_history: List[Dict[str, Any]], 
    horizon_days: int = 30
) -> Dict[str, Any]:
    """
    Прогнозирование спроса с использованием Facebook Prophet.
    
    :param sales_history: Список словарей [{'date': 'YYYY-MM-DD', 'qty': int}, ...]
    :param horizon_days: Горизонт прогноза в днях
    :return: Словарь с прогнозом и метриками качества
    """
    if not sales_history or len(sales_history) < 14:
        # Если истории слишком мало (< 2 недель), возвращаем наивный прогноз или ошибку
        return {
            "status": "error", 
            "message": "Not enough data (min 14 days required)"
        }

    try:
        # 1. Подготовка данных для Prophet (ds, y)
        df = pd.DataFrame(sales_history)
        df['ds'] = pd.to_datetime(df['date'])
        df['y'] = df['qty']
        
        # Убираем выбросы (простейшая фильтрация отрицательных продаж, если это возвраты)
        # В идеале возвраты надо обрабатывать отдельно, но для MVP считаем чистые продажи
        df = df[df['y'] >= 0]

        # 2. Инициализация и настройка модели
        # weekly_seasonality=True: для ритейла важно (выходные vs будни)
        # daily_seasonality=False: у нас данные по дням
        m = Prophet(
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality='auto', # Включится автоматически, если данных > 1 года
            interval_width=0.95, # Доверительный интервал 95%
        )

        # 3. Добавление праздников РФ
        m.add_country_holidays(country_name='RU')

        # 4. Обучение
        m.fit(df)

        # 5. Создание фрейма для прогноза
        future = m.make_future_dataframe(periods=horizon_days)
        
        # 6. Прогноз
        forecast = m.predict(future)

        # 7. Пост-обработка результатов
        # Нам нужны только будущие значения (последние horizon_days)
        future_forecast = forecast.tail(horizon_days)
        
        # Prophet может выдавать отрицательные значения (yhat < 0) при падении тренда,
        # но спрос не может быть отрицательным. Клиппим нулем.
        result_points = []
        total_forecast_sum = 0.0

        for _, row in future_forecast.iterrows():
            yhat = max(0, row['yhat'])
            yhat_lower = max(0, row['yhat_lower'])
            yhat_upper = max(0, row['yhat_upper'])
            
            result_points.append({
                "date": row['ds'].strftime("%Y-%m-%d"),
                "yhat": round(yhat, 2),
                "yhat_lower": round(yhat_lower, 2),
                "yhat_upper": round(yhat_upper, 2)
            })
            total_forecast_sum += yhat

        return {
            "status": "success",
            "forecast_points": result_points,
            "total_forecast_qty": round(total_forecast_sum, 0),
            "daily_avg_forecast": round(total_forecast_sum / horizon_days, 2)
        }

    except Exception as e:
        logger.error(f"Prophet forecasting failed: {e}")
        return {"status": "error", "message": str(e)}