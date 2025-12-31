"""
RepairRanker - Patch Ranking Engine

RFC-SEM-001 Section 2.2: Repair Ranking System

Architecture:
- Domain Layer (Business logic)
- Extends CriticModel (80% reuse)
- IScorerPort strategy pattern

SOTA Principle:
- Liskov Substitution (CriticModel → RepairRanker)
- Open-Closed (new scorers without modification)
- Integration-First (real components)
"""

from typing import TYPE_CHECKING

from apps.orchestrator.orchestrator.shared.reasoning.critic.critic_model import CriticModel
from codegraph_analysis.verification.repair_ranking.domain import PatchCandidate, ScoreResult
from codegraph_shared.infra.observability import get_logger

if TYPE_CHECKING:
    from codegraph_analysis.verification.repair_ranking.domain.models import RankingResult
    from codegraph_analysis.verification.repair_ranking.domain.ports import IScorerPort

logger = get_logger(__name__)


class RepairRanker(CriticModel):
    """
    Repair ranking engine (CriticModel 확장)

    RFC-SEM-000 Section 6.2: Repair Ranking System

    Features:
    - N-Sample patch evaluation
    - Multi-criteria scoring (taint, complexity, style)
    - Hard filter (compile, test)
    - Soft scoring (weighted average)
    - Top-1 selection (canonical patch)

    Design:
    - Extends CriticModel (80% reuse!)
    - Adds repair-specific scorers
    - Maintains CriticModel interface (LSP)

    Usage:
        ranker = RepairRanker(
            taint_scorer=TaintRegressionScorer(),
            complexity_scorer=ComplexityScorer(),
            style_scorer=StyleScorer(),
        )

        patches = [PatchCandidate(...), ...]
        result = ranker.rank_patches(patches)

        best = result.canonical_patch
    """

    def __init__(
        self,
        taint_scorer: "IScorerPort" = None,
        complexity_scorer: "IScorerPort" = None,
        style_scorer: "IScorerPort" = None,
        **kwargs,  # CriticModel args
    ):
        """
        Initialize ranker

        Args:
            taint_scorer: Taint regression scorer
            complexity_scorer: Complexity scorer
            style_scorer: Style scorer
            **kwargs: CriticModel args (config, etc.)

        Design:
        - Lazy initialization for scorers
        - Dependency injection (testable)
        """
        super().__init__(**kwargs)  # CriticModel 초기화

        # Repair-specific scorers
        self._taint_scorer = taint_scorer
        self._complexity_scorer = complexity_scorer
        self._style_scorer = style_scorer

    @property
    def taint_scorer(self) -> "IScorerPort":
        """Lazy-initialized taint scorer"""
        if self._taint_scorer is None:
            from codegraph_analysis.verification.repair_ranking.infrastructure.scorers import (
                TaintRegressionScorer,
            )

            self._taint_scorer = TaintRegressionScorer()
        return self._taint_scorer

    @property
    def complexity_scorer(self) -> "IScorerPort":
        """Lazy-initialized complexity scorer"""
        if self._complexity_scorer is None:
            from codegraph_analysis.verification.repair_ranking.infrastructure.scorers import (
                ComplexityScorer,
            )

            self._complexity_scorer = ComplexityScorer()
        return self._complexity_scorer

    @property
    def style_scorer(self) -> "IScorerPort":
        """Lazy-initialized style scorer"""
        if self._style_scorer is None:
            from codegraph_analysis.verification.repair_ranking.infrastructure.scorers import (
                StyleScorer,
            )

            self._style_scorer = StyleScorer()
        return self._style_scorer

    def rank_patches(self, patches: list[PatchCandidate]) -> "RankingResult":
        """
        Rank patch candidates

        Args:
            patches: List of patch candidates

        Returns:
            RankingResult with ranked patches

        Algorithm:
        1. Hard Filter (compile, test)
        2. Soft Scoring (taint, complexity, style)
        3. Weighted average (CriticModel + repair scorers)
        4. Sort & rank
        5. Top-1 selection

        Performance: < 100ms per patch

        Example:
            >>> ranker = RepairRanker()
            >>> patches = [PatchCandidate(...), ...]
            >>> result = ranker.rank_patches(patches)
            >>> best = result.canonical_patch
            >>> print(f"Best: {best.patch_id}, score: {result.scores[0]}")
        """
        from .models import RankingResult

        logger.info("repair_ranking_started", patches=len(patches))

        if not patches:
            logger.warning("repair_ranking_empty")
            return RankingResult(
                ranked_patches=[],
                canonical_patch=None,
                total_candidates=0,
                valid_candidates=0,
            )

        # 1. Hard Filter (compile, test)
        valid_patches = self._hard_filter(patches)

        logger.info("hard_filter_complete", valid=len(valid_patches), filtered=len(patches) - len(valid_patches))

        if not valid_patches:
            logger.warning("repair_ranking_all_filtered")
            return RankingResult(
                ranked_patches=[],
                canonical_patch=None,
                total_candidates=len(patches),
                valid_candidates=0,
            )

        # 2. Soft Scoring
        scored_patches = []
        for patch in valid_patches:
            # Base score (CriticModel 재사용)
            base_result = super().evaluate(patch)
            base_score = base_result.feedback.overall_score

            # Repair scorers (신규)
            taint_result = self.taint_scorer.score(patch)
            complexity_result = self.complexity_scorer.score(patch)
            style_result = self.style_scorer.score(patch)

            # Weighted average (RFC-SEM-000 Section 6.2)
            final_score = (
                base_score * 0.4
                + taint_result.score * self.taint_scorer.get_weight()  # CriticModel (기존)
                + complexity_result.score * self.complexity_scorer.get_weight()  # 0.3
                + style_result.score * self.style_scorer.get_weight()  # 0.2  # 0.1
            )

            scored_patches.append(
                (
                    patch,
                    final_score,
                    {
                        "base": base_score,
                        "taint": taint_result,
                        "complexity": complexity_result,
                        "style": style_result,
                    },
                )
            )

            logger.debug(
                "patch_scored",
                patch_id=patch.patch_id,
                final_score=f"{final_score:.3f}",
                taint=f"{taint_result.score:.3f}",
                complexity=f"{complexity_result.score:.3f}",
                style=f"{style_result.score:.3f}",
            )

        # 3. Sort (highest first)
        scored_patches.sort(key=lambda x: x[1], reverse=True)

        # 4. Top-1 (canonical)
        canonical = scored_patches[0][0] if scored_patches else None

        logger.info(
            "repair_ranking_complete",
            total=len(patches),
            valid=len(valid_patches),
            best_score=f"{scored_patches[0][1]:.3f}" if scored_patches else "N/A",
        )

        return RankingResult(
            ranked_patches=scored_patches,
            canonical_patch=canonical,
            total_candidates=len(patches),
            valid_candidates=len(valid_patches),
        )

    def _hard_filter(self, patches: list[PatchCandidate]) -> list[PatchCandidate]:
        """
        Hard filter (compile, test)

        Args:
            patches: Patch candidates

        Returns:
            Valid patches (passed filter)

        Filter criteria:
        - Syntax valid (can parse)
        - No obvious errors

        Note: Full compile/test filter can be added later
        """
        valid = []

        for patch in patches:
            # 1. Syntax check (basic)
            if not self._is_valid_syntax(patch.patched_code):
                logger.debug("hard_filter_rejected_syntax", patch_id=patch.patch_id)
                continue

            # 2. Not empty
            if not patch.patched_code.strip():
                logger.debug("hard_filter_rejected_empty", patch_id=patch.patch_id)
                continue

            # 3. Passed
            valid.append(patch)

        return valid

    def _is_valid_syntax(self, code: str) -> bool:
        """
        Check syntax validity

        Args:
            code: Source code

        Returns:
            True if valid syntax
        """
        import ast

        try:
            ast.parse(code)
            return True
        except SyntaxError:
            return False
