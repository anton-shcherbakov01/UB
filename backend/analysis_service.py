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
        raw_data["metrics"] = {
            "wallet_benefit": standard - wallet if standard > wallet else 0,
            "total_discount_percent": round(((base - wallet) / base * 100), 1) if base > 0 else 0,
            "is_favorable": ((base - wallet) / base) > 0.45 if base > 0 else False
        }
        return raw_data

    def clean_ai_text(self, text: str) -> str:
        if not text: return ""
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text) 
        text = re.sub(r'#+\s?', '', text)
        return text.replace("`", "").strip()

    def analyze_reviews_with_ai(self, reviews: list, product_name: str):
        if not reviews: return {"flaws": ["Нет отзывов"], "strategy": ["-"]}

        reviews_text = "\n".join([f"- {r['text'][:200]} ({r['rating']}*)" for r in reviews[:25]])
        
        prompt = f"""
        Проанализируй товар WB: "{product_name}".
        Отзывы:
        {reviews_text}
        
        Напиши 3 минуса и 5 советов продавцу.
        Ответ JSON:
        {{
            "flaws": ["...", "...", "..."],
            "strategy": ["...", "...", "...", "...", "..."]
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
                return {"flaws": ["Ошибка ИИ"], "strategy": ["Попробуйте позже"]}
            
            content = resp.json()['choices'][0]['message']['content']
            
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                parsed = json.loads(json_match.group(0))
                parsed['flaws'] = [self.clean_ai_text(str(f)) for f in parsed.get('flaws', [])]
                parsed['strategy'] = [self.clean_ai_text(str(s)) for s in parsed.get('strategy', [])]
                return parsed
            else:
                return {"flaws": ["Формат ответа неверен"], "strategy": [self.clean_ai_text(content[:200])]}

        except Exception as e:
            logger.error(f"AI Error: {e}")
            return {"flaws": ["Сбой"], "strategy": ["Ошибка подключения"]}

analysis_service = AnalysisService()