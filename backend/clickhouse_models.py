import os
import logging
import clickhouse_connect
from datetime import datetime

logger = logging.getLogger("ClickHouse")

class ClickHouseService:
    def __init__(self):
        self.host = os.getenv("CLICKHOUSE_HOST", "clickhouse")
        self.port = int(os.getenv("CLICKHOUSE_PORT", 8123))
        self.user = os.getenv("CLICKHOUSE_USER", "default")
        self.password = os.getenv("CLICKHOUSE_PASSWORD", "")
        self.database = os.getenv("CLICKHOUSE_DB", "wb_analytics")
        self.client = None

    def connect(self, retry_count=3, retry_delay=5):
        """Establishes connection to ClickHouse and ensures DB exists."""
        import time
        
        last_error = None
        for attempt in range(1, retry_count + 1):
            try:
                self.client = clickhouse_connect.get_client(
                    host=self.host,
                    port=self.port,
                    username=self.user,
                    password=self.password,
                    connect_timeout=10
                )
                # Test connection with a simple query
                self.client.command("SELECT 1")
                # Create DB if not exists
                self.client.command(f"CREATE DATABASE IF NOT EXISTS {self.database}")
                self.init_schema()
                logger.info("✅ ClickHouse connected and schema initialized.")
                return
            except Exception as e:
                last_error = e
                if attempt < retry_count:
                    logger.warning(f"⚠️ ClickHouse connection attempt {attempt}/{retry_count} failed: {e}. Retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"❌ ClickHouse connection failed after {retry_count} attempts: {e}")
                    # Don't raise - allow retry on next call
                    self.client = None
        
        # If all retries failed, raise the last error
        if last_error:
            raise last_error

    def get_client(self):
        """Get ClickHouse client, connecting if necessary."""
        if not self.client:
            try:
                self.connect()
            except Exception as e:
                logger.warning(f"ClickHouse connection failed (will retry on next use): {e}")
                # Return None to indicate connection is not available
                # This allows graceful degradation
                return None
        return self.client

    def init_schema(self):
        """
        Defines the High-Performance OLAP Schema.
        Mirrors WB API v5 /supplier/reportDetailByPeriod.
        Engine: ReplacingMergeTree for deduplication/updates based on rrd_id.
        """
        schema_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.database}.realization_reports (
            -- Identity & Meta
            rrd_id UInt64, -- Unique row ID from WB
            realizationreport_id UInt64, -- Report ID
            supplier_id UInt64, -- Internal User ID (Tenancy)
            
            -- Dimensions (LowCardinality for compression)
            gi_id UInt64,
            subject_name LowCardinality(String), -- Category
            nm_id UInt64, -- SKU
            brand_name LowCardinality(String),
            sa_name String, -- Article
            ts_name String, -- Size
            barcode String,
            doc_type_name LowCardinality(String), -- 'Продажа', 'Возврат'
            office_name LowCardinality(String), -- Warehouse
            supplier_oper_name LowCardinality(String),
            site_country LowCardinality(String),
            
            -- Dates
            create_dt DateTime,
            order_dt DateTime,
            sale_dt DateTime,
            rr_dt DateTime,
            
            -- Metrics (Decimal for Money)
            quantity UInt32,
            retail_price Decimal(18, 2),
            retail_amount Decimal(18, 2),
            sale_percent UInt16,
            commission_percent Decimal(10, 2),
            retail_price_withdisc_rub Decimal(18, 2), -- Actual Revenue
            delivery_amount UInt32,
            return_amount UInt32,
            delivery_rub Decimal(18, 2), -- Logistics Cost
            gi_box_type_name LowCardinality(String),
            product_discount_for_report Decimal(10, 2),
            supplier_promo Decimal(10, 2),
            rid UInt64,
            ppvz_spp_prc Decimal(10, 2),
            ppvz_kvw_prc_base Decimal(10, 2),
            ppvz_kvw_prc Decimal(10, 2),
            sup_rating_prc_up Decimal(10, 2),
            is_kgvp_v2 UInt8,
            ppvz_sales_commission Decimal(18, 2), -- WB Commission
            ppvz_for_pay Decimal(18, 2),
            ppvz_reward Decimal(18, 2),
            acquiring_fee Decimal(18, 2),
            acquiring_bank String,
            ppvz_vw Decimal(18, 2),
            ppvz_vw_nds Decimal(18, 2),
            ppvz_office_id UInt64,
            penalty Decimal(18, 2), -- Fines
            additional_payment Decimal(18, 2),
            rebill_logistic_cost Decimal(18, 2),
            
            -- Versioning
            inserted_at DateTime DEFAULT now()
        ) 
        ENGINE = ReplacingMergeTree(inserted_at)
        ORDER BY (supplier_id, toDate(sale_dt), nm_id, rrd_id)
        TTL sale_dt + INTERVAL 3 YEAR;
        """
        self.client.command(schema_sql)

    def insert_reports(self, reports: list):
        """Batch insert raw reports."""
        if not reports:
            return
        
        # Ensure we use the connected client
        client = self.get_client()
        if not client:
            logger.warning("ClickHouse client not available, skipping insert")
            return
        
        # Columns must match the Create Table order/structure
        # In production, use Pandas DataFrame for faster inserts, but here we use native list
        # We assume 'reports' is a list of dictionaries matching the DB columns
        try:
            client.insert(
                f"{self.database}.realization_reports",
                reports,
                column_names=[k for k in reports[0].keys()]
            )
        except Exception as e:
            logger.error(f"ClickHouse Insert Error: {e}")
            # Reset client to force reconnection on next use
            self.client = None
            raise e

# Singleton instance
ch_service = ClickHouseService()