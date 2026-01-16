import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

# Import decomposed parts
from analysis_parts.ai import AIModule
from analysis_parts.economics import EconomicsModule
from analysis_parts.clustering import ClusteringModule
from clickhouse_models import ch_service

logger = logging.getLogger("AI-Service")

class AnalysisService:
    """
    Facade class that aggregates functional modules:
    - AIModule (LLM interactions)
    - EconomicsModule (Calculations & P&L)
    - ClusteringModule (ML)
    """
    def __init__(self):
        self.ai = AIModule()
        self.economics = EconomicsModule()
        self.clustering = ClusteringModule()
        self._ch_initialized = False
        
        # Don't connect immediately - use lazy initialization
        # Connection will be established on first use

    # --- Delegations to ClusteringModule ---
    def cluster_keywords(self, keywords: List[str]) -> Dict[str, Any]:
        return self.clustering.cluster_keywords(keywords)

    # --- Delegations to EconomicsModule ---
    def calculate_supply_metrics(
        self, 
        current_stock: int, 
        sales_history: List[Dict[str, Any]], 
        forecast_data: Optional[Dict[str, Any]] = None,
        lead_time_days: int = 7,
        lead_time_sigma: int = 2,
        service_level_z: float = 1.65
    ) -> Dict[str, Any]:
        return self.economics.calculate_supply_metrics(
            current_stock, sales_history, forecast_data, 
            lead_time_days, lead_time_sigma, service_level_z
        )

    def _ensure_ch_connection(self):
        """Lazy initialization of ClickHouse connection."""
        if not self._ch_initialized:
            try:
                ch_service.connect()
                self._ch_initialized = True
                logger.info("✅ ClickHouse connection established (lazy init)")
            except Exception as e:
                logger.warning(f"ClickHouse connection failed (will retry on usage): {e}")
                # Don't raise - allow retry on next use
    
    async def get_pnl_data(self, user_id: int, date_from: datetime, date_to: datetime, db: AsyncSession) -> List[Dict[str, Any]]:
        self._ensure_ch_connection()
        return await self.economics.get_pnl_data(user_id, date_from, date_to, db)

    def calculate_metrics(self, raw_data: dict):
        return self.economics.calculate_metrics(raw_data)

    def calculate_transit_benefit(self, volume_liters: int):
        return self.economics.calculate_transit_benefit(volume_liters)

    # --- Delegations to AIModule ---
    def clean_ai_text(self, text: str) -> str:
        return self.ai.clean_ai_text(text)

    def analyze_reviews_with_ai(self, reviews: list, product_name: str) -> Dict[str, Any]:
        return self.ai.analyze_reviews_with_ai(reviews, product_name)

    def generate_product_content(self, keywords: list, tone: str, title_len: int = 100, desc_len: int = 1000):
        return self.ai.generate_product_content(keywords, tone, title_len, desc_len)

# Singleton Instance
analysis_service = AnalysisService()