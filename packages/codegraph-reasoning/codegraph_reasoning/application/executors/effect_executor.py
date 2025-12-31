"""
Effect Analysis Executor

Effect 변화 분석 전담
"""

import logging
from dataclasses import dataclass, field

from ...domain.effect_models import EffectDiff
from ...ports import EffectAnalyzerPort

logger = logging.getLogger(__name__)


@dataclass
class EffectAnalysisResult:
    """Effect 분석 결과"""

    diffs: dict[str, EffectDiff] = field(default_factory=dict)
    breaking_count: int = 0
    total_changes: int = 0

    def get_breaking_symbols(self) -> list[str]:
        """Breaking change가 있는 심볼 목록"""
        return [d.symbol_id for d in self.diffs.values() if d.is_breaking]


class EffectAnalysisExecutor:
    """
    Effect 분석 전담 실행자

    책임: 코드 변경의 effect 변화 분석
    입력: {symbol_id: (old_code, new_code)}
    출력: EffectAnalysisResult
    """

    def __init__(self, effect_analyzer: EffectAnalyzerPort):
        """
        Args:
            effect_analyzer: EffectAnalyzerPort (DI)
        """
        self._analyzer = effect_analyzer

    def execute(self, changes: dict[str, tuple[str, str]]) -> EffectAnalysisResult:
        """
        Effect 분석 실행

        Args:
            changes: {symbol_id: (before_code, after_code)}

        Returns:
            EffectAnalysisResult
        """
        logger.info(f"Analyzing effects for {len(changes)} symbols")

        diffs = self._analyzer.batch_compare(changes)

        result = EffectAnalysisResult()
        for diff in diffs:
            result.diffs[diff.symbol_id] = diff

        breaking = [d for d in diffs if d.is_breaking]
        result.breaking_count = len(breaking)
        result.total_changes = len(diffs)

        logger.info(f"Effect analysis complete: {result.breaking_count} breaking changes")
        return result
