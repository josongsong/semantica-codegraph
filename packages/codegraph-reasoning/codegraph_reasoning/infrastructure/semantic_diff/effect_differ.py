"""
EffectDiffer - 변경 전후 Effect 비교

코드 변화가 Breaking인지 판단
"""

import logging

from ...domain.effect_models import EffectDiff, EffectSet
from .effect_analyzer import EffectAnalyzer

logger = logging.getLogger(__name__)


class EffectDiffer:
    """
    변경 전후 Effect 비교

    Example:
        differ = EffectDiffer()
        diff = differ.compare(before_code, after_code, "func1")

        if diff.is_breaking:
            print(f"Breaking change: {diff.summary()}")
    """

    def __init__(self, analyzer: EffectAnalyzer | None = None):
        """
        Initialize EffectDiffer

        Args:
            analyzer: EffectAnalyzer (optional, creates new if None)
        """
        self.analyzer = analyzer or EffectAnalyzer()
        logger.info("EffectDiffer initialized")

    def compare(self, before_code: str, after_code: str, symbol_id: str) -> EffectDiff:
        """
        코드 변경 전후 비교

        Args:
            before_code: 변경 전 코드
            after_code: 변경 후 코드
            symbol_id: Symbol identifier

        Returns:
            EffectDiff
        """
        # Analyze before/after
        before_effect = self.analyzer.analyze_code(before_code, symbol_id)
        after_effect = self.analyzer.analyze_code(after_code, symbol_id)

        # Create diff
        diff = EffectDiff(symbol_id=symbol_id, before=before_effect.effects, after=after_effect.effects)

        logger.info(f"Effect diff for {symbol_id}: {diff.severity}, breaking={diff.is_breaking}")

        return diff

    def compare_effect_sets(self, before: EffectSet, after: EffectSet) -> EffectDiff:
        """
        EffectSet 직접 비교

        Args:
            before: Before EffectSet
            after: After EffectSet

        Returns:
            EffectDiff
        """
        return EffectDiff(symbol_id=before.symbol_id, before=before.effects, after=after.effects)

    def batch_compare(self, changes: dict[str, tuple[str, str]]) -> list[EffectDiff]:
        """
        여러 함수 동시 비교

        Args:
            changes: {symbol_id: (before_code, after_code)}

        Returns:
            List of EffectDiff
        """
        diffs = []

        for symbol_id, (before_code, after_code) in changes.items():
            try:
                diff = self.compare(before_code, after_code, symbol_id)
                diffs.append(diff)
            except (SyntaxError, ValueError, TypeError) as e:
                logger.error(f"Failed to compare {symbol_id}: {e}")

        logger.info(f"Batch compared {len(diffs)}/{len(changes)} symbols")
        return diffs

    def get_breaking_changes(self, diffs: list[EffectDiff]) -> list[EffectDiff]:
        """
        Breaking changes만 추출

        Args:
            diffs: List of EffectDiff

        Returns:
            Breaking changes only
        """
        breaking = [d for d in diffs if d.is_breaking]
        logger.info(f"Found {len(breaking)}/{len(diffs)} breaking changes")
        return breaking

    def summarize(self, diffs: list[EffectDiff]) -> dict[str, int]:
        """
        Diffs 요약

        Returns:
            {severity: count}
        """
        summary = {
            "none": 0,
            "low": 0,
            "medium": 0,
            "high": 0,
            "critical": 0,
        }

        for diff in diffs:
            summary[diff.severity] += 1

        return summary
