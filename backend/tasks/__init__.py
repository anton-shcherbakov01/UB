from .bidder import bidder_producer_task, bidder_consumer_task
from .finance import sync_financial_reports, train_forecasting_models, sync_product_metadata
from .seo import analyze_reviews_task, generate_seo_task, cluster_keywords_task, check_seo_position_task
from .monitoring import parse_and_save_sku, update_all_monitored_items, check_new_orders
from .utils import get_status
from .supply import sync_supply_data_task
# Добавлен импорт новой задачи
from .price_control import check_price_alerts
from .slots_sniper import sniper_check_slots 

__all__ = [
    "bidder_producer_task",
    "bidder_consumer_task",
    "sync_financial_reports",
    "train_forecasting_models",
    "sync_product_metadata",
    "analyze_reviews_task",
    "generate_seo_task",
    "cluster_keywords_task",
    "check_seo_position_task",
    "parse_and_save_sku",
    "update_all_monitored_items",
    "check_new_orders",
    "get_status",
    "sync_supply_data_task",
    "check_price_alerts",
    "sniper_check_slots", # <--- Добавлено в список экспорта
]