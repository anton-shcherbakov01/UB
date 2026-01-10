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
        """
        Расчет дней до обнуления (Out-of-Stock).
        sales_velocity: продаж в день.
        """
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
        """
        [NEW] Расчет выгоды транзита (из Roadmap 3.2.2).
        volume_liters: объем поставки в литрах.
        Возвращает сравнение прямой поставки и транзита.
        """
        # Примерные тарифы (в продакшене брать из API)
        # Коледино: Коэффициент х1, базовая приемка 30р/литр
        koledino_direct_cost = volume_liters * 30 * 1 
        
        # Казань: Коэффициент х0, транзит 1500р/палета + приемка бесплатно
        # Упрощенная логика: 1500р фикс за транзит
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
        """
        Синхронный метод (выполняется в Celery).
        """
        if not reviews: 
            return {"flaws": ["Нет отзывов"], "strategy": ["Недостаточно данных"]}

        # Готовим текст отзывов (не более 2000 символов суммарно)
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

    def generate_product_content(self, keywords: list, tone: str):
        """
        Генерация SEO заголовка и описания на основе ключевых слов.
        """
        kw_str = ", ".join(keywords)
        
        prompt = f"""
        Ты профессиональный SEO-копирайтер для Wildberries.
        Задача: Написать продающий заголовок и описание товара.
        
        Ключевые слова: {kw_str}
        Тон текста: {tone} (Учитывай это при написании!)
        
        Требования:
        1. Заголовок: до 100 символов, максимально релевантный, используй главные ключи.
        2. Описание: 1000-1500 символов, структурированное, с использованием всех ключевых слов. Без воды.
        
        Ответ верни СТРОГО в JSON:
        {{
            "title": "Сгенерированный заголовок",
            "description": "Сгенерированное описание..."
        }}
        """
        
        return self._call_ai(prompt, {"title": "Ошибка генерации", "description": "Не удалось сгенерировать текст"})

    def _call_ai(self, prompt: str, fallback_json: dict):
        """Вспомогательный метод вызова AI"""
        try:
            payload = {
                "model": "deepseek-chat", 
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7 # Чуть выше для креатива
            }
            headers = {"Authorization": f"Bearer {self.ai_api_key}", "Content-Type": "application/json"}
            
            resp = requests.post(self.ai_url, json=payload, headers=headers, timeout=90) # Увеличили таймаут для генерации текста
            
            if resp.status_code != 200:
                logger.error(f"AI API Error: {resp.text}")
                return fallback_json
            
            result = resp.json()
            content = result['choices'][0]['message']['content']
            
            try:
                # Пытаемся найти JSON
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    # Чистим значения
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