"""
Code Embedding Service (Infrastructure)

SOTA: Semantic similarity using TF-IDF (production-proven)

Strict Rules:
- NO fake similarity scores
- NO hardcoded embeddings
- Real TF-IDF implementation
- Future: CodeBERT integration (NotImplementedError)
"""

import logging

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class CodeEmbeddingService:
    """
    코드 임베딩 서비스 (Infrastructure)

    책임:
    - 코드 텍스트 → 벡터 변환
    - Semantic similarity 계산

    Implementation:
    - TF-IDF (현재)
    - CodeBERT (future, NotImplementedError)

    Note:
    - Infrastructure layer (Domain에서 직접 사용 금지)
    - Application layer에서 사용
    """

    def __init__(self, use_pretrained: bool = False):
        """
        Args:
            use_pretrained: CodeBERT 사용 여부
        """
        self.use_pretrained = use_pretrained
        self._model = None

        if use_pretrained:
            try:
                # sentence-transformers 기반 code embedding
                from sentence_transformers import SentenceTransformer

                # CodeBERT 또는 유사 모델
                self._model = SentenceTransformer("microsoft/codebert-base")
                logger.info("CodeEmbeddingService initialized with CodeBERT")
            except ImportError:
                logger.warning("sentence-transformers not available, falling back to TF-IDF")
                self.use_pretrained = False
            except Exception as e:
                logger.warning(f"Failed to load CodeBERT: {e}, falling back to TF-IDF")
                self.use_pretrained = False

        if not self.use_pretrained:
            self.vectorizer = TfidfVectorizer(
                max_features=1000, ngram_range=(1, 2), stop_words="english", lowercase=True
            )
            self._fitted = False
            self._corpus: list[str] = []
            logger.info("CodeEmbeddingService initialized with TF-IDF")

    def fit(self, code_samples: list[str]) -> None:
        """
        코드 샘플로 vectorizer 학습

        Args:
            code_samples: 코드 문자열 목록

        Raises:
            ValueError: 샘플이 비어있는 경우
        """
        if not code_samples:
            raise ValueError("code_samples cannot be empty")

        logger.info(f"Fitting vectorizer with {len(code_samples)} samples")

        self._corpus = code_samples
        self.vectorizer.fit(code_samples)
        self._fitted = True

        logger.info("Vectorizer fitted successfully")

    def embed(self, code: str) -> np.ndarray:
        """
        코드 → 벡터 변환 (CodeBERT 또는 TF-IDF)

        Args:
            code: 코드 문자열

        Returns:
            벡터 (numpy array)
        """
        # CodeBERT 사용
        if self.use_pretrained and self._model is not None:
            try:
                embedding = self._model.encode(code, convert_to_numpy=True)
                return embedding
            except Exception as e:
                logger.warning(f"CodeBERT encoding failed: {e}, falling back to TF-IDF")
                self.use_pretrained = False

        # TF-IDF 사용
        if not self._fitted:
            # Auto-fit with single sample (for testing)
            logger.warning("Vectorizer not fitted, auto-fitting with input")
            self.fit([code])

        vector = self.vectorizer.transform([code]).toarray()[0]

        return vector

    def similarity(self, code1: str, code2: str) -> float:
        """
        두 코드 간 cosine similarity 계산

        Args:
            code1: 첫 번째 코드
            code2: 두 번째 코드

        Returns:
            Cosine similarity (0.0~1.0)
        """
        if not self._fitted:
            # Auto-fit with both samples
            logger.warning("Vectorizer not fitted, auto-fitting")
            self.fit([code1, code2])

        vec1 = self.embed(code1).reshape(1, -1)
        vec2 = self.embed(code2).reshape(1, -1)

        sim = cosine_similarity(vec1, vec2)[0][0]

        # Ensure [0.0, 1.0] range
        sim = max(0.0, min(1.0, sim))

        return float(sim)

    def batch_similarity(self, query_code: str, code_samples: list[str]) -> list[float]:
        """
        Query와 여러 코드 샘플 간 similarity 계산

        Args:
            query_code: Query 코드
            code_samples: 비교할 코드 목록

        Returns:
            Similarity 점수 목록
        """
        if not code_samples:
            return []

        if not self._fitted:
            # Fit with all samples
            all_samples = [query_code] + code_samples
            self.fit(all_samples)

        query_vec = self.embed(query_code).reshape(1, -1)

        similarities = []
        for code in code_samples:
            code_vec = self.embed(code).reshape(1, -1)
            sim = cosine_similarity(query_vec, code_vec)[0][0]
            sim = max(0.0, min(1.0, sim))
            similarities.append(float(sim))

        return similarities
