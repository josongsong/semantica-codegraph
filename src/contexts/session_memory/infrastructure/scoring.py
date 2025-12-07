"""
Memory Scoring Engine

SOTA 3-axis scoring: Similarity + Recency + Importance
Based on Generative Agents (Stanford 2023)
"""

import math
from datetime import datetime
from typing import Any

from .config import get_config
from .models import Episode, MemoryScore


class MemoryScoringEngine:
    """
    메모리 스코어링 엔진 (3축 평가)

    SOTA 논문 기반:
    - Generative Agents (2023): Recency + Importance + Relevance
    - Mem0: Adaptive scoring weights
    """

    def __init__(self, config: Any | None = None):
        """
        Initialize scoring engine

        Args:
            config: RetrievalConfig 또는 None (자동 로드)
        """
        self.config = config or get_config().retrieval

    def score_episode(
        self,
        episode: Episode,
        query_embedding: list[float] | None = None,
        current_time: datetime | None = None,
    ) -> MemoryScore:
        """
        에피소드 점수 계산 (3축)

        Args:
            episode: 평가할 에피소드
            query_embedding: 쿼리 임베딩 (similarity 계산용)
            current_time: 현재 시간 (recency 계산용)

        Returns:
            MemoryScore with composite score
        """
        current_time = current_time or datetime.now()

        # 1. Similarity score (semantic)
        similarity = self._calculate_similarity(episode, query_embedding)

        # 2. Recency score (time decay)
        recency = self._calculate_recency(episode.created_at, current_time)

        # 3. Importance score (intrinsic value)
        importance = self._calculate_importance(episode)

        return MemoryScore(
            memory_id=episode.id,
            similarity=similarity,
            recency=recency,
            importance=importance,
            w_similarity=self.config.weight_similarity,
            w_recency=self.config.weight_recency,
            w_importance=self.config.weight_importance,
        )

    def _calculate_similarity(
        self,
        episode: Episode,
        query_embedding: list[float] | None,
    ) -> float:
        """
        의미적 유사도 계산 (cosine similarity)

        Args:
            episode: 에피소드
            query_embedding: 쿼리 임베딩

        Returns:
            Similarity score (0.0-1.0)
        """
        if query_embedding is None or not episode.task_description_embedding:
            # Fallback: 속성 기반 매칭
            return 0.5  # Neutral score

        # Cosine similarity
        return self._cosine_similarity(
            query_embedding,
            episode.task_description_embedding,
        )

    def _calculate_recency(
        self,
        created_at: datetime,
        current_time: datetime,
    ) -> float:
        """
        최근성 점수 계산 (exponential decay)

        Score = exp(-age_days / decay_half_life)

        Args:
            created_at: 생성 시간
            current_time: 현재 시간

        Returns:
            Recency score (0.0-1.0)
        """
        age_days = (current_time - created_at).total_seconds() / 86400.0

        # Exponential decay
        decay = math.exp(-age_days / self.config.recency_decay_days)

        return min(1.0, max(0.0, decay))

    def _calculate_importance(self, episode: Episode) -> float:
        """
        중요도 점수 계산 (intrinsic value)

        Factors:
        - Outcome status (success > partial > failure)
        - Retrieval count (how often accessed)
        - Usefulness score (user feedback)
        - Complexity (steps count)

        Args:
            episode: 에피소드

        Returns:
            Importance score (0.0-1.0)
        """
        importance = 0.0

        # 1. Outcome status (0.4 weight)
        if episode.outcome_status.value == "success":
            importance += 0.4
        elif episode.outcome_status.value == "partial":
            importance += 0.2

        # 2. Retrieval count (0.3 weight) - normalized
        retrieval_score = min(1.0, episode.retrieval_count / 10.0)
        importance += 0.3 * retrieval_score

        # 3. Usefulness score (0.2 weight)
        importance += 0.2 * episode.usefulness_score

        # 4. Complexity bonus (0.1 weight) - longer tasks = more valuable
        complexity_score = min(1.0, episode.steps_count / 50.0)
        importance += 0.1 * complexity_score

        return min(1.0, importance)

    def _cosine_similarity(
        self,
        vec1: list[float],
        vec2: list[float],
    ) -> float:
        """
        코사인 유사도 계산

        Args:
            vec1: 벡터 1
            vec2: 벡터 2

        Returns:
            Cosine similarity (0.0-1.0)
        """
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec1, vec2, strict=False))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        similarity = dot_product / (norm1 * norm2)

        # Normalize to 0-1 range (cosine can be -1 to 1)
        return (similarity + 1.0) / 2.0

    def rank_episodes(
        self,
        episodes: list[Episode],
        query_embedding: list[float] | None = None,
        top_k: int | None = None,
    ) -> list[tuple[Episode, MemoryScore]]:
        """
        에피소드 순위 매기기 (composite score 기준)

        Args:
            episodes: 평가할 에피소드 목록
            query_embedding: 쿼리 임베딩
            top_k: 상위 K개 (None = 전체)

        Returns:
            (Episode, MemoryScore) 튜플 리스트 (정렬됨)
        """
        if not episodes:
            return []

        top_k = top_k or self.config.default_top_k
        current_time = datetime.now()

        # Score all episodes
        scored = [(ep, self.score_episode(ep, query_embedding, current_time)) for ep in episodes]

        # Sort by composite score (descending)
        scored.sort(key=lambda x: x[1].composite_score, reverse=True)

        return scored[:top_k]

    def update_importance_on_retrieval(self, episode: Episode) -> None:
        """
        검색 시 중요도 업데이트 (retrieval count 증가)

        자주 검색되는 메모리 = 중요한 메모리

        Args:
            episode: 에피소드 (in-place 수정)
        """
        episode.retrieval_count += 1

        # Boost usefulness score slightly
        episode.usefulness_score = min(1.0, episode.usefulness_score + 0.05)


