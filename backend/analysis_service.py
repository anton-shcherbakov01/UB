import os
import re
import json
import logging
import requests
import math
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from database import ProductCost
from clickhouse_models import ch_service
from forecasting import forecast_demand

# ML Imports (Lazy Loading pattern to prevent crash if libs are missing)
try:
    from sentence_transformers import SentenceTransformer
    from sklearn.cluster import KMeans
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

logger = logging.getLogger("AI-Service")

class AnalysisService:
    def __init__(self):
        self.ai_api_key = os.getenv("AI_API_KEY", "") 
        self.ai_url = "https://api.artemox.com/v1/chat/completions"
        self._embedder = None # Lazy load model
        try:
            ch_service.connect()
        except Exception as e:
            logger.warning(f"ClickHouse init failed (will retry on usage): {e}")

    # --- SEMANTIC CLUSTERING (NEW) ---

    def _get_embedder(self):
        """Singleton pattern for heavy BERT model"""
        if not ML_AVAILABLE:
            raise ImportError("Install 'sentence-transformers' and 'scikit-learn'")
        if self._embedder is None:
            logger.info("Loading BERT model for clustering...")
            # Using a lightweight model suitable for CPU
            self._embedder = SentenceTransformer('all-MiniLM-L6-v2')
        return self._embedder

    def cluster_keywords(self, keywords: List[str]) -> Dict[str, Any]:
        """
        Кластеризация ключевых слов по семантической близости (BERT + K-Means).
        Позволяет группировать запросы по интенту (смыслу), а не просто по вхождению слов.
        """
        if not keywords:
            return {"status": "error", "message": "Empty keywords list"}
        
        if not ML_AVAILABLE:
            return {
                "status": "error", 
                "message": "ML libraries missing. Install sentence-transformers & scikit-learn."
            }

        try:
            model = self._get_embedder()
            
            # 1. Векторизация (Embeddings)
            embeddings = model.encode(keywords)
            
            # 2. Определение оптимального числа кластеров
            # Эвристика: ~5 ключей на кластер, минимум 2 кластера (если ключей > 5)
            n_clusters = max(2, len(keywords) // 5)
            if len(keywords) < 5:
                n_clusters = 1
            
            # 3. Кластеризация K-Means
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            kmeans.fit(embeddings)
            labels = kmeans.labels_
            
            # 4. Группировка результатов
            clusters = {}
            for keyword, label in zip(keywords, labels):
                lbl_str = str(label)
                if lbl_str not in clusters:
                    clusters[lbl_str] = []
                clusters[lbl_str].append(keyword)
            
            # 5. Нейминг кластеров (берем самое короткое слово как название темы)
            named_clusters = []
            for _, kw_list in clusters.items():
                topic_name = min(kw_list, key=len) # Самое короткое слово ~ тема
                named_clusters.append({
                    "topic": topic_name,
                    "keywords": kw_list,
                    "count": len(kw_list)
                })
                
            return {
                "status": "success",
                "clusters": named_clusters,
                "total_keywords": len(keywords),
                "n_clusters": n_clusters
            }

        except Exception as e:
            logger.error(f"Clustering failed: {e}")
            return {"status": "error", "message": str(e)}

    # --- FORECASTING & SUPPLY CHAIN METRICS ---

    def calculate_supply_metrics(
        self, 
        current_stock: int, 
        sales_history: List[Dict[str, Any]], 
        forecast_data: Optional[Dict[str, Any]] = None,
        lead_time_days: int = 7,  # Среднее время поставки
        lead_time_sigma: int = 2, # Отклонение времени поставки (дней)
        service_level_z: float = 1.65 # Z-score для 95% уровня сервиса
    ) -> Dict[str, Any]:
        """
        Расчет точки заказа (ROP) и страхового запаса (Safety Stock).
        """
        
        # 1. Определяем спрос (Demand)
        if forecast_data and forecast_data.get("status") == "success":
            avg_daily_demand = forecast_data.get("daily_avg_forecast", 0)
            forecast_points = forecast_data.get("forecast_points", [])
            demand_during_lead_time = sum([p['yhat'] for p in forecast_points[:lead_time_days]])
        else:
            if not sales_history:
                return {"status": "error", "message": "No data"}
            values = [x['qty'] for x in sales_history if x['qty'] > 0]
            if not values:
                return {"status": "error", "message": "Zero sales"}
            avg_daily_demand = np.mean(values)
            demand_during_lead_time = avg_daily_demand * lead_time_days

        # 2. Считаем стандартное отклонение спроса (sigma_Demand)
        if sales_history:
            hist_values = [x['qty'] for x in sales_history]
            sigma_demand = np.std(hist_values) if len(hist_values) > 1 else 0
        else:
            sigma_demand = 0

        # 3. Расчет Safety Stock
        term1 = lead_time_days * (sigma_demand ** 2)
        term2 = (avg_daily_demand ** 2) * (lead_time_sigma ** 2)
        safety_stock = service_level_z * math.sqrt(term1 + term2)
        
        # 4. Расчет ROP
        rop = demand_during_lead_time + safety_stock
        
        # 5. Интерпретация
        days_left = current_stock / avg_daily_demand if avg_daily_demand > 0 else 999
        
        safety_stock = int(math.ceil(safety_stock))
        rop = int(math.ceil(rop))
        days_left = int(days_left)
        
        status = "ok"
        recommendation = "Запаса достаточно"
        
        if current_stock <= 0:
            status = "out_of_stock"
            recommendation = "Товара нет в наличии!"
        elif current_stock < safety_stock:
            status = "critical"
            recommendation = "Срочно пополнить! (Ниже страхового запаса)"
        elif current_stock < rop:
            status = "warning"
            recommendation = f"Пора заказывать (Ниже точки заказа {rop} шт)"
            
        return {
            "status": status,
            "recommendation": recommendation,
            "metrics": {
                "safety_stock": safety_stock,
                "rop": rop,
                "days_left": days_left,
                "avg_daily_demand": round(avg_daily_demand, 1),
                "demand_lead_time": round(demand_during_lead_time, 1),
                "current_stock": current_stock
            },
            "inputs": {
                "lead_time": lead_time_days,
                "service_level": "95%"
            }
        }

    # --- P&L ANALYTICS ---

    async def get_pnl_data(self, user_id: int, date_from: datetime, date_to: datetime, db: AsyncSession) -> List[Dict[str, Any]]:
        ch_query = """
        SELECT 
            toDate(sale_dt) as report_date,
            nm_id,
            sumIf(retail_price_withdisc_rub, doc_type_name = 'Продажа') as gross_sales,
            sumIf(retail_price_withdisc_rub, doc_type_name = 'Возврат') as returns_sum,
            countIf(doc_type_name = 'Продажа') as qty_sold,
            countIf(doc_type_name = 'Возврат') as qty_returned,
            sum(ppvz_sales_commission) as commission,
            sum(delivery_rub) as logistics,
            sum(penalty) as penalties,
            sum(additional_payment) as adjustments
        FROM wb_analytics.realization_reports
        WHERE supplier_id = %(uid)s 
          AND sale_dt >= %(start)s 
          AND sale_dt <= %(end)s
        GROUP BY report_date, nm_id
        ORDER BY report_date ASC
        """
        
        params = {'uid': user_id, 'start': date_from, 'end': date_to}
        
        try:
            ch_client = ch_service.get_client()
            result = ch_client.query(ch_query, parameters=params)
            rows = result.result_rows
        except Exception as e:
            logger.error(f"ClickHouse Query Error: {e}")
            return []

        if not rows: return []

        unique_skus = list(set([row[1] for row in rows]))
        stmt = select(ProductCost).where(ProductCost.user_id == user_id, ProductCost.sku.in_(unique_skus))
        cogs_result = await db.execute(stmt)
        costs_map = {c.sku: c.cost_price for c in cogs_result.scalars().all()}

        daily_pnl = {}
        for row in rows:
            r_date, sku, gross_sales, returns_sum, qty_sold, qty_returned, commission, logistics, penalties, adjustments = row
            gross_sales, returns_sum = float(gross_sales), float(returns_sum)
            qty_sold, qty_returned = int(qty_sold), int(qty_returned)
            commission, logistics, penalties, adjustments = float(commission), float(logistics), float(penalties), float(adjustments)

            unit_cost = costs_map.get(sku, 0)
            total_cogs = (qty_sold * unit_cost) - (qty_returned * unit_cost)

            date_str = r_date.strftime("%Y-%m-%d")
            if date_str not in daily_pnl:
                daily_pnl[date_str] = {
                    "date": date_str, "gross_sales": 0.0, "net_sales": 0.0, "cogs": 0.0,
                    "commission": 0.0, "logistics": 0.0, "penalties": 0.0, "marketing": 0.0, 
                    "cm1": 0.0, "cm2": 0.0, "cm3": 0.0
                }
            d = daily_pnl[date_str]
            d["gross_sales"] += gross_sales
            d["net_sales"] += (gross_sales - returns_sum) 
            d["cogs"] += total_cogs
            d["commission"] += commission
            d["logistics"] += logistics
            d["penalties"] += (penalties + adjustments)
        
        final_output = []
        for date_str, metrics in sorted(daily_pnl.items()):
            metrics["cm1"] = metrics["net_sales"] - metrics["cogs"]
            metrics["cm2"] = metrics["cm1"] - metrics["commission"] - metrics["logistics"] - metrics["penalties"]
            metrics["cm3"] = metrics["cm2"] - metrics["marketing"]
            for k, v in metrics.items():
                if isinstance(v, float): metrics[k] = round(v, 2)
            final_output.append(metrics)
        return final_output

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

        # --- UPDATED: Умная склейка отзывов для большого объема данных ---
        reviews_text = ""
        # Увеличиваем лимит контекста, так как DeepSeek V3 поддерживает большой контекст
        max_chars = 12000 
        
        # Сначала берем самые информативные (длинные) отзывы
        sorted_reviews = sorted(reviews, key=lambda x: len(x['text']), reverse=True)
        
        # Если отзывов ОЧЕНЬ много (>200), берем микс из ТОП длинных (для информативности)
        # и ТОП новых (чтобы не анализировать только старые "портянки")
        if len(reviews) > 200:
            # Например: 50 самых длинных + 50 самых первых в списке (обычно это новые)
            # Примечание: предполагается, что reviews приходят отсортированные по дате (по умолчанию WB API)
            top_reviews = sorted_reviews[:50] + reviews[:50]
        else:
            top_reviews = sorted_reviews

        for r in top_reviews:
            clean_text = r['text'].replace('\n', ' ').strip()
            # Фильтруем совсем короткие отписки типа "Класс", "Норм"
            if len(clean_text) > 5:
                text = f"- {clean_text} (Оценка: {r['rating']})\n"
                if len(reviews_text) + len(text) < max_chars: 
                    reviews_text += text
                else: 
                    break
        
        prompt = f"""
        Роль: Ты Lead Data Analyst в E-commerce. Твоя специализация — ABSA и Психография.
        
        Товар: "{product_name}".
        Массив отзывов ({len(reviews)} всего, ниже выборка для анализа):
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
            "global_summary": "Общее резюме (1 предложение)",
            "flaws": ["Кратко недостатки"],
            "strategy": ["Кратко точки роста"]
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
        
        # Если AI не вернул flaws/strategy в JSON, генерируем их из аспектов
        if not ai_response.get("flaws"):
            negative_aspects = sorted(
                [a for a in aspects if a.get('sentiment_score', 5) < 4.5], 
                key=lambda x: x['sentiment_score']
            )
            ai_response["flaws"] = [f"{a['aspect']}: {a['snippet'][:50]}..." for a in negative_aspects[:5]]
        
        if not ai_response.get("strategy"):
            positive_strategies = [a['actionable_advice'] for a in aspects if a.get('sentiment_score', 0) < 7.5 and a.get('actionable_advice')]
            ai_response["strategy"] = positive_strategies[:7] if positive_strategies else ["Масштабируйте продажи"]

        if not ai_response.get("flaws"):
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

    def _clean_recursive(self, data):
        if isinstance(data, dict):
            return {k: self._clean_recursive(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._clean_recursive(i) for i in data]
        elif isinstance(data, str):
            return self.clean_ai_text(data)
        else:
            return data

analysis_service = AnalysisService()