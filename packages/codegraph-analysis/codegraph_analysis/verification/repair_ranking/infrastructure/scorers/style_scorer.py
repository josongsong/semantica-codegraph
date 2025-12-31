"""
StyleScorer - Code Style Similarity

RFC-SEM-001 Section 2.2: Repair Ranking - Soft Scoring

Architecture:
- Infrastructure Layer (Hexagonal)
- IScorerPort 구현
- difflib 사용 (Python standard library)

SOTA Principle:
- Minimal change preferred (surgical fixes)
- No guessing (difflib.SequenceMatcher)
- Fast (< 10ms per patch)
"""

import difflib

from codegraph_analysis.verification.repair_ranking.domain import IScorerPort, PatchCandidate, ScoreResult
from codegraph_shared.infra.observability import get_logger

logger = get_logger(__name__)


class StyleScorer(IScorerPort):
    """
    Style similarity scorer

    Contract:
    - Score = 1.0: Minimal change (best, surgical fix)
    - Score = 0.5: Moderate change
    - Score = 0.0: Complete rewrite (worst)

    Algorithm:
    1. Normalize whitespace
    2. SequenceMatcher similarity
    3. Penalize large diffs

    SOTA:
    - Prefers minimal diffs (surgical fixes)
    - Handles whitespace properly
    """

    def __init__(self, min_similarity: float = 0.3):
        """
        Initialize scorer

        Args:
            min_similarity: Minimum acceptable similarity (default: 0.3)
        """
        self.min_similarity = min_similarity

    def score(self, patch: PatchCandidate) -> ScoreResult:
        """
        Score patch by style similarity

        Args:
            patch: Patch candidate

        Returns:
            ScoreResult (1.0 = minimal change, 0.0 = rewrite)
        """
        logger.debug("style_scoring", patch_id=patch.patch_id)

        # 1. Normalize (whitespace-agnostic)
        before_normalized = self._normalize(patch.original_code)
        after_normalized = self._normalize(patch.patched_code)

        # 2. Similarity (difflib)
        similarity = difflib.SequenceMatcher(None, before_normalized, after_normalized).ratio()

        # 3. Score
        score = similarity

        # 4. Reasoning
        if similarity > 0.9:
            reasoning = f"Minimal change (similarity: {similarity:.2%})"
        elif similarity > 0.7:
            reasoning = f"Moderate change (similarity: {similarity:.2%})"
        elif similarity > self.min_similarity:
            reasoning = f"Significant change (similarity: {similarity:.2%})"
        else:
            reasoning = f"Complete rewrite (similarity: {similarity:.2%})"

        # 5. Diff size
        diff_size = self._calculate_diff_size(patch.original_code, patch.patched_code)

        return ScoreResult(
            score=score,
            reasoning=reasoning,
            details={
                "similarity": similarity,
                "diff_size": diff_size,
                "is_minimal": similarity > 0.9,
            },
        )

    def _normalize(self, code: str) -> str:
        """
        Normalize code (whitespace-agnostic)

        Args:
            code: Source code

        Returns:
            Normalized code

        Normalization:
        - Remove leading/trailing whitespace per line
        - Collapse multiple spaces
        - Remove blank lines
        """
        lines = code.split("\n")

        normalized_lines = []
        for line in lines:
            # Strip
            stripped = line.strip()

            # Skip blank
            if not stripped:
                continue

            # Collapse spaces
            collapsed = " ".join(stripped.split())

            normalized_lines.append(collapsed)

        return "\n".join(normalized_lines)

    def _calculate_diff_size(self, before: str, after: str) -> int:
        """
        Calculate diff size (line count)

        Args:
            before: Before code
            after: After code

        Returns:
            Number of changed lines
        """
        before_lines = before.split("\n")
        after_lines = after.split("\n")

        # Unified diff
        diff = difflib.unified_diff(before_lines, after_lines, lineterm="")

        # Count changed lines (+ and -)
        changed = sum(1 for line in diff if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))

        return changed

    def get_name(self) -> str:
        """Scorer name"""
        return "style"

    def get_weight(self) -> float:
        """Default weight (10% of total)"""
        return 0.1
