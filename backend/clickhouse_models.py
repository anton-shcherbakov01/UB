import os
import logging
import clickhouse_connect
from datetime import datetime

logger = logging.getLogger("ClickHouse")

class ClickHouseService:
    # --- ДОБАВЛЕНО: Белый список колонок для защиты от лишних полей API ---
    VALID_COLUMNS = {
        'rrd_id', 'realizationreport_id', 'supplier_id', 
        'gi_id', 'subject_name', 'nm_id', 'brand_name', 'sa_name', 'ts_name', 'barcode', 
        'doc_type_name', 'office_name', 'supplier_oper_name', 'site_country', 
        'create_dt', 'order_dt', 'sale_dt', 'rr_dt', 
        'quantity', 'retail_price', 'retail_amount', 'sale_percent', 'commission_percent', 
        'retail_price_withdisc_rub', 'delivery_amount', 'return_amount', 'delivery_rub', 
        'gi_box_type_name', 'product_discount_for_report', 'supplier_promo', 'rid', 
        'ppvz_spp_prc', 'ppvz_kvw_prc_base', 'ppvz_kvw_prc', 'sup_rating_prc_up', 
        'is_kgvp_v2', 'ppvz_sales_commission', 'ppvz_for_pay', 'ppvz_reward', 
        'acquiring_fee', 'acquiring_bank', 'ppvz_vw', 'ppvz_vw_nds', 'ppvz_office_id', 
        'penalty', 'additional_payment', 'rebill_logistic_cost'
    }
    
    # Столбцы, требующие преобразования в datetime
    DATE_COLUMNS = {'create_dt', 'order_dt', 'sale_dt', 'rr_dt'}
    # ----------------------------------------------------------------------

    def __init__(self):
        self.host = os.getenv("CLICKHOUSE_HOST", "clickhouse")
        self.port = int(os.getenv("CLICKHOUSE_PORT", 8123))
        self.user = os.getenv("CLICKHOUSE_USER", "default")
        self.password = os.getenv("CLICKHOUSE_PASSWORD", "")
        self.database = os.getenv("CLICKHOUSE_DB", "wb_analytics")
        self.client = None
        self._last_connect_attempt = None
        self._connect_backoff_seconds = 60  # Don't retry connection more often than once per minute
        
        # #region agent log
        import json
        try:
            with open('c:\\Projects\\UB\\.cursor\\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "A",
                    "location": "clickhouse_models.py:18",
                    "message": "ClickHouseService __init__",
                    "data": {
                        "host": self.host,
                        "port": self.port,
                        "user": self.user,
                        "database": self.database,
                        "password_set": bool(self.password)
                    },
                    "timestamp": int(__import__('time').time() * 1000)
                }) + '\n')
        except: pass
        # #endregion

    def connect(self, retry_count=3, retry_delay=5):
        """Establishes connection to ClickHouse and ensures DB exists."""
        import time
        import json
        
        # #region agent log
        try:
            with open('c:\\Projects\\UB\\.cursor\\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "B",
                    "location": "clickhouse_models.py:19",
                    "message": "connect() called",
                    "data": {"host": self.host, "port": self.port, "retry_count": retry_count},
                    "timestamp": int(time.time() * 1000)
                }) + '\n')
        except: pass
        # #endregion
        
        last_error = None
        for attempt in range(1, retry_count + 1):
            # #region agent log
            try:
                with open('c:\\Projects\\UB\\.cursor\\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "B",
                        "location": "clickhouse_models.py:26",
                        "message": f"Connection attempt {attempt}/{retry_count}",
                        "data": {"attempt": attempt, "host": self.host, "port": self.port},
                        "timestamp": int(time.time() * 1000)
                    }) + '\n')
            except: pass
            # #endregion
            
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
                
                # #region agent log
                try:
                    with open('c:\\Projects\\UB\\.cursor\\debug.log', 'a', encoding='utf-8') as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "B",
                            "location": "clickhouse_models.py:38",
                            "message": "Connection successful",
                            "data": {"attempt": attempt},
                            "timestamp": int(time.time() * 1000)
                        }) + '\n')
                except: pass
                # #endregion
                
                return
            except Exception as e:
                last_error = e
                
                # #region agent log
                try:
                    with open('c:\\Projects\\UB\\.cursor\\debug.log', 'a', encoding='utf-8') as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "A",
                            "location": "clickhouse_models.py:40",
                            "message": f"Connection attempt {attempt} failed",
                            "data": {"attempt": attempt, "error": str(e), "error_type": type(e).__name__},
                            "timestamp": int(time.time() * 1000)
                        }) + '\n')
                except: pass
                # #endregion
                
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
        # If client exists, return it
        if self.client:
            return self.client
        
        # Check if we should attempt connection (backoff to avoid spam)
        import time
        now = time.time()
        if self._last_connect_attempt and (now - self._last_connect_attempt) < self._connect_backoff_seconds:
            # Too soon to retry, return None without logging
            return None
        
        # Attempt connection
        self._last_connect_attempt = now
        try:
            self.connect()
            return self.client
        except Exception as e:
            # Only log error on first attempt or after backoff period
            if not self._last_connect_attempt or (now - self._last_connect_attempt) >= self._connect_backoff_seconds:
                logger.warning(f"ClickHouse connection unavailable (will retry later): {e}")
            # Return None to indicate connection is not available
            # This allows graceful degradation
            return None

    def init_schema(self):
        """
        Defines the High-Performance OLAP Schema.
        Mirrors WB API v5 /supplier/reportDetailByPeriod.
        """
        schema_sql = f"""
        CREATE TABLE IF NOT EXISTS {self.database}.realization_reports (
            rrd_id UInt64,
            realizationreport_id UInt64,
            supplier_id UInt64,
            gi_id UInt64,
            subject_name LowCardinality(String),
            nm_id UInt64,
            brand_name LowCardinality(String),
            sa_name String,
            ts_name String,
            barcode String,
            doc_type_name LowCardinality(String),
            office_name LowCardinality(String),
            supplier_oper_name LowCardinality(String),
            site_country LowCardinality(String),
            create_dt DateTime,
            order_dt DateTime,
            sale_dt DateTime,
            rr_dt DateTime,
            quantity UInt32,
            retail_price Decimal(18, 2),
            retail_amount Decimal(18, 2),
            sale_percent UInt16,
            commission_percent Decimal(10, 2),
            retail_price_withdisc_rub Decimal(18, 2),
            delivery_amount UInt32,
            return_amount UInt32,
            delivery_rub Decimal(18, 2),
            gi_box_type_name LowCardinality(String),
            product_discount_for_report Decimal(10, 2),
            supplier_promo Decimal(10, 2),
            rid UInt64,
            ppvz_spp_prc Decimal(10, 2),
            ppvz_kvw_prc_base Decimal(10, 2),
            ppvz_kvw_prc Decimal(10, 2),
            sup_rating_prc_up Decimal(10, 2),
            is_kgvp_v2 UInt8,
            ppvz_sales_commission Decimal(18, 2),
            ppvz_for_pay Decimal(18, 2),
            ppvz_reward Decimal(18, 2),
            acquiring_fee Decimal(18, 2),
            acquiring_bank String,
            ppvz_vw Decimal(18, 2),
            ppvz_vw_nds Decimal(18, 2),
            ppvz_office_id UInt64,
            penalty Decimal(18, 2),
            additional_payment Decimal(18, 2),
            rebill_logistic_cost Decimal(18, 2),
            inserted_at DateTime DEFAULT now()
        ) 
        ENGINE = ReplacingMergeTree(inserted_at)
        ORDER BY (supplier_id, toDate(sale_dt), nm_id, rrd_id)
        TTL sale_dt + INTERVAL 3 YEAR;
        """
        self.client.command(schema_sql)

    def insert_reports(self, reports: list):
        """Batch insert raw reports."""
        if not reports: return
        
        client = self.get_client()
        if not client: return
        
        try:
            clean_reports = []
            for r in reports:
                clean_r = {}
                for k, v in r.items():
                    if k not in self.VALID_COLUMNS: continue
                    
                    if k in self.DATE_COLUMNS and isinstance(v, str):
                        try:
                            clean_r[k] = datetime.fromisoformat(v.replace('Z', ''))
                        except (ValueError, TypeError):
                            clean_r[k] = datetime.fromtimestamp(0)
                    else:
                        clean_r[k] = v
                
                if clean_r:
                    clean_reports.append(clean_r)
            
            if not clean_reports: return

            columns = list(clean_reports[0].keys())
            data_values = []
            for r in clean_reports:
                row = [r.get(col) for col in columns]
                data_values.append(row)

            client.insert(
                f"{self.database}.realization_reports",
                data_values,
                column_names=columns
            )
        except Exception as e:
            logger.error(f"ClickHouse Insert Error: {e}")
            self.client = None
            raise e

# Singleton instance
ch_service = ClickHouseService()