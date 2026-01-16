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

    def _call_ai(self, prompt: str, fallback_data: dict, temperature: float = 0.5):
        """
        Универсальный метод вызова LLM с авто-исправлением JSON.
        """
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": "You are a precise JSON generator. Output ONLY valid JSON without Markdown blocks (```json). Do not add comments."},
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            # Добавляем response_format, если API поддерживает (для OpenAI/DeepSeek это json_object)
            # Но для универсальности оставим пока текстом и будем парсить сами.
        }

        for attempt in range(3):
            try:
                logger.info(f"Запрос к AI API: {self.api_url}")
                response = requests.post(self.api_url, headers=self.headers, json=payload, timeout=60)
                
                if response.status_code != 200:
                    logger.error(f"AI API Error {response.status_code}: {response.text}")
                    time.sleep(2)
                    continue

                raw_content = response.json()['choices'][0]['message']['content']
                
                # --- AUTO-FIX JSON ---
                # 1. Убираем Markdown обертки ```json ... ```
                clean_json = re.sub(r'```json\s*|\s*```', '', raw_content).strip()
                
                # 2. Убираем странные символы в начале (BOM и прочее)
                clean_json = clean_json.strip('`').strip()
                
                # 3. Фикс распространенной ошибки: лишняя запятая в конце списка/объекта
                clean_json = re.sub(r',\s*([\]}])', r'\1', clean_json)
                
                # 4. Фикс ошибки из лога: AI иногда вставляет "&" перед объектом
                clean_json = re.sub(r':\s*&{', ': {', clean_json)

                try:
                    data = json.loads(clean_json)
                    return data
                except json.JSONDecodeError as e:
                    logger.error(f"JSON Parse Error: {e}. Content: {clean_json[:500]}")
                    # Если совсем плохо - попробуем найти первый { и последний }
                    try:
                        start = clean_json.find('{')
                        end = clean_json.rfind('}') + 1
                        if start != -1 and end != 0:
                            return json.loads(clean_json[start:end])
                    except: pass
                    
                    if attempt == 2:
                        fallback_data["_error"] = f"Ошибка парсинга JSON от AI: {str(e)}"
                        return fallback_data

            except Exception as e:
                logger.error(f"AI Connection Error: {e}")
                time.sleep(2)

        fallback_data["_error"] = "AI сервис недоступен после 3 попыток"
        return fallback_data

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

    def generate_product_content(self, keywords: list, tone: str, title_len: int = 60, desc_len: int = 1000):
        """
        WB-Optimized Generation.
        Исправлена ошибка с кодировкой заголовка и увеличено кол-во FAQ.
        """
        # Сортировка ключей
        main_keywords = keywords[:5]
        lsi_keywords = keywords[5:]
        
        kw_str_main = ", ".join(main_keywords)
        kw_str_lsi = ", ".join(lsi_keywords)

        prompt = f"""
        Роль: Ты ведущий SEO-эксперт Wildberries. Твоя цель — создать карточку товара, которая займет ТОП-1 в органике.

        Входные данные:
        - Ключевые слова (ВЧ - обязательно в Заголовок и первый абзац): {kw_str_main}
        - LSI-фразы (НЧ - распределить по тексту): {kw_str_lsi}
        - Тон: {tone}
        - Лимит заголовка: {title_len} символов (СТРОГО! Не обрезай слова).

        ПРАВИЛА WILDBERRIES (ЗАПРЕТЫ):
        1. ⛔ НИКАКИХ ЭМОДЗИ. Текст должен быть чистым.
        2. ⛔ В Заголовке НЕ пиши название Бренда (оно подтягивается само).
        3. ⛔ В Заголовке НЕ используй слэши (/) и повторы слов.
           ПЛОХО: "Крем для лица / крем увлажняющий"
           ХОРОШО: "Крем для лица увлажняющий питательный ночной"
        4. ⛔ ЗАПРЕЩЕНО: "топ", "хит", "лучший", "акция", "скидка".
        5. ⛔ ЗАПРЕЩЕНО: КАПС (кроме ГОСТ, ПВХ и т.д.).

        СТРУКТУРА ОТВЕТА (JSON):
        {{
            "title": "Суть товара + 2-3 главные характеристики (Например: Швабра с отжимом и ведром для мытья полов)",
            "description": "Продающий SEO-текст.
             1 абзац: УТП товара, решение проблемы клиента + главные ключи.
             2 блок: Преимущества (списком с '•').
             3 блок: Для кого/чего подойдет.
             4 блок: Технические особенности.
             LSI-фразы вписывай органично.",
            "structured_features": {{
                "Назначение": "...",
                "Материал изделия": "...",
                "Комплектация": "...",
                "Страна производства": "..."
            }},
            "faq": [
                {{ "question": "Вопрос про размер/цвет", "answer": "Ответ" }},
                {{ "question": "Вопрос про упаковку (анонимность/надежность)", "answer": "Ответ" }},
                {{ "question": "Вопрос про способ применения", "answer": "Ответ" }},
                {{ "question": "Вопрос про брак/возврат", "answer": "Ответ" }},
                {{ "question": "Вопрос про срок годности/гарантию", "answer": "Ответ" }}
            ]
        }}
        """
        
        fallback = {
            "title": "Наименование товара", 
            "description": "Описание генерируется...", 
            "structured_features": {}, 
            "faq": []
        }
        
        result = self._call_ai(prompt, fallback, temperature=0.4)
        
        if "_error" in result:
            logger.error(f"AI WB Generation failed: {result['_error']}")
            return fallback
        
        # --- ФИНАЛЬНАЯ ЧИСТКА ---
        if "title" in result:
            # Убираем кавычки
            clean_title = result["title"].replace('"', '').replace("'", "").strip()
            
            # ВАЖНО: Убрал .encode('ascii'), который убивал русский текст.
            # Если нужно убрать эмодзи программно, лучше использовать regex,
            # но при temperature=0.4 модель обычно соблюдает запрет на эмодзи.
            
            # Убираем точку в конце заголовка (на WB заголовки без точек)
            if clean_title.endswith('.'):
                clean_title = clean_title[:-1]
                
            result["title"] = clean_title

        return result