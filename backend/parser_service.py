import asyncio
from parser_parts.config import GEO_ZONES, logger
from parser_parts.product import ProductParser
from parser_parts.search import SearchParser

# Re-export GEO_ZONES for compatibility
__all__ = ["parser_service", "GEO_ZONES"]

class SeleniumWBParser:
    """
    Фасад для микросервиса парсинга Wildberries.
    Делегирует задачи специализированным модулям в parser_parts.
    """
    def __init__(self):
        self.product_parser = ProductParser()
        self.search_parser = SearchParser()

    def get_product_data(self, sku: int):
        """Парсинг цен и остатков (Sync wrapper for Celery)"""
        return self.product_parser.get_product_data(sku)

    def get_full_product_info(self, sku: int, limit: int = 50):
        """Парсинг отзывов и деталей"""
        return self.product_parser.get_full_product_info(sku, limit)

    async def get_seo_data(self, sku: int):
        """Парсинг ключевых слов (Async)"""
        return await self.product_parser.get_seo_data(sku)

    async def get_search_position_v2(self, query: str, target_sku: int, dest: str = GEO_ZONES["moscow"]):
        """Гибридный поиск позиции (Async)"""
        return await self.search_parser.get_search_position_v2(query, target_sku, dest)

    def get_search_position(self, query: str, target_sku: int):
        """Legacy Sync Wrapper для поиска"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.get_search_position_v2(query, target_sku))
            loop.close()
            return result["organic_pos"] if result["organic_pos"] > 0 else (result["ad_pos"] if result["ad_pos"] > 0 else 0)
        except Exception as e:
            logger.error(f"Legacy Search Error: {e}")
            return 0

# Singleton Instance
parser_service = SeleniumWBParser()