import os
import re
import json
import logging
import requests
from datetime import datetime, timedelta

logger = logging.getLogger("AI-Service")

class AnalysisService:
    def __init__(self):
        self.ai_api_key = os.getenv("AI_API_KEY", "") 
        self.ai_url = "https://api.artemox.com/v1/chat/completions" 

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
    def calculate_pnl(
        price: float, 
        quantity_sold: int,
        logistics_wb: float, 
        commission_wb: float,
        advertising_wb: float,
        cost_price: float,
        fulfillment: float,
        external_marketing: float,
        tax_rate: float
    ):
        """
        Расчет Unit-экономики и P&L (Profit and Loss) согласно плану.
        
        Иерархия маржинальности:
        1. Gross Sales = Цена * Кол-во
        2. Net Sales = Gross Sales - Возвраты (упрощенно считаем в quantity_sold чистые продажи)
        3. CM1 (Marginal Profit) = Net Sales - COGS (Себестоимость)
        4. CM2 (Operational Margin) = CM1 - (Логистика + Комиссия + Фулфилмент + Налоги)
        5. CM3 (Net Margin) = CM2 - Маркетинг (Внутренний + Внешний)
        """
        
        # 1. Gross Sales (Выручка)
        gross_sales = price * quantity_sold
        
        # 2. COGS (Cost of Goods Sold)
        total_cogs = cost_price * quantity_sold
        
        # 3. CM1
        cm1 = gross_sales - total_cogs
        
        # Переменные расходы WB и Операционные
        total_commission = commission_wb * quantity_sold
        total_logistics = logistics_wb * quantity_sold
        total_fulfillment = fulfillment * quantity_sold
        total_tax = (gross_sales * (tax_rate / 100))
        
        operational_expenses = total_commission + total_logistics + total_fulfillment + total_tax
        
        # 4. CM2
        cm2 = cm1 - operational_expenses
        
        # Маркетинг
        total_marketing = (advertising_wb * quantity_sold) + external_marketing # external считаем как фикс на объем
        
        # 5. CM3 (Net Profit)
        net_profit = cm2 - total_marketing
        
        # Метрики
        margin_percent = round((net_profit / gross_sales * 100), 1) if gross_sales > 0 else 0
        roi = round((net_profit / (total_cogs + total_marketing) * 100), 1) if (total_cogs + total_marketing) > 0 else 0
        
        return {
            "gross_sales": int(gross_sales),
            "cogs": int(total_cogs),
            "cm1": int(cm1),
            "expenses": {
                "commission": int(total_commission),
                "logistics": int(total_logistics),
                "fulfillment": int(total_fulfillment),
                "tax": int(total_tax)
            },
            "cm2": int(cm2),
            "marketing": {
                "internal": int(advertising_wb * quantity_sold),
                "external": int(external_marketing)
            },
            "cm3": int(net_profit), # Чистая прибыль
            "margin_percent": margin_percent,
            "roi": roi,
            "is_toxic": cm2 < 0 or net_profit < 0
        }

    @staticmethod
    def calculate_supply_prediction(current_stock: int, sales_velocity: float):
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
        kw_str = ", ".join(keywords)
        prompt = f"""
        Ты профессиональный SEO-копирайтер для Wildberries.
        Задача: Написать продающий заголовок и описание товара.
        Параметры:
        - Ключевые слова: {kw_str}
        - Тон текста: {tone}
        - Длина заголовка: ~{title_len} символов.
        - Длина описания: ~{desc_len} символов.
        Ответ верни СТРОГО в JSON:
        {{
            "title": "Заголовок",
            "description": "Описание..."
        }}
        """
        return self._call_ai(prompt, {"title": "Ошибка генерации", "description": "Не удалось сгенерировать текст"})

    def _call_ai(self, prompt: str, fallback_json: dict):
        try:
            payload = {
                "model": "deepseek-chat", 
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5 
            }
            auth_header = self.ai_api_key if self.ai_api_key.startswith("Bearer ") else f"Bearer {self.ai_api_key}"
            headers = {"Authorization": auth_header, "Content-Type": "application/json"}
            resp = requests.post(self.ai_url, json=payload, headers=headers, timeout=60)
            
            if resp.status_code != 200: 
                logger.error(f"AI API Error: {resp.text}")
                return fallback_json
            
            content = resp.json()['choices'][0]['message']['content']
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                return json.loads(json_match.group(0))
            return fallback_json
        except Exception as e:
            logger.error(f"AI Error: {e}")
            return fallback_json

analysis_service = AnalysisService()