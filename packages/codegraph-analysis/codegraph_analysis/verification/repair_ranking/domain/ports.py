"""
Repair Ranking Ports (Contract-First Design)

RFC-SEM-001 Section 2: Repair Ranking System

Architecture: Hexagonal (Port-Adapter)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class PatchCandidate:
    """
    Patch candidate (immutable)

    Fields:
    - patch_id: Unique identifier
    - original_code: Before code
    - patched_code: After code
    - description: What this patch does
    - metadata: Additional info (e.g., LLM params)
    """

    patch_id: str
    original_code: str
    patched_code: str
    description: str
    metadata: dict[str, any] = None

    def __post_init__(self):
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})


@dataclass
class ScoreResult:
    """
    Score result from a scorer

    Fields:
    - score: 0.0-1.0 (1.0 = best)
    - reasoning: Why this score?
    - details: Additional metrics
    """

    score: float  # 0.0-1.0
    reasoning: str
    details: dict[str, any] = None

    def __post_init__(self):
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"Score must be 0.0-1.0, got {self.score}")
        if self.details is None:
            object.__setattr__(self, "details", {})


# ============================================================
# Scorer Port (Contract)
# ============================================================


class IScorerPort(ABC):
    """
    Scorer interface (Port)

    All scorers must implement this contract.

    Contract:
    - Input: PatchCandidate
    - Output: ScoreResult (0.0-1.0)
    - Stateless: No side effects
    - Deterministic: Same input → same output

    Example:
        scorer = TaintRegressionScorer(...)
        result = scorer.score(patch)
        print(f"Score: {result.score}, Reason: {result.reasoning}")
    """

    @abstractmethod
    def score(self, patch: PatchCandidate) -> ScoreResult:
        """
        Score a patch candidate

        Args:
            patch: Patch candidate

        Returns:
            ScoreResult (0.0-1.0)

        Raises:
            ValueError: If patch invalid

        Contract:
        - Must be deterministic
        - Must be stateless
        - Must return 0.0-1.0
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """
        Get scorer name

        Returns:
            Scorer name (e.g., "taint_regression", "complexity")
        """
        pass

    @abstractmethod
    def get_weight(self) -> float:
        """
        Get default weight for this scorer

        Returns:
            Weight (0.0-1.0)

        Note: Weights should sum to 1.0 across all scorers
        """
        pass
