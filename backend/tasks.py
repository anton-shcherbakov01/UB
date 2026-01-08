from celery_app import celery_app
from parser_service import parser_service
from analysis_service import analysis_service
import logging

logger = logging.getLogger("CeleryWorker")

@celery_app.task(bind=True, name="parse_sku")
def parse_sku_task(self, sku: int):
    """
    Асинхронная задача парсинга.
    Self дает доступ к состоянию задачи (чтобы обновлять прогресс).
    """
    logger.info(f"Начинаю обработку SKU: {sku}")
    
    # Можно обновлять статус, чтобы пользователь видел "Парсим..."
    self.update_state(state='PROGRESS', meta={'status': 'Запуск браузера...'})
    
    # Вызов тяжелого парсера
    raw_result = parser_service.get_product_data(sku)
    
    if raw_result.get("status") == "error":
        # Если ошибка, выбрасываем исключение или возвращаем ошибку
        return {"status": "error", "error": raw_result.get("message")}
    
    self.update_state(state='PROGRESS', meta={'status': 'Анализ цен...'})
    
    # Анализ данных
    final_result = analysis_service.calculate_metrics(raw_result)
    
    return final_result