import os
import re
import json
import logging
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import ProductCost
from clickhouse_models import ch_service

logger = logging.getLogger("AI-Service")

class AnalysisService:
    def __init__(self):
        self.ai_api_key = os.getenv("AI_API_KEY", "") 
        self.ai_url = "https://api.artemox.com/v1/chat/completions"
        # Ensure ClickHouse is connected lazily or on startup
        try:
            ch_service.connect()
        except Exception as e:
            logger.warning(f"ClickHouse init failed (will retry on usage): {e}")

    # --- P&L ANALYTICS (NEW) ---

    async def get_pnl_data(self, user_id: int, date_from: datetime, date_to: datetime, db: AsyncSession) -> List[Dict[str, Any]]:
        """
        Calculates Profit & Loss (P&L) by merging OLAP data (ClickHouse) with COGS (Postgres).
        
        Metrics Hierarchy:
        1. Gross Sales = Sum of realized price (Sales)
        2. Net Sales = Gross Sales - Returns
        3. COGS = Cost of Goods Sold
        4. CM1 (Marginal Profit 1) = Net Sales - COGS
        5. CM2 (Marginal Profit 2) = CM1 - Commission - Logistics - Penalties
        6. CM3 (EBITDA proxy) = CM2 - Marketing (Simulated or External)
        """
        
        # 1. Fetch Aggregates from ClickHouse
        # We group by Date and SKU (nm_id) to map COGS correctly
        ch_query = """
        SELECT 
            toDate(sale_dt) as report_date,
            nm_id,
            sumIf(retail_price_withdisc_rub, doc_type_name = 'Продажа') as gross_sales,
            sumIf(retail_price_withdisc_rub, doc_type_name = 'Возврат') as returns_sum,
            countIf(doc_type_name = 'Продажа') as qty_sold,
            countIf(doc_type_name = 'Возврат') as qty_returned,
            sum(ppvz_sales_commission) as commission,
            sum(delivery_rub) as logistics,
            sum(penalty) as penalties,
            sum(additional_payment) as adjustments
        FROM wb_analytics.realization_reports
        WHERE supplier_id = %(uid)s 
          AND sale_dt >= %(start)s 
          AND sale_dt <= %(end)s
        GROUP BY report_date, nm_id
        ORDER BY report_date ASC
        """
        
        params = {
            'uid': user_id, 
            'start': date_from, 
            'end': date_to
        }
        
        try:
            ch_client = ch_service.get_client()
            result = ch_client.query(ch_query, parameters=params)
            rows = result.result_rows # List of tuples
        except Exception as e:
            logger.error(f"ClickHouse Query Error: {e}")
            return []

        if not rows:
            return []

        # 2. Fetch COGS from PostgreSQL
        # Get unique SKUs from the CH result to optimize DB query
        unique_skus = list(set([row[1] for row in rows]))
        
        stmt = select(ProductCost).where(
            ProductCost.user_id == user_id, 
            ProductCost.sku.in_(unique_skus)
        )
        cogs_result = await db.execute(stmt)
        costs_map = {c.sku: c.cost_price for c in cogs_result.scalars().all()}

        # 3. Merge and Calculate Daily Aggregates
        daily_pnl = {}

        for row in rows:
            r_date = row[0] # date
            sku = row[1]
            gross_sales = float(row[2])
            returns_sum = float(row[3]) # Usually positive in CH sum, need to subtract
            qty_sold = int(row[4])
            qty_returned = int(row[5])
            commission = float(row[6])
            logistics = float(row[7])
            penalties = float(row[8])
            adjustments = float(row[9])

            # Calculate COGS for this line
            unit_cost = costs_map.get(sku, 0)
            # COGS is calculated on Net Quantity (Sold - Returned) or just Sold depending on accounting policy.
            # Usually: COGS is recognized when sale happens. Returns reverse COGS.
            total_cogs = (qty_sold * unit_cost) - (qty_returned * unit_cost)

            date_str = r_date.strftime("%Y-%m-%d")
            
            if date_str not in daily_pnl:
                daily_pnl[date_str] = {
                    "date": date_str,
                    "gross_sales": 0.0,
                    "net_sales": 0.0,
                    "cogs": 0.0,
                    "commission": 0.0,
                    "logistics": 0.0,
                    "penalties": 0.0,
                    "marketing": 0.0, # Placeholder
                    "cm1": 0.0,
                    "cm2": 0.0,
                    "cm3": 0.0
                }

            # Aggregation
            d = daily_pnl[date_str]
            d["gross_sales"] += gross_sales
            # Net Sales = Gross - Returns (Assuming returns_sum is the money returned to client)
            # In WB realization report, 'returns_sum' is often the value associated with return.
            # We subtract it.
            d["net_sales"] += (gross_sales - returns_sum) 
            d["cogs"] += total_cogs
            d["commission"] += commission
            d["logistics"] += logistics
            d["penalties"] += (penalties + adjustments)
        
        # 4. Finalize Metrics Calculation
        final_output = []
        for date_str, metrics in sorted(daily_pnl.items()):
            metrics["cm1"] = metrics["net_sales"] - metrics["cogs"]
            metrics["cm2"] = metrics["cm1"] - metrics["commission"] - metrics["logistics"] - metrics["penalties"]
            metrics["cm3"] = metrics["cm2"] - metrics["marketing"]
            
            # Rounding for UI
            for k, v in metrics.items():
                if isinstance(v, float):
                    metrics[k] = round(v, 2)
            
            final_output.append(metrics)

        return final_output

    # --- EXISTING METHODS (Preserved) ---

    @staticmethod
    def calculate_metrics(raw_data: dict):
        if raw_data.get("status") == "error": return raw_data
        
        p = raw_data.get("prices", {})
        wallet = p.get("wallet_purple", 0)
        standard = p.get("standard_black", 0)
        base = p.get("base_crossed", 0)
        
        # Расчет выгоды
        benefit = standard - wallet if standard > wallet else 0
        discount_pct = round(((base - wallet) / base * 100), 1) if base > 0 else 0
        
        raw_data["metrics"] = {
            "wallet_benefit": benefit,
            "total_discount_percent": discount_pct,
            "is_favorable": discount_pct > 45
        }
        return raw_data

    @staticmethod
    def calculate_supply_prediction(current_stock: int, sales_velocity: float):
        """Расчет дней до обнуления (Out-of-Stock)."""
        if sales_velocity <= 0:
            return {"days_left": 999, "status": "ok", "message": "Продаж нет"}
        
        days_left = int(current_stock / sales_velocity)
        
        status = "ok"
        message = "Запаса достаточно"
        if days_left <= 3:
            status = "critical"
            message = "Критический остаток!"
        elif days_left <= 7:
            status = "warning"
            message = "Пора планировать поставку"
            
        return {"days_left": days_left, "status": status, "message": message}

    @staticmethod
    def calculate_transit_benefit(volume_liters: int):
        """[NEW] Расчет выгоды транзита (Roadmap 3.2.2)."""
        koledino_direct_cost = volume_liters * 30 * 1 
        kazan_transit_cost = 1500 + (volume_liters * 20 * 0) 
        
        benefit = koledino_direct_cost - kazan_transit_cost
        
        return {
            "direct_cost": koledino_direct_cost,
            "transit_cost": kazan_transit_cost,
            "benefit": benefit,
            "is_profitable": benefit > 0,
            "recommendation": "Используйте транзит через Казань" if benefit > 0 else "Прямая поставка выгоднее"
        }

    def clean_ai_text(self, text: str) -> str:
        """Очистка текста от Markdown мусора"""
        if not text: return ""
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text) 
        text = re.sub(r'#+\s?', '', text)
        text = text.replace("`", "")
        return text.strip()

    def analyze_reviews_with_ai(self, reviews: list, product_name: str):
        """Синхронный метод (выполняется в Celery)."""
        if not reviews: 
            return {"flaws": ["Нет отзывов"], "strategy": ["Недостаточно данных"]}

        reviews_text = ""
        for r in reviews[:25]:
            text = f"- {r['text'][:150]} ({r['rating']}*)\n"
            if len(reviews_text) + len(text) < 2500:
                reviews_text += text
            else:
                break
        
        prompt = f"""
        Проанализируй товар WB: "{product_name}".
        Отзывы:
        {reviews_text}
        
        Задача:
        1. Напиши 3 главных минуса (жалобы).
        2. Напиши 5 советов продавцу (стратегия улучшения).
        
        Ответ верни СТРОГО в JSON:
        {{
            "flaws": ["минус 1", "минус 2", "минус 3"],
            "strategy": ["совет 1", "совет 2", "совет 3", "совет 4", "совет 5"]
        }}
        """

        return self._call_ai(prompt, {"flaws": ["Ошибка"], "strategy": ["Ошибка"]})

    def generate_product_content(self, keywords: list, tone: str, title_len: int = 100, desc_len: int = 1000):
        """Генерация SEO заголовка и описания на основе ключевых слов."""
        kw_str = ", ".join(keywords)
        
        prompt = f"""
        Ты профессиональный SEO-копирайтер для Wildberries.
        Задача: Написать продающий заголовок и описание товара.
        
        Параметры:
        - Ключевые слова: {kw_str}
        - Тон текста: {tone}
        - Длина заголовка: ~{title_len} символов (максимально используй ключи).
        - Длина описания: ~{desc_len} символов.
        
        Требования:
        1. Заголовок: релевантный, для поиска.
        2. Описание: структурированное, без воды, богатое ключами.
        
        Ответ верни СТРОГО в JSON:
        {{
            "title": "Заголовок",
            "description": "Описание..."
        }}
        """
        
        return self._call_ai(prompt, {"title": "Ошибка генерации", "description": "Не удалось сгенерировать текст"})

    def _call_ai(self, prompt: str, fallback_json: dict):
        """Вспомогательный метод вызова AI"""
        try:
            payload = {
                "model": "deepseek-chat", 
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7 
            }
            headers = {"Authorization": f"Bearer {self.ai_api_key}", "Content-Type": "application/json"}
            
            resp = requests.post(self.ai_url, json=payload, headers=headers, timeout=90) 
            
            if resp.status_code != 200:
                logger.error(f"AI API Error: {resp.text}")
                return fallback_json
            
            result = resp.json()
            content = result['choices'][0]['message']['content']
            
            try:
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    for k, v in parsed.items():
                        if isinstance(v, list):
                            parsed[k] = [self.clean_ai_text(str(x)) for x in v]
                        elif isinstance(v, str):
                             parsed[k] = self.clean_ai_text(v)
                    return parsed
                else:
                    return fallback_json
            except Exception as e:
                logger.error(f"JSON Parse Error: {e}")
                return fallback_json

        except Exception as e:
            logger.error(f"AI Connection Error: {e}")
            return fallback_json

analysis_service = AnalysisService()