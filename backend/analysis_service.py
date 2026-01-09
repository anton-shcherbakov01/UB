import os
import re
import json
import logging
import requests

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

        try:
            payload = {
                "model": "deepseek-chat", 
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5
            }
            headers = {"Authorization": f"Bearer {self.ai_api_key}", "Content-Type": "application/json"}
            
            resp = requests.post(self.ai_url, json=payload, headers=headers, timeout=60)
            
            if resp.status_code != 200:
                logger.error(f"AI API Error: {resp.text}")
                return {"flaws": ["Ошибка ИИ"], "strategy": [f"Статус {resp.status_code}"]}
            
            result = resp.json()
            content = result['choices'][0]['message']['content']
            
            try:
                # Пытаемся найти JSON в ответе (иногда модель пишет текст вокруг)
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    # Очищаем строки
                    parsed['flaws'] = [self.clean_ai_text(str(f)) for f in parsed.get('flaws', [])]
                    parsed['strategy'] = [self.clean_ai_text(str(s)) for s in parsed.get('strategy', [])]
                    return parsed
                else:
                    return {"flaws": ["Формат ответа неверен"], "strategy": [self.clean_ai_text(content[:100])]}
            except Exception as e:
                logger.error(f"JSON Parse Error: {e}")
                return {"flaws": ["Ошибка обработки"], "strategy": ["Не удалось прочитать ответ ИИ"]}

        except Exception as e:
            logger.error(f"AI Connection Error: {e}")
            return {"flaws": ["Сбой сети"], "strategy": ["Ошибка подключения к AI"]}

analysis_service = AnalysisService()