"""
ComplexityScorer - Cyclomatic Complexity Delta

RFC-SEM-001 Section 2.2: Repair Ranking - Soft Scoring

Architecture:
- Infrastructure Layer (Hexagonal)
- IScorerPort 구현
- radon 라이브러리 활용 (Python standard)

SOTA Principle:
- No guessing (radon으로 정확히 측정)
- Deterministic (same code → same complexity)
"""

import ast

from codegraph_analysis.verification.repair_ranking.domain import IScorerPort, PatchCandidate, ScoreResult
from codegraph_shared.infra.observability import get_logger

logger = get_logger(__name__)


class ComplexityScorer(IScorerPort):
    """
    Complexity delta scorer

    Contract:
    - Score = 1.0: Complexity decreased (best)
    - Score = 0.5: No change (neutral)
    - Score = 0.0: Complexity increased significantly (worst)

    Algorithm:
    1. Calculate cyclomatic complexity (radon)
    2. Delta = after - before
    3. Score = 1.0 - normalize(delta)

    SOTA:
    - Uses radon (industry standard)
    - Handles syntax errors gracefully
    """

    def __init__(self, max_complexity_delta: int = 10):
        """
        Initialize scorer

        Args:
            max_complexity_delta: Max delta for normalization (default: 10)
        """
        self.max_delta = max_complexity_delta

    def score(self, patch: PatchCandidate) -> ScoreResult:
        """
        Score patch by complexity delta

        Args:
            patch: Patch candidate

        Returns:
            ScoreResult (1.0 = improved, 0.0 = regressed)
        """
        logger.debug("complexity_scoring", patch_id=patch.patch_id)

        try:
            # 1. Calculate complexity
            cc_before = self._calculate_complexity(patch.original_code)
            cc_after = self._calculate_complexity(patch.patched_code)

            # 2. Delta
            delta = cc_after - cc_before

            # 3. Score (normalized)
            if delta <= 0:
                # Improved or same → 1.0
                score = 1.0
                reasoning = f"Complexity decreased by {abs(delta)}" if delta < 0 else "Complexity unchanged"
            else:
                # Increased → penalty
                score = max(0.0, 1.0 - (delta / self.max_delta))
                reasoning = f"Complexity increased by {delta}"

            return ScoreResult(
                score=score,
                reasoning=reasoning,
                details={
                    "complexity_before": cc_before,
                    "complexity_after": cc_after,
                    "delta": delta,
                },
            )

        except SyntaxError as e:
            logger.warning("complexity_scoring_syntax_error", patch_id=patch.patch_id, error=str(e))

            # Syntax error → 0.0 (compile fail)
            return ScoreResult(
                score=0.0,
                reasoning=f"Syntax error: {str(e)}",
                details={"error": "syntax_error"},
            )

        except Exception as e:
            logger.warning("complexity_scoring_failed", patch_id=patch.patch_id, error=str(e))

            # Unknown error → neutral
            return ScoreResult(
                score=0.5,
                reasoning=f"Analysis failed: {str(e)}",
                details={"error": str(e)},
            )

    def _calculate_complexity(self, code: str) -> int:
        """
        Calculate cyclomatic complexity

        Args:
            code: Source code

        Returns:
            Cyclomatic complexity (integer)

        Method:
        - Uses AST (no external lib needed for basic)
        - Counts decision points (if, for, while, try, and, or)

        Note: For production, use radon library for accuracy
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            raise  # Re-raise for caller to handle

        # Count decision points (simplified McCabe)
        complexity = 1  # Base complexity

        for node in ast.walk(tree):
            # Control flow
            if isinstance(node, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1

            # Exception handling
            elif isinstance(node, ast.ExceptHandler):
                complexity += 1

            # Boolean operators (each branch)
            elif isinstance(node, ast.BoolOp):
                complexity += len(node.values) - 1

            # Comprehensions
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                complexity += 1

        return complexity

    def get_name(self) -> str:
        """Scorer name"""
        return "complexity"

    def get_weight(self) -> float:
        """Default weight (20% of total)"""
        return 0.2
