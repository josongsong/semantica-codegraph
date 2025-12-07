"""
Budget Manager - Token budget enforcement for LLM context

Relevance-based pruning to keep slice under token limit.
"""

import logging
from dataclasses import dataclass
from typing import Literal

from .slicer import SliceResult

logger = logging.getLogger(__name__)


@dataclass
class BudgetConfig:
    """Budget 설정"""

    max_tokens: int = 8000
    """최대 토큰 수"""

    min_tokens: int = 500
    """최소 토큰 수 (너무 작으면 경고)"""

    summarization_threshold: int = 200
    """이 라인 수 이상의 함수는 요약"""

    # Relevance weights
    distance_weight: float = 0.5
    """Distance score 가중치"""

    effect_weight: float = 0.3
    """Effect score 가중치"""

    recency_weight: float = 0.1
    """Recency score 가중치"""

    hotspot_weight: float = 0.1
    """Hotspot score 가중치"""


@dataclass
class RelevanceScore:
    """Node 중요도 점수"""

    node_id: str
    """PDG node ID"""

    score: float
    """Total relevance score (0.0-1.0)"""

    distance_score: float = 0.0
    """PDG distance 기반 점수"""

    effect_score: float = 0.0
    """Side effect 기반 점수"""

    recency_score: float = 0.0
    """최근 수정 기반 점수"""

    hotspot_score: float = 0.0
    """변경 빈도 기반 점수"""

    reason: Literal["distance", "effect", "recency", "hotspot"] = "distance"
    """주요 이유"""

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "score": self.score,
            "distance": self.distance_score,
            "effect": self.effect_score,
            "recency": self.recency_score,
            "hotspot": self.hotspot_score,
            "reason": self.reason,
        }


