import os
import re
import aiohttp
import json
import logging

logger = logging.getLogger("AI-Service")

class AnalysisService:
    """
    Микросервис аналитики и ИИ.
    Отвечает за расчет метрик и общение с нейросетями.
    """
    def __init__(self):
        self.ai_api_key = os.getenv("AI_API_KEY", "") # Ключ Artemox/DeepSeek
        self.ai_url = "https://api.artemox.com/v1/chat/completions" # Пример URL, замените на актуальный для Artemox

    @staticmethod
    def calculate_metrics(raw_data: dict):
        if raw_data.get("status") == "error":
            return raw_data

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
        """Очищает ответ ИИ от мусора (звездочки, решетки, markdown)"""
        if not text: return ""
        # Удаляем жирный шрифт (**текст**)
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        # Удаляем заголовки (###)
        text = re.sub(r'#+\s?', '', text)
        # Удаляем лишние переносы
        text = text.strip()
        return text

    async def analyze_reviews_with_ai(self, reviews: list, product_name: str):
        """
        Отправляет отзывы в ИИ и получает стратегию.
        """
        if not reviews:
            return {"error": "Нет отзывов для анализа"}

        # Готовим промпт
        reviews_text = "\n".join([f"- {r['text']} (Рейтинг: {r['rating']})" for r in reviews[:30]]) # Берем топ-30 для анализа
        
        prompt = f"""
        Ты — эксперт по E-commerce и маркетплейсу Wildberries.
        Проанализируй отзывы на товар: "{product_name}".
        
        Список отзывов:
        {reviews_text}
        
        Твоя задача:
        1. Выдели 3 самых частых недостатка, на которые жалуются клиенты.
        2. Напиши "Стратегию победы": 5 конкретных пунктов, как мне (продавцу) отстроиться от этого конкурента, исправив его ошибки.
        
        Ответ дай в формате JSON:
        {{
            "flaws": ["недостаток 1", "недостаток 2", "недостаток 3"],
            "strategy": ["пункт 1", "пункт 2", "пункт 3", "пункт 4", "пункт 5"],
            "summary": "Краткий вывод одним предложением"
        }}
        Не пиши ничего лишнего, только JSON.
        """

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": "deepseek-chat", # Или актуальная модель на Artemox
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7
                }
                headers = {"Authorization": f"Bearer {self.ai_api_key}", "Content-Type": "application/json"}
                
                async with session.post(self.ai_url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        logger.error(f"AI Error: {await resp.text()}")
                        return {"error": "ИИ не отвечает, попробуйте позже"}
                    
                    result = await resp.json()
                    content = result['choices'][0]['message']['content']
                    
                    # Пытаемся распарсить JSON из ответа ИИ
                    try:
                        # Иногда ИИ оборачивает JSON в ```json ... ```
                        clean_json = re.search(r'\{.*\}', content, re.DOTALL)
                        if clean_json:
                            parsed = json.loads(clean_json.group(0))
                            # Чистим текст внутри JSON
                            parsed['flaws'] = [self.clean_ai_text(f) for f in parsed['flaws']]
                            parsed['strategy'] = [self.clean_ai_text(s) for s in parsed['strategy']]
                            return parsed
                        else:
                            return {"error": "Ошибка формата ответа ИИ"}
                    except:
                        return {"raw_text": self.clean_ai_text(content)}

        except Exception as e:
            logger.error(f"AI Critical Error: {e}")
            return {"error": "Сбой соединения с ИИ"}

analysis_service = AnalysisService()