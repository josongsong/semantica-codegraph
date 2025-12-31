"""
Repair Ranking Models

RFC-SEM-001 Section 2: Repair Ranking System
"""

from dataclasses import dataclass


@dataclass
class RankingResult:
    """
    Ranking result

    Fields:
    - ranked_patches: List of (patch, score, details)
    - canonical_patch: Best patch (Top-1)
    - total_candidates: Total input patches
    - valid_candidates: Patches that passed hard filter

    Immutable: frozen=True
    """

    ranked_patches: list[tuple[any, float, dict]]  # (patch, score, details)
    canonical_patch: any  # PatchCandidate
    total_candidates: int
    valid_candidates: int

    def get_top_k(self, k: int = 3) -> list:
        """Get top-k patches"""
        return [p[0] for p in self.ranked_patches[:k]]

    def get_scores(self) -> list[float]:
        """Get all scores"""
        return [p[1] for p in self.ranked_patches]

    def get_pass_rate(self) -> float:
        """Get hard filter pass rate"""
        if self.total_candidates == 0:
            return 0.0
        return self.valid_candidates / self.total_candidates
