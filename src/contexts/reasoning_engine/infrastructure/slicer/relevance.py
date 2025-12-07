"""
Multi-Factor Relevance Scoring

Proper relevance scoring with Effect System, Git metadata, and distance.
"""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class RelevanceFactors:
    """Relevance score factors"""

    distance: float  # PDG distance (0-1, closer = higher)
    effect: float  # Side effect importance (0-1)
    recency: float  # Recently modified (0-1)
    hotspot: float  # Frequently changed (0-1)
    complexity: float  # Code complexity (0-1)

    def weighted_score(
        self,
        w_distance: float = 0.35,
        w_effect: float = 0.25,
        w_recency: float = 0.15,
        w_hotspot: float = 0.15,
        w_complexity: float = 0.10,
    ) -> float:
        """Calculate weighted total score"""
        return (
            w_distance * self.distance
            + w_effect * self.effect
            + w_recency * self.recency
            + w_hotspot * self.hotspot
            + w_complexity * self.complexity
        )


class RelevanceScorer:
    """
    Multi-factor relevance scorer

    Combines multiple signals to rank node importance.
    """

    def __init__(
        self,
        effect_analyzer: any | None = None,
        git_service: any | None = None,
    ):
        # Use lazy initialization to avoid import in __init__
        self._effect_analyzer = effect_analyzer
        self._git_service = git_service

    @property
    def effect_analyzer(self):
        """Lazy initialization"""
        if self._effect_analyzer is None:
            from .effect_analyzer import EffectAnalyzer

            self._effect_analyzer = EffectAnalyzer()
        return self._effect_analyzer

    @property
    def git_service(self):
        """Lazy initialization"""
        if self._git_service is None:
            from .git_service import GitService

            self._git_service = GitService()
        return self._git_service

    def score_node(
        self,
        node_id: str,
        node_statement: str,
        pdg_distance: int,
        max_distance: int,
        git_metadata: dict | None = None,
    ) -> RelevanceFactors:
        """
        Score a single node

        Args:
            node_id: Node ID
            node_statement: Source code statement
            pdg_distance: Distance from target in PDG
            max_distance: Maximum distance in current slice
            git_metadata: Optional git metadata {node_id: {...}}

        Returns:
            RelevanceFactors
        """
        # 1. Distance score (inverse)
        distance_score = self._score_distance(pdg_distance, max_distance)

        # 2. Effect score (side effects = important)
        effect_score = self._score_effect(node_statement)

        # 3. Recency score (recently modified = important)
        recency_score = self._score_recency(node_id, git_metadata)

        # 4. Hotspot score (frequently changed = important)
        hotspot_score = self._score_hotspot(node_id, git_metadata)

        # 5. Complexity score (complex code = important)
        complexity_score = self._score_complexity(node_statement)

        return RelevanceFactors(
            distance=distance_score,
            effect=effect_score,
            recency=recency_score,
            hotspot=hotspot_score,
            complexity=complexity_score,
        )

    def _score_distance(self, distance: int, max_distance: int) -> float:
        """
        Distance-based score (closer = higher)

        Uses exponential decay.
        """
        if max_distance == 0:
            return 1.0

        # Exponential decay: e^(-k*d)
        k = 0.2  # Decay rate
        distance / max_distance
        return max(0.0, min(1.0, 1.0 / (1.0 + k * distance)))

    def _score_effect(self, statement: str) -> float:
        """
        Effect-based score (side effects = important)

        Uses actual EffectAnalyzer if available.
        """
        if self.effect_analyzer:
            try:
                effect_type = self.effect_analyzer.analyze_statement(statement)

                effect_scores = {
                    "PURE": 0.1,  # Pure functions, less important
                    "READ": 0.3,  # Reads state
                    "WRITE": 0.7,  # Writes state
                    "IO": 0.9,  # I/O operations
                    "SIDE_EFFECT": 1.0,  # General side effects
                    "UNKNOWN": 0.5,  # Default
                }

                return effect_scores.get(effect_type, 0.5)
            except:
                pass  # Fallback to heuristic

        # Heuristic-based scoring
        statement_lower = statement.lower()

        # High effect keywords
        if any(
            kw in statement_lower
            for kw in ["write", "delete", "update", "insert", "modify", "save", "commit", "execute", "run", "send"]
        ):
            return 0.9

        # Medium effect keywords
        if any(kw in statement_lower for kw in ["read", "get", "fetch", "load", "query", "open", "close", "connect"]):
            return 0.5

        # Assignment
        if "=" in statement and "==" not in statement:
            return 0.4

        # Pure/simple
        return 0.2

    def _score_recency(self, node_id: str, git_metadata: dict | None) -> float:
        """
        Recency-based score (recent = important)

        Uses actual Git data if available.
        """
        if not git_metadata:
            return 0.5  # Default

        if self.git_service:
            try:
                last_modified = self.git_service.get_last_modified(node_id)
                if last_modified:
                    return self._time_decay_score(last_modified)
            except:
                pass

        # Fallback to metadata
        last_modified_ts = git_metadata.get(f"{node_id}_modified", 0)
        if last_modified_ts > 0:
            return self._time_decay_score(last_modified_ts)

        return 0.5

    def _score_hotspot(self, node_id: str, git_metadata: dict | None) -> float:
        """
        Hotspot-based score (frequently changed = important)

        Uses actual Git churn data if available.
        """
        if not git_metadata:
            return 0.5

        if self.git_service:
            try:
                churn = self.git_service.get_churn(node_id)
                if churn is not None:
                    # Normalize to 0-1 (assuming max churn = 100)
                    return min(1.0, churn / 100.0)
            except:
                pass

        # Fallback to metadata
        churn = git_metadata.get(f"{node_id}_churn", 0)

        # Sigmoid normalization
        return 1.0 / (1.0 + 2.0 ** (-churn / 10.0))

    def _score_complexity(self, statement: str) -> float:
        """
        Complexity-based score (complex = important)

        Simple heuristic based on statement length and nesting.
        """
        # Line count
        lines = statement.count("\n") + 1

        # Nesting level (approximation)
        nesting = statement.count("    ") // 4  # Assume 4-space indent

        # Operators
        operators = sum(1 for c in statement if c in "+-*/<>=&|")

        # Combine
        complexity = (
            0.3 * min(1.0, lines / 20.0)  # Max 20 lines
            + 0.3 * min(1.0, nesting / 5.0)  # Max 5 levels
            + 0.4 * min(1.0, operators / 10.0)  # Max 10 operators
        )

        return complexity

    def _time_decay_score(self, timestamp: float) -> float:
        """
        Time decay: recent = higher score

        Args:
            timestamp: Unix timestamp or datetime

        Returns:
            Score 0-1
        """
        if isinstance(timestamp, datetime):
            timestamp = timestamp.timestamp()

        now = datetime.now(timezone.utc).timestamp()
        age_days = (now - timestamp) / (24 * 3600)

        # Decay over 90 days
        decay_period = 90.0

        return max(0.0, 1.0 - (age_days / decay_period))
