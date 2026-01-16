import logging
import numpy as np
from typing import List, Dict, Any

logger = logging.getLogger("Analysis-Clustering")

try:
    from sentence_transformers import SentenceTransformer
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
            # ИСПОЛЬЗУЕМ БОЛЕЕ МОЩНУЮ МНОГОЯЗЫЧНУЮ МОДЕЛЬ
            # Она лучше понимает контекст русского языка, чем L6-v2
            self._embedder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        return self._embedder

    def cluster_keywords(self, keywords: List[str]) -> Dict[str, Any]:
        """
        Умная кластеризация с поиском центроидов для названия тем.
        """
        if not keywords:
            return {"status": "error", "message": "Empty keywords list"}
        
        # Чистка и дедупликация
        unique_keywords = list(dict.fromkeys([k.strip() for k in keywords if k.strip()]))
        
        if len(unique_keywords) < 2:
            return {
                "status": "success",
                "clusters": [{"topic": unique_keywords[0], "keywords": unique_keywords, "count": 1}] if unique_keywords else [],
                "n_clusters": 1
            }

        if not ML_AVAILABLE:
            return {"status": "error", "message": "ML libraries missing."}

        try:
            model = self._get_embedder()
            
            # 1. Векторизация
            embeddings = model.encode(unique_keywords)
            # Нормализация для Cosine Similarity через Euclidean distance
            embeddings = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)

            # 2. Кластеризация
            # distance_threshold: 
            # 1.0 - строгая кластеризация (фразы должны быть очень похожи)
            # 1.5 - мягкая (объединяет более далекие темы)
            # Оптимально для paraphrase-multilingual: 1.2 - 1.4
            clustering_model = AgglomerativeClustering(
                n_clusters=None, 
                distance_threshold=1.3, 
                metric='euclidean', # На нормализованных векторах это эквивалентно косинусному
                linkage='ward'
            )
            
            labels = clustering_model.fit_predict(embeddings)

            # 3. Сбор данных по группам
            # Нам нужно сохранить индексы, чтобы потом достать эмбеддинги для расчета центра
            temp_clusters = {}
            for idx, (keyword, label) in enumerate(zip(unique_keywords, labels)):
                lbl = str(label)
                if lbl not in temp_clusters:
                    temp_clusters[lbl] = {"keywords": [], "indices": []}
                
                temp_clusters[lbl]["keywords"].append(keyword)
                temp_clusters[lbl]["indices"].append(idx)

            # 4. Нейминг через ЦЕНТРОИДЫ (Самая важная часть улучшения)
            named_clusters = []
            
            for _, data in temp_clusters.items():
                kw_list = data["keywords"]
                indices = data["indices"]
                
                topic_name = kw_list[0] # Fallback
                
                if len(kw_list) > 1:
                    # Получаем векторы всех фраз этой группы
                    cluster_vectors = embeddings[indices]
                    
                    # Вычисляем средний вектор (центр масс кластера)
                    centroid = np.mean(cluster_vectors, axis=0).reshape(1, -1)
                    
                    # Ищем фразу, которая ближе всего к этому центру
                    # Это и будет "самая репрезентативная фраза" группы
                    similarities = cosine_similarity(centroid, cluster_vectors)
                    best_idx = np.argmax(similarities) # Индекс лучшей фразы внутри группы
                    
                    topic_name = kw_list[best_idx]
                
                # Форматирование
                topic_name = topic_name.capitalize()

                named_clusters.append({
                    "topic": topic_name,
                    "keywords": sorted(kw_list), # Сортируем внутри для красоты
                    "count": len(kw_list)
                })

            # Сортируем группы: сначала самые большие
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