import os
import clickhouse_connect
import logging
from datetime import datetime

logger = logging.getLogger("ClickHouse")

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", 8123))
CLICKHOUSE_USER = os.getenv("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "")

class ClickHouseClient:
    def __init__(self):
        self.client = None
        self._connect()

    def _connect(self):
        try:
            self.client = clickhouse_connect.get_client(
                host=CLICKHOUSE_HOST,
                port=CLICKHOUSE_PORT,
                username=CLICKHOUSE_USER,
                password=CLICKHOUSE_PASSWORD,
                database='default'
            )
            logger.info("Connected to ClickHouse")
        except Exception as e:
            logger.error(f"Failed to connect to ClickHouse: {e}")

    def init_schema(self):
        """
        Инициализация схемы данных.
        Используем ReplacingMergeTree для обработки дублей и обновлений по rrd_id.
        """
        if not self.client:
            return

        # Таблица финансовых отчетов (Зеркало API WB)
        # Partition by toYYYYMM(sale_dt) для эффективного удаления старых данных и управления диском
        ddl = """
        CREATE TABLE IF NOT EXISTS realization_reports (
            rrd_id UInt64,                 -- Уникальный ID строки отчета
            supplier_id UInt32,            -- ID селлера (для мульти-тенанси)
            realizationreport_id UInt64,   -- ID отчета
            
            -- Даты
            sale_dt DateTime,              -- Дата продажи/операции
            create_dt DateTime,            -- Дата формирования записи
            date_from DateTime,
            date_to DateTime,

            -- Товарная часть
            nm_id UInt32,                  -- Артикул WB
            brand_name LowCardinality(String),
            sa_name LowCardinality(String), -- Артикул продавца
            subject_name LowCardinality(String), -- Категория
            ts_name LowCardinality(String), -- Размер
            barcode String,
            
            -- Тип документа (Продажа/Возврат)
            doc_type_name LowCardinality(String), 
            supplier_oper_name LowCardinality(String),

            -- Финансы (Decimal для точности)
            retail_price Decimal(18, 2),        -- Розничная цена
            retail_amount Decimal(18, 2),       -- Сумма продаж (возвратов)
            commission_percent Decimal(18, 2),
            commission_amount Decimal(18, 2),   -- Комиссия WB
            retail_price_withdisc_rub Decimal(18, 2),
            
            -- Логистика и штрафы
            delivery_rub Decimal(18, 2),        -- Логистика к клиенту
            delivery_amount UInt32,             -- Кол-во доставок
            return_amount UInt32,               -- Кол-во возвратов
            penalty Decimal(18, 2),             -- Штрафы
            additional_payment Decimal(18, 2),  -- Доплаты
            
            -- Склады
            office_name LowCardinality(String),
            site_country LowCardinality(String),
            
            -- Метаданные
            record_status Enum8('actual' = 1, 'provisional' = 2), -- 1: Реализация, 2: Предварительно (из заказов)
            inserted_at DateTime DEFAULT now()

        ) ENGINE = ReplacingMergeTree(rrd_id)
        PARTITION BY toYYYYMM(sale_dt)
        ORDER BY (supplier_id, sale_dt, nm_id, rrd_id)
        TTL sale_dt + INTERVAL 3 YEAR;
        """
        
        try:
            self.client.command(ddl)
            logger.info("ClickHouse schema initialized: realization_reports")
        except Exception as e:
            logger.error(f"Schema init failed: {e}")

    def insert_reports(self, data: list, columns: list):
        """Пакетная вставка данных"""
        if not self.client or not data:
            return
        try:
            self.client.insert('realization_reports', data, column_names=columns)
        except Exception as e:
            logger.error(f"Batch insert failed: {e}")
            raise e

    def get_aggregated_pnl(self, user_id: int, date_from: datetime, date_to: datetime):
        """
        Получение агрегированных данных для P&L.
        Группировка по дням и артикулам.
        """
        query = """
        SELECT 
            toDate(sale_dt) as day,
            nm_id,
            sum(retail_amount) as revenue,
            sum(commission_amount) as commission,
            sum(delivery_rub) as logistics,
            sum(penalty) as penalty,
            sum(additional_payment) as additional,
            countIf(doc_type_name = 'Продажа') as sales_count,
            countIf(doc_type_name = 'Возврат') as returns_count
        FROM realization_reports
        WHERE supplier_id = %(user_id)s 
          AND sale_dt BETWEEN %(date_from)s AND %(date_to)s
        GROUP BY day, nm_id
        ORDER BY day
        """
        parameters = {'user_id': user_id, 'date_from': date_from, 'date_to': date_to}
        return self.client.query(query, parameters=parameters).result_rows

# Singleton instance
ch_client = ClickHouseClient()