class AdaptiveScoringEngine(MemoryScoringEngine):
    """
    적응형 스코어링 엔진

    사용자 피드백에 따라 가중치 자동 조정
    """

    def __init__(self, config: Any | None = None):
        """Initialize adaptive engine"""
        super().__init__(config)
        self.feedback_history: list[dict[str, Any]] = []

    def record_feedback(
        self,
        episode: Episode,
        helpful: bool,
        score: MemoryScore,
    ) -> None:
        """
        사용자 피드백 기록

        Args:
            episode: 에피소드
            helpful: 도움 여부
            score: 당시 계산된 점수
        """
        self.feedback_history.append(
            {
                "episode_id": episode.id,
                "helpful": helpful,
                "similarity": score.similarity,
                "recency": score.recency,
                "importance": score.importance,
                "composite": score.composite_score,
            }
        )

        # Auto-tune weights (simple version)
        if len(self.feedback_history) >= 10:
            self._auto_tune_weights()

    def _auto_tune_weights(self) -> None:
        """
        피드백 기반 가중치 자동 조정

        높은 점수 + 도움 = 좋은 가중치
        높은 점수 + 도움 안됨 = 나쁜 가중치
        """
        # Simple heuristic: 마지막 10개 피드백 분석
        recent = self.feedback_history[-10:]

        helpful = [f for f in recent if f["helpful"]]
        unhelpful = [f for f in recent if not f["helpful"]]

        if not helpful or not unhelpful:
            return  # Not enough data

        # 도움이 된 케이스의 평균 점수
        avg_helpful = {
            "similarity": sum(f["similarity"] for f in helpful) / len(helpful),
            "recency": sum(f["recency"] for f in helpful) / len(helpful),
            "importance": sum(f["importance"] for f in helpful) / len(helpful),
        }

        # 도움이 안 된 케이스의 평균 점수
        avg_unhelpful = {
            "similarity": sum(f["similarity"] for f in unhelpful) / len(unhelpful),
            "recency": sum(f["recency"] for f in unhelpful) / len(unhelpful),
            "importance": sum(f["importance"] for f in unhelpful) / len(unhelpful),
        }

        # 차이가 큰 축에 더 높은 가중치
        diff_similarity = abs(avg_helpful["similarity"] - avg_unhelpful["similarity"])
        diff_recency = abs(avg_helpful["recency"] - avg_unhelpful["recency"])
        diff_importance = abs(avg_helpful["importance"] - avg_unhelpful["importance"])

        total_diff = diff_similarity + diff_recency + diff_importance
        if total_diff == 0:
            return

        # 정규화
        self.config.weight_similarity = diff_similarity / total_diff
        self.config.weight_recency = diff_recency / total_diff
        self.config.weight_importance = diff_importance / total_diff

        # 로깅
        from src.infra.observability import get_logger

        logger = get_logger(__name__)
        logger.info(
            "adaptive_weights_updated",
            sim=f"{self.config.weight_similarity:.2f}",
            rec=f"{self.config.weight_recency:.2f}",
            imp=f"{self.config.weight_importance:.2f}",
        )
