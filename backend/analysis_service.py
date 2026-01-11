import os
import re
import json
import logging
import requests
import math
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import ProductCost
from clickhouse_models import ch_service
from forecasting import forecast_demand

logger = logging.getLogger("AI-Service")

class AnalysisService:
    def __init__(self):
        self.ai_api_key = os.getenv("AI_API_KEY", "") 
        self.ai_url = "https://api.artemox.com/v1/chat/completions"
        try:
            ch_service.connect()
        except Exception as e:
            logger.warning(f"ClickHouse init failed (will retry on usage): {e}")

    # --- FORECASTING & SUPPLY CHAIN METRICS (NEW) ---

    def calculate_supply_metrics(
        self, 
        current_stock: int, 
        sales_history: List[Dict[str, Any]], 
        forecast_data: Optional[Dict[str, Any]] = None,
        lead_time_days: int = 7,  # Среднее время поставки
        lead_time_sigma: int = 2, # Отклонение времени поставки (дней)
        service_level_z: float = 1.65 # Z-score для 95% уровня сервиса
    ) -> Dict[str, Any]:
        """
        Расчет точки заказа (ROP) и страхового запаса (Safety Stock).
        
        Формула Safety Stock (SS):
        SS = Z * sqrt( (Avg_Lead_Time * sigma_Demand^2) + (Avg_Demand^2 * sigma_Lead_Time^2) )
        
        Формула Reorder Point (ROP):
        ROP = (Demand_During_Lead_Time) + SS
        """
        
        # 1. Определяем спрос (Demand)
        # Если есть прогноз от Prophet, используем его среднее значение на горизонте Lead Time
        if forecast_data and forecast_data.get("status") == "success":
            avg_daily_demand = forecast_data.get("daily_avg_forecast", 0)
            forecast_points = forecast_data.get("forecast_points", [])
            # Сумма прогноза именно на время доставки (Lead Time)
            demand_during_lead_time = sum([p['yhat'] for p in forecast_points[:lead_time_days]])
        else:
            # Fallback: Считаем среднее по истории, если нет прогноза
            if not sales_history:
                return {"status": "error", "message": "No data"}
            values = [x['qty'] for x in sales_history if x['qty'] > 0]
            if not values:
                return {"status": "error", "message": "Zero sales"}
            avg_daily_demand = np.mean(values)
            demand_during_lead_time = avg_daily_demand * lead_time_days

        # 2. Считаем стандартное отклонение спроса (sigma_Demand) по истории
        if sales_history:
            hist_values = [x['qty'] for x in sales_history]
            sigma_demand = np.std(hist_values) if len(hist_values) > 1 else 0
        else:
            sigma_demand = 0

        # 3. Расчет Safety Stock
        # (Avg_Lead_Time * sigma_Demand^2)
        term1 = lead_time_days * (sigma_demand ** 2)
        # (Avg_Demand^2 * sigma_Lead_Time^2)
        term2 = (avg_daily_demand ** 2) * (lead_time_sigma ** 2)
        
        safety_stock = service_level_z * math.sqrt(term1 + term2)
        
        # 4. Расчет ROP
        rop = demand_during_lead_time + safety_stock
        
        # 5. Интерпретация для пользователя
        days_left = current_stock / avg_daily_demand if avg_daily_demand > 0 else 999
        
        # Округляем
        safety_stock = int(math.ceil(safety_stock))
        rop = int(math.ceil(rop))
        days_left = int(days_left)
        
        status = "ok"
        recommendation = "Запаса достаточно"
        
        if current_stock <= 0:
            status = "out_of_stock"
            recommendation = "Товара нет в наличии!"
        elif current_stock < safety_stock:
            status = "critical"
            recommendation = "Срочно пополнить! (Ниже страхового запаса)"
        elif current_stock < rop:
            status = "warning"
            recommendation = f"Пора заказывать (Ниже точки заказа {rop} шт)"
            
        return {
            "status": status,
            "recommendation": recommendation,
            "metrics": {
                "safety_stock": safety_stock,
                "rop": rop,
                "days_left": days_left,
                "avg_daily_demand": round(avg_daily_demand, 1),
                "demand_lead_time": round(demand_during_lead_time, 1),
                "current_stock": current_stock
            },
            "inputs": {
                "lead_time": lead_time_days,
                "service_level": "95%"
            }
        }

    # --- P&L ANALYTICS (EXISTING) ---

    async def get_pnl_data(self, user_id: int, date_from: datetime, date_to: datetime, db: AsyncSession) -> List[Dict[str, Any]]:
        # ... (Preserved P&L Logic from previous file)
        # For brevity, reusing the previous logic via Copy-Paste is assumed in real env, 
        # but here I must output full file content or updated parts.
        # Since I'm refactoring, I will include the P&L logic fully to ensure the file is complete.
        
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
        
        params = {'uid': user_id, 'start': date_from, 'end': date_to}
        
        try:
            ch_client = ch_service.get_client()
            result = ch_client.query(ch_query, parameters=params)
            rows = result.result_rows
        except Exception as e:
            logger.error(f"ClickHouse Query Error: {e}")
            return []

        if not rows: return []

        unique_skus = list(set([row[1] for row in rows]))
        stmt = select(ProductCost).where(ProductCost.user_id == user_id, ProductCost.sku.in_(unique_skus))
        cogs_result = await db.execute(stmt)
        costs_map = {c.sku: c.cost_price for c in cogs_result.scalars().all()}

        daily_pnl = {}
        for row in rows:
            r_date, sku, gross_sales, returns_sum, qty_sold, qty_returned, commission, logistics, penalties, adjustments = row
            gross_sales, returns_sum = float(gross_sales), float(returns_sum)
            qty_sold, qty_returned = int(qty_sold), int(qty_returned)
            commission, logistics, penalties, adjustments = float(commission), float(logistics), float(penalties), float(adjustments)

            unit_cost = costs_map.get(sku, 0)
            total_cogs = (qty_sold * unit_cost) - (qty_returned * unit_cost)

            date_str = r_date.strftime("%Y-%m-%d")
            if date_str not in daily_pnl:
                daily_pnl[date_str] = {
                    "date": date_str, "gross_sales": 0.0, "net_sales": 0.0, "cogs": 0.0,
                    "commission": 0.0, "logistics": 0.0, "penalties": 0.0, "marketing": 0.0, 
                    "cm1": 0.0, "cm2": 0.0, "cm3": 0.0
                }
            d = daily_pnl[date_str]
            d["gross_sales"] += gross_sales
            d["net_sales"] += (gross_sales - returns_sum) 
            d["cogs"] += total_cogs
            d["commission"] += commission
            d["logistics"] += logistics
            d["penalties"] += (penalties + adjustments)
        
        final_output = []
        for date_str, metrics in sorted(daily_pnl.items()):
            metrics["cm1"] = metrics["net_sales"] - metrics["cogs"]
            metrics["cm2"] = metrics["cm1"] - metrics["commission"] - metrics["logistics"] - metrics["penalties"]
            metrics["cm3"] = metrics["cm2"] - metrics["marketing"]
            for k, v in metrics.items():
                if isinstance(v, float): metrics[k] = round(v, 2)
            final_output.append(metrics)
        return final_output

    @staticmethod
    def calculate_metrics(raw_data: dict):
        if raw_data.get("status") == "error": return raw_data
        p = raw_data.get("prices", {})
        wallet = p.get("wallet_purple", 0)
        standard = p.get("standard_black", 0)
        base = p.get("base_crossed", 0)
        benefit = standard - wallet if standard > wallet else 0
        discount_pct = round(((base - wallet) / base * 100), 1) if base > 0 else 0
        raw_data["metrics"] = {
            "wallet_benefit": benefit,
            "total_discount_percent": discount_pct,
            "is_favorable": discount_pct > 45
        }
        return raw_data

    @staticmethod
    def calculate_transit_benefit(volume_liters: int):
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
        if not text: return ""
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text) 
        text = re.sub(r'#+\s?', '', text)
        text = text.replace("`", "")
        return text.strip()

    def analyze_reviews_with_ai(self, reviews: list, product_name: str):
        if not reviews: return {"flaws": ["Нет отзывов"], "strategy": ["Недостаточно данных"]}
        reviews_text = ""
        for r in reviews[:25]:
            text = f"- {r['text'][:150]} ({r['rating']}*)\n"
            if len(reviews_text) + len(text) < 2500: reviews_text += text
            else: break
        
        prompt = f"""
        Проанализируй товар WB: "{product_name}".
        Отзывы: {reviews_text}
        Задача: 1. Напиши 3 главных минуса (жалобы). 2. Напиши 5 советов продавцу.
        Ответ верни СТРОГО в JSON: {{ "flaws": [...], "strategy": [...] }}
        """
        return self._call_ai(prompt, {"flaws": ["Ошибка"], "strategy": ["Ошибка"]})

    def generate_product_content(self, keywords: list, tone: str, title_len: int = 100, desc_len: int = 1000):
        kw_str = ", ".join(keywords)
        prompt = f"""
        Ты профессиональный SEO-копирайтер для Wildberries.
        Задача: Написать продающий заголовок и описание товара.
        Параметры: Ключевые слова: {kw_str}. Тон: {tone}. Заголовок: ~{title_len} симв. Описание: ~{desc_len} симв.
        Ответ верни СТРОГО в JSON: {{ "title": "...", "description": "..." }}
        """
        return self._call_ai(prompt, {"title": "Ошибка генерации", "description": "Не удалось сгенерировать текст"})

    def _call_ai(self, prompt: str, fallback_json: dict):
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
                        if isinstance(v, list): parsed[k] = [self.clean_ai_text(str(x)) for x in v]
                        elif isinstance(v, str): parsed[k] = self.clean_ai_text(v)
                    return parsed
                else: return fallback_json
            except Exception as e:
                logger.error(f"JSON Parse Error: {e}")
                return fallback_json
        except Exception as e:
            logger.error(f"AI Connection Error: {e}")
            return fallback_json

analysis_service = AnalysisService()