class BudgetManager:
    """
    Token Budget Manager

    Relevance-based pruning to keep slice under budget.
    """

    def __init__(self, config: BudgetConfig, pdg_builder=None, git_service=None):
        self.config = config
        self.pdg_builder = pdg_builder
        self.git_service = git_service  # CRITICAL FIX: git_service 저장 필수
        self._node_cache = {}  # Cache for node statements
        # Import here to avoid circular dependency
        from .relevance import RelevanceScorer

        self.relevance_scorer = RelevanceScorer(None, git_service)

    def batch_fetch_git_metadata(
        self,
        node_ids: set[str],
        file_path: str | None = None,
    ) -> dict:
        """
        Batch Git metadata fetching (성능 최적화)

        Args:
            node_ids: PDG node IDs
            file_path: Optional file path (모든 node가 같은 파일이면)

        Returns:
            {node_id: {last_modified, churn}}
        """
        if not self.git_service:
            return {}

        metadata = {}

        # File-level metadata (한 번만 fetch)
        if file_path:
            try:
                file_meta = self.git_service.get_file_metadata(file_path)

                # 모든 node에 동일한 file metadata 적용
                for node_id in node_ids:
                    metadata[node_id] = {
                        "last_modified": file_meta.last_modified,
                        "churn": file_meta.commit_count,
                    }
            except Exception as e:
                logger.warning(f"Git metadata fetch failed for {file_path}: {e}")
        else:
            # Node별로 fetch (fallback)
            for node_id in node_ids:
                if self.pdg_builder:
                    node = self.pdg_builder.nodes.get(node_id)
                    if node and node.file_path:
                        try:
                            file_meta = self.git_service.get_file_metadata(node.file_path)
                            metadata[node_id] = {
                                "last_modified": file_meta.last_modified,
                                "churn": file_meta.commit_count,
                            }
                        except:
                            pass  # Skip on error

        return metadata

    def apply_budget(
        self,
        slice_result: SliceResult,
        pdg_distance_map: dict[str, int],
        node_statements: dict[str, str] | None = None,
        git_metadata: dict | None = None,
    ) -> SliceResult:
        """
        Budget 적용 (초과 시 pruning)

        Args:
            slice_result: Original slice
            pdg_distance_map: {node_id: distance from target}

        Returns:
            Pruned SliceResult (if needed)

        Raises:
            BudgetExceededError: If cannot meet min_tokens
        """
        logger.info(f"Applying budget: max={self.config.max_tokens}, min={self.config.min_tokens}")

        # Estimate current tokens
        current_tokens = slice_result.estimate_tokens()

        # Budget 내면 그대로 반환
        if current_tokens <= self.config.max_tokens:
            logger.debug(f"Within budget: {current_tokens}/{self.config.max_tokens}")
            slice_result.total_tokens = current_tokens
            return slice_result

        logger.warning(f"Over budget: {current_tokens} > {self.config.max_tokens}, pruning...")

        # Cache node statements if provided
        if node_statements:
            self._node_cache = node_statements

        # FIXED: Batch fetch Git metadata if not provided
        if git_metadata is None and self.git_service:
            git_metadata = self.batch_fetch_git_metadata(slice_result.slice_nodes)

        # Relevance scores 계산 (git_metadata 전달)
        relevance_scores = self._compute_relevance(
            slice_result.slice_nodes,
            pdg_distance_map,
            git_metadata,
        )

        # Score 순으로 정렬
        sorted_scores = sorted(relevance_scores, key=lambda s: s.score, reverse=True)

        # Budget 내에서 Top-K 선택
        selected_nodes = set()
        accumulated_tokens = 0

        for score in sorted_scores:
            # Estimate node tokens (rough)
            node_tokens = self._estimate_node_tokens(score.node_id, slice_result)

            # Budget 초과하면 중단
            if accumulated_tokens + node_tokens > self.config.max_tokens:
                break

            selected_nodes.add(score.node_id)
            accumulated_tokens += node_tokens

        # Filter code fragments
        filtered_fragments = [frag for frag in slice_result.code_fragments if frag.node_id in selected_nodes]

        # Update relevance scores
        for frag in filtered_fragments:
            score = next((s for s in relevance_scores if s.node_id == frag.node_id), None)
            if score:
                frag.relevance_score = score.score

        # Create pruned result
        return SliceResult(
            target_variable=slice_result.target_variable,
            slice_type=slice_result.slice_type,
            slice_nodes=selected_nodes,
            code_fragments=filtered_fragments,
            control_context=slice_result.control_context,
            total_tokens=accumulated_tokens,
            confidence=slice_result.confidence * 0.9,  # Penalty for pruning
            metadata={
                **slice_result.metadata,
                "pruned": True,
                "original_nodes": len(slice_result.slice_nodes),
                "selected_nodes": len(selected_nodes),
                "reduction_ratio": 1 - len(selected_nodes) / len(slice_result.slice_nodes),
            },
        )

    def _compute_relevance(
        self,
        node_ids: set[str],
        pdg_distance_map: dict[str, int],
        git_metadata: dict | None = None,
    ) -> list[RelevanceScore]:
        """
        모든 node의 relevance 계산

        FIXED: RelevanceScorer 사용 (중복 제거)

        Args:
            node_ids: PDG node IDs
            pdg_distance_map: Distance from target
            git_metadata: Optional {node_id: {last_modified, churn}}

        Returns:
            List of RelevanceScores
        """
        scores = []

        # Max distance 계산
        max_distance = max(pdg_distance_map.values()) if pdg_distance_map else 1

        for node_id in node_ids:
            # Get node statement
            statement = ""
            if self.pdg_builder:
                node = self.pdg_builder.nodes.get(node_id)
                if node:
                    statement = node.statement
            elif self._node_cache:
                statement = self._node_cache.get(node_id, "")

            # FIXED: Use RelevanceScorer (no duplication)
            distance = pdg_distance_map.get(node_id, max_distance)

            factors = self.relevance_scorer.score_node(
                node_id=node_id,
                node_statement=statement,
                pdg_distance=distance,
                max_distance=max_distance,
                git_metadata=git_metadata,
            )

            # Calculate total score with config weights
            total_score = (
                self.config.distance_weight * factors.distance
                + self.config.effect_weight * factors.effect
                + self.config.recency_weight * factors.recency
                + self.config.hotspot_weight * factors.hotspot
            )

            # Determine dominant reason
            reason = self._determine_reason(factors.distance, factors.effect, factors.recency, factors.hotspot)

            scores.append(
                RelevanceScore(
                    node_id=node_id,
                    score=total_score,
                    distance_score=factors.distance,
                    effect_score=factors.effect,
                    recency_score=factors.recency,
                    hotspot_score=factors.hotspot,
                    reason=reason,
                )
            )

        return scores

        # REMOVED: _calculate_recency_score (use RelevanceScorer instead)

        # REMOVED: _calculate_hotspot_score (use RelevanceScorer instead)  # Default (not a hotspot)

        churn = git_metadata[node_id].get("churn", 0)

        # Scoring: high churn = high score (frequently changed)
        if churn >= 10:
            return 1.0
        elif churn >= 5:
            return 0.6
        elif churn >= 2:
            return 0.3
        else:
            return 0.0

    # REMOVED: _estimate_effect_score (use RelevanceScorer instead)

    def _estimate_node_tokens(self, node_id: str, slice_result: SliceResult) -> int:
        """
        Node의 토큰 수 추정

        Args:
            node_id: PDG node ID
            slice_result: Slice result

        Returns:
            Estimated tokens
        """
        # Find fragment
        fragment = next((f for f in slice_result.code_fragments if f.node_id == node_id), None)

        if not fragment:
            return 10  # Default

        # 1 line ≈ 10 tokens
        lines = fragment.end_line - fragment.start_line + 1
        return lines * 10

    def _determine_reason(
        self,
        distance: float,
        effect: float,
        recency: float,
        hotspot: float,
    ) -> Literal["distance", "effect", "recency", "hotspot"]:
        """
        주요 이유 결정

        Returns:
            Dominant factor
        """
        scores = {
            "distance": distance * self.config.distance_weight,
            "effect": effect * self.config.effect_weight,
            "recency": recency * self.config.recency_weight,
            "hotspot": hotspot * self.config.hotspot_weight,
        }

        return max(scores, key=scores.get)  # type: ignore

    def check_budget(self, slice_result: SliceResult) -> dict:
        """
        Budget 상태 체크

        Args:
            slice_result: Slice result

        Returns:
            Budget status dict
        """
        tokens = slice_result.total_tokens or slice_result.estimate_tokens()

        return {
            "tokens": tokens,
            "max_tokens": self.config.max_tokens,
            "usage_ratio": tokens / self.config.max_tokens,
            "over_budget": tokens > self.config.max_tokens,
            "needs_pruning": tokens > self.config.max_tokens,
            "reduction_needed": max(0, tokens - self.config.max_tokens),
        }
