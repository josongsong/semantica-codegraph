"""
Repair Ranking Service (Application Layer)

RFC-SEM-001 Section 2: Repair Ranking System

Main entry point for patch ranking.

Architecture: Hexagonal (Application Layer)
"""

from typing import TYPE_CHECKING

from codegraph_analysis.verification.repair_ranking.domain import PatchCandidate
from codegraph_analysis.verification.repair_ranking.domain.repair_ranker import RepairRanker
from codegraph_shared.infra.observability import get_logger

if TYPE_CHECKING:
    from codegraph_analysis.verification.repair_ranking.domain.models import RankingResult

logger = get_logger(__name__)


class RepairRankingService:
    """
    Repair ranking service

    Usage:
        service = RepairRankingService()

        patches = [PatchCandidate(...), ...]
        result = service.rank_patches(patches)

        best = result.canonical_patch
    """

    def __init__(self, ranker: RepairRanker | None = None):
        """
        Initialize service

        Args:
            ranker: RepairRanker (lazy if None)
        """
        self._ranker = ranker

    @property
    def ranker(self) -> RepairRanker:
        """Lazy-initialized ranker"""
        if self._ranker is None:
            self._ranker = RepairRanker()
        return self._ranker

    def rank_patches(self, patches: list[PatchCandidate]) -> "RankingResult":
        """
        Rank patches

        Args:
            patches: Patch candidates

        Returns:
            RankingResult with ranked patches
        """
        logger.info("repair_ranking_service_started", patches=len(patches))

        result = self.ranker.rank_patches(patches)

        logger.info(
            "repair_ranking_service_complete",
            total=result.total_candidates,
            valid=result.valid_candidates,
            best=result.canonical_patch.patch_id if result.canonical_patch else None,
        )

        return result
