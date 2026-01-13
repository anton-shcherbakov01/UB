import logging
from typing import List, Dict, Any

logger = logging.getLogger("Analysis-Clustering")

# Lazy Loading pattern to prevent crash if libs are missing
try:
    from sentence_transformers import SentenceTransformer
    from sklearn.cluster import KMeans
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False

class ClusteringModule:
    def __init__(self):
        self._embedder = None

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