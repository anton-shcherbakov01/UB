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
        self.ai_url = os.getenv("AI_API_URL", "https://api.artemox.com/v1/chat/completions")
        
        if not self.ai_api_key:
            logger.warning("⚠️ AI_API_KEY не установлен! AI функции будут возвращать заглушки.")

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
        # Проверка наличия API ключа
        if not self.ai_api_key:
            logger.error("AI_API_KEY не установлен. Пропуск AI запроса.")
            fallback_json["_error"] = "AI_API_KEY не настроен. Проверьте переменные окружения."
            return fallback_json
            
        try:
            payload = {
                "model": "deepseek-chat", 
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature
            }
            headers = {"Authorization": f"Bearer {self.ai_api_key}", "Content-Type": "application/json"}
            
            logger.info(f"Запрос к AI API: {self.ai_url}")
            resp = requests.post(self.ai_url, json=payload, headers=headers, timeout=90) 
            
            if resp.status_code != 200:
                error_text = resp.text[:500] if resp.text else "Нет ответа"
                logger.error(f"AI API Error {resp.status_code}: {error_text}")
                fallback_json["_error"] = f"AI API вернул ошибку {resp.status_code}: {error_text}"
                return fallback_json
            
            result = resp.json()
            if 'choices' not in result or not result['choices']:
                logger.error(f"AI API вернул некорректный ответ: {result}")
                fallback_json["_error"] = "AI API вернул некорректный формат ответа"
                return fallback_json
                
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
                    logger.warning(f"No JSON found in AI response. Content preview: {content[:200]}...")
                    fallback_json["_error"] = f"AI вернул некорректный формат. Первые 200 символов: {content[:200]}"
                    return fallback_json
            except json.JSONDecodeError as e:
                logger.error(f"JSON Parse Error: {e}. Content: {content[:300]}")
                fallback_json["_error"] = f"Ошибка парсинга JSON от AI: {str(e)}"
                return fallback_json
        except requests.exceptions.Timeout:
            logger.error(f"AI API Timeout после 90 секунд")
            fallback_json["_error"] = "Таймаут запроса к AI API (90s)"
            return fallback_json
        except requests.exceptions.ConnectionError as e:
            logger.error(f"AI API Connection Error: {e}")
            fallback_json["_error"] = f"Ошибка соединения с AI API: {str(e)}"
            return fallback_json
        except Exception as e:
            logger.error(f"AI Connection Error: {e}", exc_info=True)
            fallback_json["_error"] = f"Неожиданная ошибка AI: {str(e)}"
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
        
        # Если была ошибка AI, логируем и добавляем информацию в ответ
        if "_error" in ai_response:
            logger.error(f"AI анализ провалился: {ai_response['_error']}")
            # Добавляем информацию об ошибке в глобальное резюме для отображения пользователю
            ai_response["global_summary"] = f"⚠️ Ошибка AI: {ai_response['_error']}"
            ai_response["flaws"] = [f"AI сервис недоступен: {ai_response['_error']}"]
            ai_response["strategy"] = ["Проверьте настройки AI_API_KEY в переменных окружения"]
        
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
        WB-Optimized Generation.
        Создает контент строго по правилам ранжирования Wildberries (SEO + LSI).
        Без эмодзи, спама и запрещенных слов.
        """
        # Сортируем ключи: сначала самые важные (обычно первые в списке), остальные для LSI
        main_keywords = keywords[:5]
        lsi_keywords = keywords[5:]
        
        kw_str_main = ", ".join(main_keywords)
        kw_str_lsi = ", ".join(lsi_keywords)

        prompt = f"""
        Роль: Ты ведущий эксперт по ранжированию карточек на Wildberries и SEO-копирайтер.
        Твоя задача — создать текст карточки товара, который выведет её в ТОП органической выдачи.

        Входные данные:
        - Главные ключи (вписать в заголовок и первые абзацы): {kw_str_main}
        - LSI-ключи (равномерно распределить по тексту): {kw_str_lsi}
        - Тон (Tone of Voice): {tone} (но сохраняй экспертность)
        - Лимит заголовка: до {title_len} символов.
        - Лимит описания: до {desc_len} символов.

        СТРОГИЕ ЗАПРЕТЫ (Правила Wildberries):
        1. ⛔ ЗАПРЕЩЕНО использовать эмодзи (смайлики). Текст должен быть чистым.
        2. ⛔ ЗАПРЕЩЕНО использовать слова: "лучший", "самый", "номер один", "скидка", "акция", "распродажа", "дешевый".
        3. ⛔ ЗАПРЕЩЕНО писать КАПСОМ (кроме аббревиатур вроде ПВХ, ГОСТ).
        4. ⛔ ЗАПРЕЩЕНО указывать контакты, ссылки, призывы перейти на сайт.

        Требования к структуре описания:
        1. Первый абзац: УТП товара + вхождение главного ключа. Закрытие боли клиента.
        2. Характеристики и преимущества: Используй маркированный список (символы "-" или "•").
        3. Сценарии использования: Для кого и для чего подходит.
        4. Технические детали: Материал, размеры, уход.

        Формат ответа (JSON):
        {{
            "title": "Читаемый заголовок (Бренд / Тип товара / Главная особенность)",
            "description": "Текст описания, разбитый на абзацы. Без воды.",
            "structured_features": {{
                "Материал изделия": "...",
                "Назначение": "...",
                "Комплектация": "...",
                "Страна производства": "..."
            }},
            "faq": [
                {{ "question": "Частый вопрос покупателя WB", "answer": "Короткий и четкий ответ" }},
                {{ "question": "Вопрос про уход/размер", "answer": "Ответ" }}
            ]
        }}
        """
        
        fallback = {
            "title": "Товар Wildberries", 
            "description": "Описание временно недоступно. Пожалуйста, проверьте API ключ.", 
            "structured_features": {}, 
            "faq": []
        }
        
        # temperature=0.5 делает AI более "сосредоточенным" и менее склонным к галлюцинациям
        result = self._call_ai(prompt, fallback, temperature=0.5)
        
        if "_error" in result:
            logger.error(f"AI WB Generation failed: {result['_error']}")
            # Возвращаем хоть что-то, чтобы фронт не упал
            return fallback
        
        return result