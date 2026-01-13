import os
import re
import json
import logging
import requests
from typing import Dict, Any

logger = logging.getLogger("Analysis-AI")

class AIModule:
    def __init__(self):
        self.ai_api_key = os.getenv("AI_API_KEY", "") 
        self.ai_url = "https://api.artemox.com/v1/chat/completions"

    def clean_ai_text(self, text: str) -> str:
        if not text: return ""
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text) 
        text = re.sub(r'#+\s?', '', text)
        text = text.replace("`", "")
        return text.strip()

    def _clean_recursive(self, data):
        if isinstance(data, dict):
            return {k: self._clean_recursive(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._clean_recursive(i) for i in data]
        elif isinstance(data, str):
            return self.clean_ai_text(data)
        else:
            return data

    def _call_ai(self, prompt: str, fallback_json: dict, temperature: float = 0.7):
        try:
            payload = {
                "model": "deepseek-chat", 
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature
            }
            headers = {"Authorization": f"Bearer {self.ai_api_key}", "Content-Type": "application/json"}
            resp = requests.post(self.ai_url, json=payload, headers=headers, timeout=90) 
            if resp.status_code != 200:
                logger.error(f"AI API Error: {resp.text}")
                return fallback_json
            
            result = resp.json()
            content = result['choices'][0]['message']['content']
            try:
                # Очистка Markdown-блоков кода
                content = re.sub(r'^```json\s*', '', content, flags=re.MULTILINE)
                content = re.sub(r'^```\s*', '', content, flags=re.MULTILINE)
                content = content.strip()

                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    # Рекурсивная очистка
                    return self._clean_recursive(parsed)
                else: 
                    logger.warning(f"No JSON found in AI response: {content[:100]}...")
                    return fallback_json
            except Exception as e:
                logger.error(f"JSON Parse Error: {e}")
                return fallback_json
        except Exception as e:
            logger.error(f"AI Connection Error: {e}")
            return fallback_json

    def analyze_reviews_with_ai(self, reviews: list, product_name: str) -> Dict[str, Any]:
        """
        Комплексный анализ отзывов с использованием DeepSeek-V3.
        1. ABSA (Aspect-Based Sentiment Analysis).
        2. Психографическое профилирование.
        """
        if not reviews: 
            return {
                "aspects": [], 
                "audience_stats": {"rational": 0, "emotional": 0, "skeptic": 0},
                "global_summary": "Нет данных для анализа",
                "flaws": ["Нет отзывов"], 
                "strategy": ["Соберите первые отзывы"]
            }

        reviews_text = ""
        for r in reviews[:40]:
            clean_text = r['text'].replace('\n', ' ').strip()
            if len(clean_text) > 5:
                text = f"- {clean_text} (Оценка: {r['rating']})\n"
                if len(reviews_text) + len(text) < 4000: 
                    reviews_text += text
                else: 
                    break
        
        prompt = f"""
        Роль: Ты Lead Data Analyst в E-commerce. Твоя специализация — ABSA и Психография.
        
        Товар: "{product_name}".
        Отзывы покупателей:
        {reviews_text}

        Выполни глубокий анализ по двум направлениям:

        НАПРАВЛЕНИЕ 1: Аспектный анализ (ABSA)
        - Выдели ключевые аспекты (Aspect = Entity + Attribute).
        - Оцени каждый аспект по шкале Valence (Тональность) от 1.00 (Крайний негатив) до 9.00 (Восхищение).
        - Найди цитату (Snippet) и дай совет (Actionable Advice).

        НАПРАВЛЕНИЕ 2: Психографическое профилирование аудитории
        - Определи, к какому типу относится большинство авторов отзывов:
          A. Rational (Рациональный): Факты, цифры, срок службы.
          B. Emotional (Эмоциональный): Стиль, восторг, упаковка, "вау-эффект".
          C. Skeptic (Скептик): Сомнения, поиск брака, проверка гарантий.
        - Рассчитай примерный процент (%) каждого типа в выборке.
        - На основе ДОМИНИРУЮЩЕГО типа сгенерируй рекомендацию для инфографики (Infographic Tip).

        Формат ответа (СТРОГО JSON):
        {{
            "aspects": [
                {{
                    "aspect": "Название аспекта",
                    "sentiment_score": 2.5,
                    "snippet": "цитата",
                    "actionable_advice": "совет"
                }}
            ],
            "audience_stats": {{
                "rational_percent": 30,
                "emotional_percent": 50,
                "skeptic_percent": 20
            }},
            "dominant_type": "Emotional",
            "infographic_recommendation": "Текст рекомендации...",
            "global_summary": "Общее резюме (1 предложение)"
        }}
        """
        
        fallback = {
            "aspects": [],
            "audience_stats": {"rational_percent": 33, "emotional_percent": 33, "skeptic_percent": 34},
            "dominant_type": "Mixed",
            "infographic_recommendation": "Проверьте качество контента",
            "global_summary": "Ошибка анализа нейросети",
            "flaws": ["Ошибка API"],
            "strategy": ["Повторите попытку"]
        }
        
        ai_response = self._call_ai(prompt, fallback, temperature=0.5)
        
        # Post-Processing
        aspects = ai_response.get("aspects", [])
        
        negative_aspects = sorted(
            [a for a in aspects if a.get('sentiment_score', 5) < 4.5], 
            key=lambda x: x['sentiment_score']
        )
        ai_response["flaws"] = [f"{a['aspect']}: {a['snippet'][:50]}..." for a in negative_aspects[:5]]
        
        positive_strategies = [a['actionable_advice'] for a in aspects if a.get('sentiment_score', 0) < 7.5]
        ai_response["strategy"] = positive_strategies[:7] if positive_strategies else ["Масштабируйте продажи"]

        if not ai_response["flaws"]:
            ai_response["flaws"] = ["Критических проблем не выявлено"]

        return ai_response

    def generate_product_content(self, keywords: list, tone: str, title_len: int = 100, desc_len: int = 1000):
        """
        GEO-Optimized Generation (Generative Engine Optimization).
        Создает контент, оптимизированный для AI-поисковиков (Perplexity, SGE, Yandex GPT).
        Включает структурированные данные и FAQ.
        """
        kw_str = ", ".join(keywords)
        prompt = f"""
        Роль: Ты профессиональный SEO-копирайтер уровня Senior, специализирующийся на GEO (Generative Engine Optimization).
        Твоя задача — создать контент для Wildberries, который легко считывается AI-алгоритмами и ранжируется в SGE.

        Входные данные:
        - Ключевые слова: {kw_str}
        - Тон (Tone of Voice): {tone}
        - Лимит заголовка: ~{title_len} симв.
        - Лимит описания: ~{desc_len} симв.

        Требования к структуре (GEO Standards):
        1. Extractability: Используй маркированные списки и четкие сущности.
        2. Authority: Добавь таблицу характеристик для сравнения.
        3. User Intent: Добавь блок FAQ (3-5 вопросов), закрывающий боли Рационалов, Эмоционалов и Скептиков.

        Верни ответ СТРОГО в формате JSON:
        {{
            "title": "Продающий заголовок с вхождением топ ключей",
            "description": "Основной текст описания с LSI-фразами и структурированными списками...",
            "structured_features": {{
                "Материал": "...",
                "Назначение": "...",
                "Особенность": "..."
            }},
            "faq": [
                {{ "question": "Вопрос клиента", "answer": "Экспертный ответ" }},
                {{ "question": "Вопрос про гарантию", "answer": "Ответ про надежность" }}
            ]
        }}
        """
        
        fallback = {
            "title": "Ошибка генерации", 
            "description": "Не удалось сгенерировать текст", 
            "structured_features": {}, 
            "faq": []
        }
        
        return self._call_ai(prompt, fallback, temperature=0.7)