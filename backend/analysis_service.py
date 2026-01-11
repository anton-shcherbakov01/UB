import os
import re
import json
import logging
import requests
import math
from statistics import mean, stdev
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
    def calculate_supply_metrics(current_stock: int, sales_history: list, lead_time_days: int = 14):
        """
        Расчет метрик Supply Chain по формулам из раздела 4.2 Плана.
        
        sales_history: список продаж по дням (int), например [5, 2, 0, 8, ...] за 30-60 дней.
        lead_time_days: срок поставки (L), по умолчанию 14 дней.
        """
        if not sales_history:
            return {
                "status": "no_data",
                "message": "Нет данных о продажах",
                "recommendation": 0,
                "days_left": 999
            }

        # 1. Основные статистики
        avg_daily_sales = mean(sales_history) if sales_history else 0
        
        # Если продаж нет
        if avg_daily_sales == 0:
             return {
                "status": "ok",
                "message": "Продаж нет",
                "recommendation": 0,
                "days_left": 999,
                "safety_stock": 0
            }

        # Стандартное отклонение спроса (sigma_D)
        # Если данных мало (1 день), stdev кидает ошибку, берем 0
        try:
            sigma_d = stdev(sales_history)
        except:
            sigma_d = avg_daily_sales * 0.5 # Эвристика для новых товаров

        # 2. Параметры модели
        # Уровень сервиса 95% -> Z = 1.65 (из плана)
        z_alpha = 1.65 
        
        # Стандартное отклонение времени поставки (sigma_L). 
        # Обычно это 1-2 дня для WB. Возьмем 2 дня для надежности.
        sigma_l = 2 

        # 3. Расчет страхового запаса (SS)
        # Формула: SS = Z * sqrt( L * sigma_D^2 + D_avg^2 * sigma_L^2 )
        term1 = lead_time_days * (sigma_d ** 2)
        term2 = (avg_daily_sales ** 2) * (sigma_l ** 2)
        safety_stock = int(z_alpha * math.sqrt(term1 + term2))

        # 4. Расчет точки заказа (ROP)
        # Формула: ROP = (D_avg * L) + SS
        cycle_stock = avg_daily_sales * lead_time_days
        rop = int(cycle_stock + safety_stock)

        # 5. Анализ текущей ситуации
        days_left = int(current_stock / avg_daily_sales)
        
        # Сколько нужно заказать?
        # Target Stock Level обычно ROP + Cycle Stock (или просто доводим до уровня ROP + запас на период)
        # Упрощенно: если мы ниже ROP, заказываем, чтобы покрыть lead_time + еще один цикл продаж
        qty_to_order = 0
        status = "ok"
        message = "Запаса достаточно"

        if current_stock <= rop:
            # Нужно заказать: (ROP + Cycle Stock) - Current Stock
            target_level = rop + cycle_stock 
            qty_to_order = int(target_level - current_stock)
            if qty_to_order < 0: qty_to_order = 0
            
            if current_stock <= safety_stock:
                status = "critical"
                message = "Критический остаток! Риск OOS"
            else:
                status = "warning"
                message = "Пора заказывать"

        elif days_left < lead_time_days + 5:
             # Мягкое предупреждение
             status = "warning"
             message = "Планируйте поставку"

        return {
            "status": status,
            "message": message,
            "days_left": days_left,
            "metrics": {
                "avg_sales": round(avg_daily_sales, 1),
                "volatility": round(sigma_d, 1), # Волатильность
                "safety_stock": safety_stock,
                "rop": rop
            },
            "recommendation": qty_to_order
        }

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
            "cm3": int(net_profit),
            "margin_percent": margin_percent,
            "roi": roi,
            "is_toxic": cm2 < 0 or net_profit < 0
        }

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