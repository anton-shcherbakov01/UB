import logging
import numpy as np
from typing import List, Dict, Any

logger = logging.getLogger("Analysis-Clustering")

try:
    from sentence_transformers import SentenceTransformer
    # Заменяем KMeans на AgglomerativeClustering для автоматического определения числа групп
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.metrics.pairwise import cosine_similarity
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

class ClusteringModule:
    def __init__(self):
        self._embedder = None

    def _get_embedder(self):
        if not ML_AVAILABLE:
            raise ImportError("Install 'sentence-transformers' and 'scikit-learn'")
        if self._embedder is None:
            logger.info("Loading BERT model for clustering...")
            # Модель 'all-MiniLM-L6-v2' легкая и быстрая, отлично подходит для русского языка (multilingual версии)
            # Если нужна строго русская, можно взять 'cointegrated/rubert-tiny2', но MiniLM универсальнее
            self._embedder = SentenceTransformer('all-MiniLM-L6-v2')
        return self._embedder

    def cluster_keywords(self, keywords: List[str]) -> Dict[str, Any]:
        """
        Умная кластеризация на основе Agglomerative Clustering.
        Группирует фразы по смыслу, автоматически определяя количество групп.
        """
        if not keywords:
            return {"status": "error", "message": "Empty keywords list"}
        
        # Убираем дубликаты и пустые строки, сохраняя порядок
        unique_keywords = list(dict.fromkeys([k.strip() for k in keywords if k.strip()]))
        
        if len(unique_keywords) < 2:
            return {
                "status": "success",
                "clusters": [{"topic": unique_keywords[0], "keywords": unique_keywords, "count": 1}] if unique_keywords else [],
                "total_keywords": len(unique_keywords),
                "n_clusters": 1
            }

        if not ML_AVAILABLE:
            return {"status": "error", "message": "ML libraries missing."}

        try:
            model = self._get_embedder()
            
            # 1. Векторизация (Embeddings)
            embeddings = model.encode(unique_keywords)
            
            # Нормализуем векторы для корректной работы косинусного расстояния
            embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

            # 2. Иерархическая кластеризация
            # distance_threshold=1.5 -> параметр "строгости". 
            # Чем МЕНЬШЕ, тем более похожими должны быть фразы, чтобы попасть в одну группу.
            # Для MiniLM значения обычно варьируются от 1.0 до 1.5 (Euclidean over normalized vectors ~ Cosine)
            # При affinity='euclidean' и linkage='ward' на нормализованных векторах это работает как косинусная близость.
            clustering_model = AgglomerativeClustering(
                n_clusters=None,           # Автоматическое число кластеров
                distance_threshold=1.2,    # Порог объединения (подбирается экспериментально, 1.2 - сбалансировано)
                metric='euclidean',
                linkage='ward'
            )
            
            labels = clustering_model.fit_predict(embeddings)

            # 3. Группировка результатов
            clusters_map = {}
            for keyword, label in zip(unique_keywords, labels):
                lbl_str = str(label)
                if lbl_str not in clusters_map:
                    clusters_map[lbl_str] = []
                clusters_map[lbl_str].append(keyword)

            # 4. Формирование красивого вывода
            named_clusters = []
            for _, kw_list in clusters_map.items():
                # Выбор названия темы:
                # Берем самую короткую фразу, так как она часто является "ядром" (напр. "платье" vs "платье красное длинное")
                # Либо, если список длинный, можно искать центроид, но min(len) работает хорошо и быстро.
                kw_list_sorted = sorted(kw_list, key=len)
                topic_name = kw_list_sorted[0] 
                
                # Делаем первую букву заглавной
                topic_name = topic_name.capitalize()

                named_clusters.append({
                    "topic": topic_name,
                    "keywords": kw_list,
                    "count": len(kw_list)
                })

            # Сортируем кластеры по количеству ключевиков (самые крупные первыми)
            named_clusters.sort(key=lambda x: x['count'], reverse=True)

            return {
                "status": "success",
                "clusters": named_clusters,
                "total_keywords": len(unique_keywords),
                "n_clusters": len(named_clusters)
            }

        except Exception as e:
            logger.error(f"Clustering failed: {e}")
            return {"status": "error", "message": str(e)}