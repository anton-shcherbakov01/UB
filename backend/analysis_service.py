import os
import re
import aiohttp
import json
import logging

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

    async def analyze_reviews_with_ai(self, reviews: list, product_name: str):
        if not reviews: return {"error": "Отзывы не найдены"}

        reviews_text = "\n".join([f"- {r['text']} ({r['rating']}*)" for r in reviews[:20]])
        
        prompt = f"""
        Анализ товара WB: "{product_name}".
        Отзывы:
        {reviews_text}
        
        Задача:
        1. 3 главных минуса.
        2. 5 советов для конкурента (как сделать лучше).
        
        JSON ответ:
        {{
            "flaws": ["минус 1", "минус 2", "минус 3"],
            "strategy": ["совет 1", "совет 2", "совет 3", "совет 4", "совет 5"]
        }}
        """

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": "deepseek-chat", 
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5
                }
                headers = {"Authorization": f"Bearer {self.ai_api_key}", "Content-Type": "application/json"}
                
                async with session.post(self.ai_url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        return {"error": f"Ошибка ИИ: {resp.status}"}
                    
                    result = await resp.json()
                    content = result['choices'][0]['message']['content']
                    
                    try:
                        json_match = re.search(r'\{.*\}', content, re.DOTALL)
                        if json_match:
                            parsed = json.loads(json_match.group(0))
                            parsed['flaws'] = [self.clean_ai_text(f) for f in parsed['flaws']]
                            parsed['strategy'] = [self.clean_ai_text(s) for s in parsed['strategy']]
                            return parsed
                        else:
                            return {"flaws": ["Ошибка формата"], "strategy": [self.clean_ai_text(content[:200])]}
                    except:
                        return {"error": "Ошибка парсинга ответа ИИ"}

        except Exception as e:
            logger.error(f"AI Error: {e}")
            return {"error": "Сбой соединения с ИИ"}

analysis_service = AnalysisService()