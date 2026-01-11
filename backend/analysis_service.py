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

# Imports for DB access (Sync access inside async methods via run_in_executor usually, 
# but for simplicity we assume this service might be called from tasks or async wrappers)
from database import SyncSessionLocal, ProductCost
from clickhouse_models import ch_client

logger = logging.getLogger("AI-Service")

class AnalysisService:
    def __init__(self):
        self.ai_api_key = os.getenv("AI_API_KEY", "") 
        self.ai_url = "https://api.artemox.com/v1/chat/completions" 

    def get_pnl_data(self, user_id: int, date_from: datetime, date_to: datetime):
        """
        Расчет P&L (Profit and Loss) на основе данных ClickHouse и Postgres.
        
        Алгоритм:
        1. ClickHouse: Получаем факт продаж, комиссии, логистики (агрегаты по дням и SKU).
        2. Postgres: Получаем себестоимость (COGS), налоги, расходы на маркетинг.
        3. Merge: Объединяем данные в памяти.
        4. Calc: Считаем иерархию метрик (Gross -> Net -> CM1 -> CM2 -> CM3).
        """
        
        # 1. Запрос к OLAP (ClickHouse)
        # Результат: [(day, nm_id, revenue, commission, logistics, penalty, additional, sales_cnt, return_cnt), ...]
        raw_data = ch_client.get_aggregated_pnl(user_id, date_from, date_to)
        
        if not raw_data:
            return []

        # Собираем уникальные SKU для запроса себестоимости
        unique_skus = set(row[1] for row in raw_data)
        
        # 2. Запрос к OLTP (Postgres) за себестоимостью
        # В идеале здесь должна быть историческая таблица себестоимости.
        # Пока берем текущую из ProductCost.
        session = SyncSessionLocal()
        costs_map = {}
        try:
            costs = session.query(ProductCost).filter(
                ProductCost.user_id == user_id, 
                ProductCost.sku.in_(unique_skus)
            ).all()
            for c in costs:
                costs_map[c.sku] = {
                    "cogs": c.cost_price, 
                    "tax_rate": c.tax_rate,
                    "external_marketing": c.external_marketing,
                    "fulfillment": c.fulfillment_cost
                }
        finally:
            session.close()

        # 3. Агрегация по дням
        daily_pnl = defaultdict(lambda: {
            "date": "", "gross_sales": 0, "returns_amount": 0, "net_sales": 0,
            "cogs": 0, "cm1": 0, 
            "wb_commission": 0, "wb_logistics": 0, "wb_penalties": 0,
            "cm2": 0, "marketing": 0, "tax": 0, "cm3": 0,
            "sales_count": 0, "returns_count": 0
        })

        for row in raw_data:
            day_date, sku, revenue, comm, log, penalty, add_pay, s_cnt, r_cnt = row
            
            # Приведение типов (Decimal -> float для JSON)
            revenue = float(revenue)
            comm = float(comm)
            log = float(log)
            penalty = float(penalty)
            
            date_str = day_date.strftime("%Y-%m-%d")
            metrics = daily_pnl[date_str]
            metrics["date"] = date_str
            
            # Экономика товара
            cost_info = costs_map.get(sku, {"cogs": 0, "tax_rate": 6, "external_marketing": 0, "fulfillment": 0})
            
            # Расчет COGS (Себестоимость проданных - Себестоимость возвращенных)
            # Если return_amount в CH нет, используем r_cnt как прокси
            # Важно: revenue в отчете реализации уже учитывает возвраты (они там с минусом), 
            # но для COGS нам нужно знать физическое движение.
            
            # Упрощенная модель:
            item_cogs = cost_info["cogs"] * (s_cnt - r_cnt)
            item_fulfillment = cost_info["fulfillment"] * s_cnt # Фулфилмент платим за отгрузку
            
            # --- ИЕРАРХИЯ P&L ---
            
            # 1. Gross & Net Sales
            # В отчете реализации WB `retail_amount` - это уже Net Sales (Продажи - Возвраты) по деньгам
            metrics["net_sales"] += revenue
            metrics["sales_count"] += s_cnt
            metrics["returns_count"] += r_cnt
            
            # 2. CM1 = Net Sales - COGS
            metrics["cogs"] += item_cogs
            
            # 3. CM2 = CM1 - WB Expenses (Commission + Logistics + Penalty)
            metrics["wb_commission"] += comm
            metrics["wb_logistics"] += log
            metrics["wb_penalties"] += penalty
            
            # 4. CM3 = CM2 - Taxes - Marketing - Fulfillment
            # Налог (УСН) считается от "Продаж" (положительной части revenue), не вычитая комиссию WB
            # Грубая оценка: revenue (если > 0) * tax_rate
            tax_base = revenue if revenue > 0 else 0
            item_tax = tax_base * (cost_info["tax_rate"] / 100)
            metrics["tax"] += item_tax
            
            metrics["marketing"] += cost_info["external_marketing"] # Это daily fix cost на товар (упрощение)
            # Если маркетинг задан на единицу, то: cost_info["external_marketing"] * s_cnt
            
            metrics["cm3"] += 0 # Посчитаем в конце

        # Финализация расчетов
        result_list = []
        for date_key in sorted(daily_pnl.keys()):
            m = daily_pnl[date_key]
            
            m["gross_sales"] = m["net_sales"] # Если нет данных о возвратах в рублях отдельно, считаем Net=Gross
            
            m["cm1"] = m["net_sales"] - m["cogs"]
            
            wb_expenses = m["wb_commission"] + m["wb_logistics"] + m["wb_penalties"]
            m["cm2"] = m["cm1"] - wb_expenses
            
            other_expenses = m["tax"] + m["marketing"]
            m["cm3"] = m["cm2"] - other_expenses
            
            # Округление для UI
            for k, v in m.items():
                if isinstance(v, (int, float)):
                    m[k] = round(v, 2)
            
            result_list.append(m)
            
        return result_list

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

    @staticmethod
    def calculate_supply_metrics(current_stock: int, sales_history: list, lead_time_days: int = 14):
        if not sales_history:
            return {"status": "no_data", "message": "Нет данных", "recommendation": 0, "days_left": 999}
        avg_daily_sales = mean(sales_history) if sales_history else 0
        if avg_daily_sales == 0:
             return {"status": "ok", "message": "Продаж нет", "recommendation": 0, "days_left": 999, "safety_stock": 0}
        try: sigma_d = stdev(sales_history)
        except: sigma_d = avg_daily_sales * 0.5
        z_alpha = 1.65 
        sigma_l = 2 
        term1 = lead_time_days * (sigma_d ** 2)
        term2 = (avg_daily_sales ** 2) * (sigma_l ** 2)
        safety_stock = int(z_alpha * math.sqrt(term1 + term2))
        cycle_stock = avg_daily_sales * lead_time_days
        rop = int(cycle_stock + safety_stock)
        days_left = int(current_stock / avg_daily_sales)
        qty_to_order = 0
        status = "ok"
        message = "Запаса достаточно"
        if current_stock <= rop:
            target_level = rop + cycle_stock 
            qty_to_order = int(target_level - current_stock)
            if qty_to_order < 0: qty_to_order = 0
            if current_stock <= safety_stock:
                status = "critical"
                message = "Критический остаток!"
            else:
                status = "warning"
                message = "Пора заказывать"
        elif days_left < lead_time_days + 5:
             status = "warning"
             message = "Планируйте поставку"
        return {
            "status": status, "message": message, "days_left": days_left,
            "metrics": {"avg_sales": round(avg_daily_sales, 1), "volatility": round(sigma_d, 1), "safety_stock": safety_stock, "rop": rop},
            "recommendation": qty_to_order
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