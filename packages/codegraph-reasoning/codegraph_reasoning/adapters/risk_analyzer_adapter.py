"""
Risk Analyzer Adapter

RiskAnalyzer를 RiskAnalyzerPort로 래핑
"""

from typing import Any

from ..domain.speculative_models import RiskReport, SpeculativePatch
from ..infrastructure.speculative.delta_graph import DeltaGraph
from ..infrastructure.speculative.risk_analyzer import RiskAnalyzer


class RiskAnalyzerAdapter:
    """
    RiskAnalyzer Adapter

    Infrastructure → Port 브릿지
    """

    def __init__(self, semantic_differ: Any | None = None):
        """
        Initialize adapter

        Args:
            semantic_differ: Optional semantic diff engine
        """
        self._analyzer = RiskAnalyzer(semantic_differ)

    def analyze_risk(
        self,
        patch: SpeculativePatch,
        delta_graph: DeltaGraph,
        base_graph: Any,
    ) -> RiskReport:
        """위험도 분석 (Port 메서드)"""
        return self._analyzer.analyze_risk(patch, delta_graph, base_graph)


# Type check
def _type_check() -> None:
    """Static type check (not executed at runtime)"""
    RiskAnalyzerAdapter()
