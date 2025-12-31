"""
Impact Analyzer Adapter

Infrastructure ImpactAnalyzer를 Port로 래핑
"""

from typing import Any

from ..domain.effect_models import EffectDiff
from ..domain.impact_models import ImpactReport
from ..infrastructure.impact.impact_analyzer import ImpactAnalyzer


class ImpactAnalyzerAdapter:
    """
    ImpactAnalyzer Adapter

    Infrastructure → Port 브릿지
    """

    def __init__(self, graph: Any, max_depth: int = 3, min_confidence: float = 0.5):
        """
        Initialize adapter

        Args:
            graph: GraphDocument
            max_depth: Maximum propagation depth
            min_confidence: Minimum confidence threshold
        """
        self._analyzer = ImpactAnalyzer(
            graph=graph,
            max_depth=max_depth,
            min_confidence=min_confidence,
        )

    def analyze_impact(
        self,
        symbol_id: str,
        effect_diff: EffectDiff | None = None,
    ) -> ImpactReport:
        """Impact 분석 (Port 메서드)"""
        return self._analyzer.analyze_impact(symbol_id, effect_diff)

    def batch_analyze(
        self,
        symbol_ids: list[str],
        effect_diffs: dict[str, EffectDiff] | None = None,
    ) -> dict[str, ImpactReport]:
        """Batch impact 분석 (Port 메서드)"""
        return self._analyzer.batch_analyze(symbol_ids, effect_diffs)
