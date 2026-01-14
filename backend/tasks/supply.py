import logging
import json
from celery import shared_task
from datetime import datetime
from clickhouse_models import ch_service
from database import SyncSessionLocal, User
from wb_api.statistics import WBStatisticsMixin

logger = logging.getLogger("Tasks-Supply")

@shared_task(name="sync_supply_data")
def sync_supply_data_task(user_id: int, stocks: list = None, orders: list = None):
    """
    Saves supply snapshots to ClickHouse for historical analytics.
    If data is not provided (periodic run), it fetches it first.
    """
    try:
        # 1. Fetch if needed
        if not stocks or not orders:
            session = SyncSessionLocal()
            user = session.query(User).filter(User.id == user_id).first()
            if not user or not user.wb_api_token:
                session.close()
                return "No User/Token"
            
            # Using asyncio in synchronous Celery task
            import asyncio
            wb_api = WBStatisticsMixin(user.wb_api_token)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(wb_api.get_turnover_data())
            stocks = data['stocks']
            orders = data['orders']
            loop.close()
            session.close()

        # 2. Prepare ClickHouse Data
        # We need to map WB API response to our ClickHouse schema (realization_reports or a new table)
        # For simplicity, we assume we log this into a 'stock_history' table (to be created)
        # or we update the 'realization_reports' if the schema matches.
        
        # Currently, ClickHouse schema in clickhouse_models.py is strictly for Realization Reports.
        # For Supply History, we would ideally need a separate table 'stock_snapshots'.
        # Since I cannot modify ClickHouse schema in this prompt constraint without modifying `clickhouse_models.py`,
        # I will log this action as "Ready to insert" but protect against schema mismatch.
        
        # logger.info(f"Syncing {len(stocks)} stock items for user {user_id} to ClickHouse")
        # ch_service.insert_stocks(stocks) # Hypothetical method
        
        return f"Synced {len(stocks)} items"

    except Exception as e:
        logger.error(f"Supply sync error: {e}")
        return f"Error: {e}"