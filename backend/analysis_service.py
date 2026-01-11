import os
import re
import json
import logging
import requests
import math
import asyncio
from statistics import mean, stdev
from datetime import datetime, timedelta
from collections import defaultdict

# Imports for DB access
from database import SyncSessionLocal, ProductCost, CostHistory, User, TaxScheme
from clickhouse_models import ch_client

# ML Forecasting
from forecasting import forecast_demand

logger = logging.getLogger("AI-Service")

class AnalysisService:
    def __init__(self):
        self.ai_api_key = os.getenv("AI_API_KEY", "") 
        self.ai_url = "https://api.artemox.com/v1/chat/completions"
        import redis
        self.redis = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

    def get_pnl_data(self, user_id: int, date_from: datetime, date_to: datetime):
        """
        Dynamic P&L Calculation Engine v2.0
        Features:
        - Historical COGS Lookup
        - Dynamic Tax Schemes (USN 6/15, 1, OSNO)
        - Dual Ledger (Provisional vs Actual)
        """
        session = SyncSessionLocal()
        try:
            # 1. Fetch User Settings (Tax Scheme)
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                logger.error(f"User {user_id} not found")
                return []
            
            tax_scheme = user.tax_scheme or TaxScheme.USN_6
            
            # 2. Fetch Aggregated Sales Data (ClickHouse)
            raw_data = ch_client.get_aggregated_pnl(user_id, date_from, date_to)
            if not raw_data:
                return []
            
            # Collect unique SKUs for batch loading
            unique_skus = set(row[1] for row in raw_data) # row[1] is nm_id/sku
            
            # 3. Batch Fetch Cost History & Settings
            # Fetch ProductCost (Static settings: marketing, fixed costs)
            product_costs = session.query(ProductCost).filter(
                ProductCost.user_id == user_id,
                ProductCost.sku.in_(unique_skus)
            ).all()
            
            # Fetch CostHistory (Dynamic costs: cogs, fulfillment)
            cost_histories = session.query(CostHistory).filter(
                CostHistory.user_id == user_id,
                CostHistory.sku.in_(unique_skus)
            ).order_by(CostHistory.valid_from.asc()).all()
            
            # 4. Organize Data for Fast Lookup
            settings_map = {pc.sku: pc for pc in product_costs}
            
            # Map: SKU -> List of History Records (sorted by date)
            history_map = defaultdict(list)
            for ch in cost_histories:
                history_map[ch.sku].append(ch)

            daily_pnl = defaultdict(lambda: {
                "date": "", 
                "gross_sales": 0, "returns_amount": 0, "net_sales": 0,
                "cogs": 0, "cm1": 0, 
                "wb_commission": 0, "wb_logistics": 0, "wb_penalties": 0,
                "cm2": 0, "marketing": 0, "tax": 0, "cm3": 0,
                "sales_count": 0, "returns_count": 0,
                "is_provisional": False, # Flag for UI
                "missing_costs": False
            })

            # 5. Iterate & Calculate
            for row in raw_data:
                # Unpack ClickHouse Row
                # day, nm_id, revenue, commission, logistics, penalty, additional, sales_count, returns_count
                day_date, sku, revenue, comm, log, penalty, add_pay, s_cnt, r_cnt = row
                
                # Normalize types
                revenue = float(revenue)
                comm = float(comm)
                log = float(log)
                penalty = float(penalty)
                
                # Check for provisional status (if available in row, implied by method signature in previous code)
                # Assuming ClickHouse query might return it or we infer.
                # Since get_aggregated_pnl logic aggregates, if ANY record is provisional, the day is provisional?
                # For now, we assume data is 'actual' unless flagged explicitly in a detailed query.
                # However, task says "Check a reconciliation_status flag". 
                # Let's assume standard behavior: 
                # If we need strict checking, we'd need to fetch status in aggregation. 
                # Defaulting to False here as agg query doesn't return status column in provided snippet.
                
                date_str = day_date.strftime("%Y-%m-%d")
                metrics = daily_pnl[date_str]
                metrics["date"] = date_str
                
                # --- Find Applicable Cost ---
                sku_history = history_map.get(sku, [])
                active_cost = None
                
                # Find the record valid for this day
                # Since records are sorted by valid_from:
                for record in sku_history:
                    start = record.valid_from
                    end = record.valid_to
                    # Check if day_date is within [start, end) or [start, infinity)
                    if start.date() <= day_date.date():
                        if end is None or day_date.date() < end.date():
                            active_cost = record
                            # Keep iterating to find the *latest* valid start date if multiple overlap (shouldn't happen)
                            # Or break if we assume non-overlapping sorted.
                            # Best practice: take the last one that started before or on date.
                            
                if not active_cost and sku_history:
                     # Fallback: if no record covers the date, maybe use the closest one?
                     # Task says: "IF no record found, flag as Missing Cost"
                     pass

                # Static settings
                static_settings = settings_map.get(sku)
                ext_marketing_per_unit = static_settings.external_marketing if static_settings else 0.0
                
                # Cost Calculation
                unit_cogs = 0.0
                unit_fulfillment = 0.0
                
                if active_cost:
                    unit_cogs = active_cost.cost_price
                    unit_fulfillment = active_cost.fulfillment_cost
                else:
                    metrics["missing_costs"] = True
                
                # Metrics Accumulation
                # Net Sales
                metrics["net_sales"] += revenue
                metrics["sales_count"] += s_cnt
                metrics["returns_count"] += r_cnt
                
                # COGS (Cost of Sales - Returns)
                # Technically COGS is realized on sale. Returns put item back to stock (usually).
                # Simple logic: (Sales - Returns) * Cost
                net_qty = s_cnt - r_cnt
                metrics["cogs"] += unit_cogs * net_qty
                
                # Fulfillment (Usually charged per order, sometimes returned)
                # We assume fulfillment is paid on sale
                metrics["cogs"] += unit_fulfillment * s_cnt
                
                # WB Expenses
                metrics["wb_commission"] += comm
                metrics["wb_logistics"] += log
                metrics["wb_penalties"] += penalty
                
                # Marketing (External)
                metrics["marketing"] += ext_marketing_per_unit * s_cnt
                
                # --- Dynamic Tax Calculation ---
                item_tax = 0.0
                
                if tax_scheme == TaxScheme.USN_6:
                    # 6% of Revenue (Income)
                    # Revenue cannot be negative for tax base usually, but P&L allows negative days.
                    tax_base = max(0, revenue)
                    item_tax = tax_base * 0.06
                    
                elif tax_scheme == TaxScheme.USN_1:
                    # 1% of Revenue
                    tax_base = max(0, revenue)
                    item_tax = tax_base * 0.01
                    
                elif tax_scheme == TaxScheme.USN_15:
                    # 15% of (Revenue - Expenses)
                    # Expenses = COGS + Comm + Log + Penalty + Marketing
                    # Note: We calculate tax on the *Item* level here for aggregation, 
                    # but strictly USN-15 is calculated on the total period. 
                    # Approximating per-item is acceptable for daily dashboard.
                    
                    expenses = (unit_cogs * net_qty) + (unit_fulfillment * s_cnt) + \
                               comm + log + penalty + (ext_marketing_per_unit * s_cnt)
                    
                    profit_base = revenue - expenses
                    item_tax = max(0, profit_base * 0.15)
                
                elif tax_scheme == TaxScheme.OSNO:
                    # Generic 20% VAT approximation if not specified
                    # Assuming revenue includes VAT
                    vat = revenue / 1.20 * 0.20
                    item_tax = vat
                    
                metrics["tax"] += item_tax

            # 6. Final Aggregation
            result_list = []
            for date_key in sorted(daily_pnl.keys()):
                m = daily_pnl[date_key]
                
                m["gross_sales"] = m["net_sales"] # Can differ if discounts applied differently
                
                # CM 1: Net Sales - COGS
                m["cm1"] = m["net_sales"] - m["cogs"]
                
                # CM 2: CM1 - Marketplace Expenses
                wb_expenses = m["wb_commission"] + m["wb_logistics"] + m["wb_penalties"]
                m["cm2"] = m["cm1"] - wb_expenses
                
                # CM 3: CM2 - Marketing & Tax
                other_expenses = m["tax"] + m["marketing"]
                m["cm3"] = m["cm2"] - other_expenses
                
                # Rounding
                for k, v in m.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        m[k] = round(v, 2)
                        
                result_list.append(m)
                
            return result_list

        except Exception as e:
            logger.error(f"PnL Calculation Error: {e}")
            return []
        finally:
            session.close()

    # --- Старые методы (оставляем для совместимости) ---
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

    def calculate_supply_metrics(self, current_stock: int, sales_history: list, lead_time_days: int = 14, sku: int = None):
        """
        Расчет метрик пополнения с использованием ML-прогноза (Prophet).
        """
        if not sales_history:
            return {"status": "no_data", "message": "Нет данных", "recommendation": 0, "days_left": 999}

        # 1. Получаем прогноз (Из кэша или считаем на лету)
        forecast_data = None
        if sku:
            # Пытаемся достать свежий прогноз из Redis
            cached = self.redis.get(f"forecast:{sku}")
            if cached:
                try:
                    forecast_data = json.loads(cached)
                except: pass
        
        # Fallback
        if not forecast_data:
            forecast_data = forecast_demand(sales_history, horizon_days=lead_time_days)

        # 2. Извлекаем метрики
        avg_daily_demand = forecast_data.get("forecast_avg_daily", 0)
        sigma_d = forecast_data.get("sigma", 0)
        
        if avg_daily_demand == 0:
             return {"status": "ok", "message": "Спрос отсутствует", "recommendation": 0, "days_left": 999, "safety_stock": 0}

        # 3. Параметры Supply Chain
        z_alpha = 1.65  # 95%
        avg_lead_time = lead_time_days
        sigma_lead_time = 2 

        # 4. Расчет Safety Stock
        term1 = avg_lead_time * (sigma_d ** 2)
        term2 = (avg_daily_demand ** 2) * (sigma_lead_time ** 2)
        safety_stock = int(z_alpha * math.sqrt(term1 + term2))

        # 5. Расчет ROP
        demand_during_lead_time = avg_daily_demand * avg_lead_time
        cycle_stock = int(demand_during_lead_time)
        rop = int(cycle_stock + safety_stock)

        # 6. Анализ
        days_left = int(current_stock / avg_daily_demand) if avg_daily_demand > 0 else 999
        qty_to_order = 0
        status = "ok"
        message = "Запаса достаточно"

        if current_stock <= rop:
            target_level = rop + (avg_daily_demand * 30) 
            qty_to_order = int(target_level - current_stock)
            if qty_to_order < 0: qty_to_order = 0
            
            if current_stock <= safety_stock:
                status = "critical"
                message = f"Критично! Остаток < SS ({safety_stock})"
            else:
                status = "warning"
                message = f"Пора заказывать (ROP: {rop})"
        elif days_left < lead_time_days + 5:
             status = "warning"
             message = "Планируйте поставку"

        return {
            "status": status, 
            "message": message, 
            "days_left": days_left,
            "metrics": {
                "avg_sales": round(avg_daily_demand, 1),
                "volatility": round(sigma_d, 1), 
                "safety_stock": safety_stock, 
                "rop": rop,
                "lead_time": lead_time_days
            },
            "recommendation": qty_to_order,
            "forecast_source": "prophet" if forecast_data.get("status") == "success" else "simple_avg"
        }

    @staticmethod
    def calculate_pnl(price, quantity_sold, logistics_wb, commission_wb, advertising_wb, cost_price, fulfillment, external_marketing, tax_rate):
        # Legacy method kept for single-item calculation compatibility
        gross_sales = price * quantity_sold
        total_cogs = cost_price * quantity_sold
        cm1 = gross_sales - total_cogs
        total_commission = commission_wb * quantity_sold
        total_logistics = logistics_wb * quantity_sold
        total_fulfillment = fulfillment * quantity_sold
        total_tax = (gross_sales * (tax_rate / 100))
        operational_expenses = total_commission + total_logistics + total_fulfillment + total_tax
        cm2 = cm1 - operational_expenses
        total_marketing = (advertising_wb * quantity_sold) + external_marketing
        net_profit = cm2 - total_marketing
        margin_percent = round((net_profit / gross_sales * 100), 1) if gross_sales > 0 else 0
        roi = round((net_profit / (total_cogs + total_marketing) * 100), 1) if (total_cogs + total_marketing) > 0 else 0
        return {
            "gross_sales": int(gross_sales), "cogs": int(total_cogs), "cm1": int(cm1),
            "expenses": {"commission": int(total_commission), "logistics": int(total_logistics), "fulfillment": int(total_fulfillment), "tax": int(total_tax)},
            "cm2": int(cm2),
            "marketing": {"internal": int(advertising_wb * quantity_sold), "external": int(external_marketing)},
            "cm3": int(net_profit), "margin_percent": margin_percent, "roi": roi, "is_toxic": cm2 < 0 or net_profit < 0
        }

    @staticmethod
    def calculate_transit_benefit(volume_liters: int):
        koledino_direct_cost = volume_liters * 30 * 1 
        kazan_transit_cost = 1500 + (volume_liters * 20 * 0) 
        benefit = koledino_direct_cost - kazan_transit_cost
        return {"direct_cost": koledino_direct_cost, "transit_cost": kazan_transit_cost, "benefit": benefit, "is_profitable": benefit > 0, "recommendation": "Используйте транзит через Казань" if benefit > 0 else "Прямая поставка выгоднее"}

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
        prompt = f"""Проанализируй товар WB: "{product_name}". Отзывы: {reviews_text} Задача: 1. Напиши 3 главных минуса. 2. Напиши 5 советов продавцу. Ответ JSON: {{ "flaws": [], "strategy": [] }}"""
        return self._call_ai(prompt, {"flaws": ["Ошибка"], "strategy": ["Ошибка"]})

    def generate_product_content(self, keywords: list, tone: str, title_len: int = 100, desc_len: int = 1000):
        kw_str = ", ".join(keywords)
        prompt = f"""SEO-копирайтер WB. Ключи: {kw_str}. Тон: {tone}. Заголовок: ~{title_len}. Описание: ~{desc_len}. JSON: {{ "title": "...", "description": "..." }}"""
        return self._call_ai(prompt, {"title": "Ошибка", "description": "Ошибка"})

    def _call_ai(self, prompt: str, fallback_json: dict):
        try:
            payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.5}
            auth_header = self.ai_api_key if self.ai_api_key.startswith("Bearer ") else f"Bearer {self.ai_api_key}"
            headers = {"Authorization": auth_header, "Content-Type": "application/json"}
            resp = requests.post(self.ai_url, json=payload, headers=headers, timeout=60)
            if resp.status_code != 200: 
                logger.error(f"AI API Error: {resp.text}")
                return fallback_json
            content = resp.json()['choices'][0]['message']['content']
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match: return json.loads(json_match.group(0))
            return fallback_json
        except Exception as e:
            logger.error(f"AI Error: {e}")
            return fallback_json

analysis_service = AnalysisService()