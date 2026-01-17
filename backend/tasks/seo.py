import logging
import asyncio
from typing import List

from celery_app import celery_app
from parser_service import parser_service, GEO_ZONES
from analysis_service import analysis_service
from services.queue_service import queue_service
from .utils import save_history_sync, save_seo_position_sync

logger = logging.getLogger("Tasks-SEO")

@celery_app.task(bind=True, name="analyze_reviews_task")
def analyze_reviews_task(self, sku: int, limit: int = 50, user_id: int = None):
    try:
        self.update_state(state='PROGRESS', meta={'status': 'Парсинг карточки и отзывов...'})
        
        try:
            product_info = parser_service.get_full_product_info(sku, limit)
        except Exception as parse_error:
            logger.error(f"Product parsing exception for SKU {sku}: {parse_error}", exc_info=True)
            return {"status": "error", "error": f"Ошибка парсинга товара: {str(parse_error)}"}
        
        if not product_info:
            logger.error(f"Product info is None for SKU {sku}")
            return {"status": "error", "error": "Не удалось получить данные о товаре"}
        
        if product_info.get("status") == "error":
            error_msg = product_info.get("message", "Ошибка парсинга товара")
            logger.error(f"Product parsing error for SKU {sku}: {error_msg}")
            return {"status": "error", "error": error_msg}
        
        self.update_state(state='PROGRESS', meta={'status': 'ABSA Аналитика (DeepSeek-V3)...'})
        
        reviews = product_info.get('reviews', [])
        if not isinstance(reviews, list):
            logger.warning(f"Reviews is not a list for SKU {sku}, got {type(reviews)}")
            reviews = []
        
        product_name = product_info.get('name', f"Товар {sku}")
        
        try:
            ai_result = analysis_service.analyze_reviews_with_ai(reviews, product_name)
        except Exception as ai_error:
            logger.error(f"AI analysis exception for SKU {sku}: {ai_error}", exc_info=True)
            ai_result = {
                "_error": f"Ошибка AI анализа: {str(ai_error)}",
                "aspects": [],
                "audience_stats": {"rational_percent": 0, "emotional_percent": 0, "skeptic_percent": 0},
                "global_summary": "Ошибка при анализе отзывов",
                "strategy": []
            }

        # Проверяем наличие ошибки в AI ответе
        if ai_result.get("_error"):
            logger.error(f"AI analysis error for SKU {sku}: {ai_result['_error']}")
            # Не прерываем выполнение, но пометим в результате

        final_result = {
            "status": "success",
            "sku": sku,
            "product_name": product_name,
            "image": product_info.get('image'),
            "rating": product_info.get('rating'),
            "reviews_count": len(reviews),
            "ai_analysis": ai_result
        }

        if user_id:
            try:
                title = f"ABSA: {product_name[:30]} ({len(reviews)} отз.)"
                save_history_sync(user_id, sku, 'ai', title, final_result)
            except Exception as save_error:
                logger.error(f"Failed to save history for SKU {sku}, user {user_id}: {save_error}", exc_info=True)
                # Не прерываем выполнение, результат все равно возвращаем
        
        # Remove task from queue after successful completion
        try:
            queue_service.remove_task_from_queue(self.request.id)
        except Exception as queue_e:
            logger.warning(f"Error removing task from queue: {queue_e}")

        return final_result
    except Exception as e:
        logger.error(f"Analyze reviews task error for SKU {sku}: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}

@celery_app.task(bind=True, name="generate_seo_task")
def generate_seo_task(self, keywords: list, tone: str, sku: int = 0, user_id: int = None, title_len: int = 100, desc_len: int = 1000):
    try:
        self.update_state(state='PROGRESS', meta={'status': 'Генерация GEO контента...'})
        
        content = analysis_service.generate_product_content(keywords, tone, title_len, desc_len)
        
        # Проверяем наличие ошибки в AI ответе
        if content.get("_error"):
            logger.error(f"AI generation error: {content['_error']}")
            # Не прерываем выполнение, но информация об ошибке будет в результате
        
        final_result = {
            "status": "success",
            "sku": sku,
            "keywords": keywords,
            "tone": tone,
            "generated_content": content 
        }
        
        if user_id and sku > 0:
            title = f"GEO: {content.get('title', 'Без заголовка')[:20]}..."
            save_history_sync(user_id, sku, 'seo', title, final_result)
            
        return final_result
    except Exception as e:
        logger.error(f"Generate SEO task error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}

@celery_app.task(bind=True, name="cluster_keywords_task")
def cluster_keywords_task(self, keywords: List[str], user_id: int = None, sku: int = 0):
    self.update_state(state='PROGRESS', meta={'status': 'Загрузка BERT модели...'})
    
    result = analysis_service.cluster_keywords(keywords)
    
    if user_id and sku > 0:
        title = f"Clusters: {len(keywords)} keys ({result.get('n_clusters', 0)} groups)"
        save_history_sync(user_id, sku, 'clusters', title, result)
        
    return result

@celery_app.task(bind=True, name="check_seo_position_task")
def check_seo_position_task(self, sku: int, keyword: str, user_id: int, regions: List[str] = None):
    self.update_state(state='PROGRESS', meta={'status': 'Geo Tracking...'})
    if not regions: regions = ["moscow"]

    async def check_all_regions():
        tasks = []
        for reg_name in regions:
            dest_id = GEO_ZONES.get(reg_name.lower(), GEO_ZONES["moscow"])
            tasks.append(parser_service.get_search_position_v2(keyword, sku, dest=dest_id))
        return await asyncio.gather(*tasks)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(check_all_regions())
        loop.close()
        
        main_result = results[0]
        db_position = main_result["organic_pos"]
        save_seo_position_sync(user_id, sku, keyword, db_position)
        
        detailed_report = {}
        for reg, res in zip(regions, results): detailed_report[reg] = res

        return {"status": "success", "sku": sku, "keyword": keyword, "main_position": db_position, "geo_details": detailed_report}

    except Exception as e:
        logger.error(f"SEO Check Task Error: {e}")
        return {"status": "error", "message": str(e)}