import logging
import asyncio
from datetime import datetime, timedelta
from wb_api.statistics import WBStatisticsAPI
from clickhouse_models import ch_service

logger = logging.getLogger("ReportLoader")

async def load_realization_reports_task(user_id: int, token: str, days: int = 90):
    """
    Задача для загрузки отчетов реализации из API WB в ClickHouse.
    """
    logger.info(f"🔄 [Sync] Starting realization report sync for user {user_id} (last {days} days)")
    try:
        api = WBStatisticsAPI(token)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        reports = await api.get_realization_reports(start_date, end_date)
        
        if not reports:
            logger.warning(f"⚠️ [Sync] No realization reports found for user {user_id}")
            return
            
        logger.info(f"📥 [Sync] Fetched {len(reports)} rows. Preparing to insert into ClickHouse...")

        # Обогащаем данные user_id (supplier_id в схеме CH)
        # Схема ClickHouse ожидает 'supplier_id' как разделитель пользователей
        for r in reports:
            r['supplier_id'] = user_id
            
            # Приводим даты к формату, который понимает драйвер (хотя обычно строки ISO ок)
            # Иногда WB присылает 'Z' в конце, иногда нет.
            
        # Вставка батчем
        ch_service.insert_reports(reports)
        logger.info(f"✅ [Sync] Successfully inserted {len(reports)} reports for user {user_id}")
        
    except Exception as e:
        logger.error(f"❌ [Sync] Failed to sync realization reports for user {user_id}: {e}", exc_info=True)