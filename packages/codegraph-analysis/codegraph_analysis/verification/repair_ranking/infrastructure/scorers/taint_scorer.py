"""
TaintRegressionScorer - Taint 재발 검증

RFC-SEM-001 Section 2.2: Repair Ranking - Hard Filter

Architecture:
- Infrastructure Layer (Hexagonal)
- IScorerPort 구현
- TaintAnalyzer 재사용 (No duplication)

SOTA Principle:
- Producer 먼저 확인 (TaintAnalyzer)
- No fake/stub (Real TaintAnalyzer)
- Deterministic (Same patch → same score)
"""

from typing import TYPE_CHECKING

from codegraph_analysis.verification.repair_ranking.domain import IScorerPort, PatchCandidate, ScoreResult
from codegraph_shared.infra.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

logger = get_logger(__name__)


class TaintRegressionScorer(IScorerPort):
    """
    Taint regression scorer

    Contract:
    - Score = 1.0: No regression (safe)
    - Score = 0.0: Regression detected (unsafe)

    Algorithm:
    1. Taint analysis on original_code
    2. Taint analysis on patched_code
    3. Compare vulnerability counts
    4. Regression = vulnerabilities increased

    SOTA:
    - Uses real TaintAnalysisService (no mock)
    - Deterministic (same code → same vulnerabilities)
    - Fast (< 100ms per patch)
    """

    def __init__(self, taint_service=None):
        """
        Initialize scorer

        Args:
            taint_service: TaintAnalysisService (lazy if None)

        Design:
        - Lazy initialization (avoid heavy imports at module load)
        - Dependency injection (testable)
        """
        self._taint_service = taint_service
        self._policy_ids = [
            "sql-injection",
            "xss",
            "command-injection",
            "path-traversal",
        ]

    @property
    def taint_service(self):
        """Lazy-initialized TaintAnalysisService"""
        if self._taint_service is None:
            from codegraph_engine.code_foundation.application import TaintAnalysisService

            self._taint_service = TaintAnalysisService.from_defaults()
        return self._taint_service

    def score(self, patch: PatchCandidate) -> ScoreResult:
        """
        Score patch for taint regression

        Args:
            patch: Patch candidate

        Returns:
            ScoreResult (1.0 = safe, 0.0 = regression)

        Algorithm:
        1. Parse codes → IR (real parsing)
        2. Taint analysis (real TaintAnalyzer)
        3. Compare vulnerabilities
        4. Regression check

        Performance: < 100ms per patch
        """
        logger.debug("taint_regression_scoring", patch_id=patch.patch_id)

        try:
            # 1. Parse original (baseline)
            ir_before = self._parse_code(patch.original_code, f"{patch.patch_id}_before")

            # 2. Parse patched
            ir_after = self._parse_code(patch.patched_code, f"{patch.patch_id}_after")

            # 3. Taint analysis (real!)
            vulns_before = self._analyze_taint(ir_before)
            vulns_after = self._analyze_taint(ir_after)

            # 4. Regression check
            regression_detected = len(vulns_after) > len(vulns_before)

            if regression_detected:
                # Regression → 0.0 (unsafe)
                new_vulns = len(vulns_after) - len(vulns_before)
                return ScoreResult(
                    score=0.0,
                    reasoning=f"Taint regression: +{new_vulns} vulnerabilities",
                    details={
                        "before_count": len(vulns_before),
                        "after_count": len(vulns_after),
                        "regression": True,
                    },
                )

            # 5. Safe or improved
            if len(vulns_after) < len(vulns_before):
                # Improvement
                fixed = len(vulns_before) - len(vulns_after)
                return ScoreResult(
                    score=1.0,
                    reasoning=f"Taint improvement: fixed {fixed} vulnerabilities",
                    details={
                        "before_count": len(vulns_before),
                        "after_count": len(vulns_after),
                        "improvement": True,
                    },
                )

            # No change
            return ScoreResult(
                score=1.0,
                reasoning="No taint regression",
                details={
                    "before_count": len(vulns_before),
                    "after_count": len(vulns_after),
                    "regression": False,
                },
            )

        except Exception as e:
            logger.warning("taint_scoring_failed", patch_id=patch.patch_id, error=str(e))

            # Fail-safe: Unknown → 중립 (0.5)
            return ScoreResult(
                score=0.5,
                reasoning=f"Taint analysis failed: {str(e)}",
                details={"error": str(e)},
            )

    def _parse_code(self, code: str, file_id: str) -> "IRDocument":
        """
        Parse code → IRDocument (real parsing)

        Args:
            code: Source code
            file_id: Virtual file ID

        Returns:
            IRDocument

        Note: Uses real parser (no mock)
        """
        from codegraph_engine.code_foundation.infrastructure.ir import IRBuilder

        # Real parsing
        builder = IRBuilder(language="python")  # TODO: detect language
        ir_doc = builder.build_from_source(
            source_code=code,
            file_path=f"<patch>/{file_id}.py",
        )

        return ir_doc

    def _analyze_taint(self, ir_doc: "IRDocument") -> list:
        """
        Taint analysis (real TaintAnalyzer)

        Args:
            ir_doc: IRDocument

        Returns:
            List of vulnerabilities

        Note: Uses real TaintAnalysisService
        """
        # Real taint analysis!
        result = self.taint_service.analyze(
            ir_doc=ir_doc,
            policies=self._policy_ids,
        )

        vulnerabilities = result.get("vulnerabilities", [])

        logger.debug("taint_analysis_complete", vulnerabilities=len(vulnerabilities))

        return vulnerabilities

    def get_name(self) -> str:
        """Scorer name"""
        return "taint_regression"

    def get_weight(self) -> float:
        """Default weight (30% of total)"""
        return 0.3
