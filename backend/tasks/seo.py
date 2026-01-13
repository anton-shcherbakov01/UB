import logging
import asyncio
from typing import List

from celery_app import celery_app
from parser_service import parser_service, GEO_ZONES
from analysis_service import analysis_service
from .utils import save_history_sync, save_seo_position_sync

logger = logging.getLogger("Tasks-SEO")

@celery_app.task(bind=True, name="analyze_reviews_task")
def analyze_reviews_task(self, sku: int, limit: int = 50, user_id: int = None):
    self.update_state(state='PROGRESS', meta={'status': 'Парсинг карточки и отзывов...'})
    
    product_info = parser_service.get_full_product_info(sku, limit)
    if product_info.get("status") == "error":
        return {"status": "error", "error": product_info.get("message")}
    
    self.update_state(state='PROGRESS', meta={'status': 'ABSA Аналитика (DeepSeek-V3)...'})
    
    reviews = product_info.get('reviews', [])
    product_name = product_info.get('name', f"Товар {sku}")
    ai_result = analysis_service.analyze_reviews_with_ai(reviews, product_name)

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
        title = f"ABSA: {product_name[:30]} ({len(reviews)} отз.)"
        save_history_sync(user_id, sku, 'ai', title, final_result)

    return final_result

@celery_app.task(bind=True, name="generate_seo_task")
def generate_seo_task(self, keywords: list, tone: str, sku: int = 0, user_id: int = None, title_len: int = 100, desc_len: int = 1000):
    self.update_state(state='PROGRESS', meta={'status': 'Генерация GEO контента...'})
    
    content = analysis_service.generate_product_content(keywords, tone, title_len, desc_len)
    
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