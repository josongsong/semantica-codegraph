"""
Impact Analysis Executor

영향 전파 분석 전담
"""

import logging
from dataclasses import dataclass, field

from ...domain.effect_models import EffectDiff
from ...domain.impact_models import ImpactLevel, ImpactReport
from ...ports import ImpactAnalyzerPort

logger = logging.getLogger(__name__)


# 매직 숫자 상수화
IMPACT_THRESHOLD_CRITICAL = 20
IMPACT_THRESHOLD_HIGH = 5
IMPACT_THRESHOLD_MEDIUM = 2


@dataclass
class ImpactAnalysisResult:
    """Impact 분석 결과"""

    reports: dict[str, ImpactReport] = field(default_factory=dict)
    total_impact: ImpactLevel = ImpactLevel.NONE
    impacted_symbols: set[str] = field(default_factory=set)

    def get_critical_symbols(self) -> list[str]:
        """Critical impact 심볼 목록"""
        symbols = []
        for report in self.reports.values():
            for node in report.impacted_nodes:
                if node.impact_level == ImpactLevel.CRITICAL:
                    symbols.append(node.symbol_id)
        return symbols


class ImpactAnalysisExecutor:
    """
    Impact 분석 전담 실행자

    책임: 변경의 영향 전파 분석
    입력: source_ids, effect_diffs
    출력: ImpactAnalysisResult
    """

    def __init__(self, impact_analyzer: ImpactAnalyzerPort):
        """
        Args:
            impact_analyzer: ImpactAnalyzerPort (DI)
        """
        self._analyzer = impact_analyzer

    def execute(
        self,
        source_ids: list[str],
        effect_diffs: dict[str, EffectDiff] | None = None,
    ) -> ImpactAnalysisResult:
        """
        Impact 분석 실행

        Args:
            source_ids: 분석할 source symbol IDs
            effect_diffs: Effect 변화 정보 (optional)

        Returns:
            ImpactAnalysisResult
        """
        logger.info(f"Analyzing impact for {len(source_ids)} sources")

        reports = self._analyzer.batch_analyze(source_ids, effect_diffs)

        result = ImpactAnalysisResult()
        result.reports = reports

        # Collect impacted symbols
        for report in reports.values():
            result.impacted_symbols.update(n.symbol_id for n in report.impacted_nodes)

        # Calculate total impact
        result.total_impact = self._calculate_total_impact(reports)

        logger.info(
            f"Impact analysis complete: {len(result.impacted_symbols)} impacted, total={result.total_impact.value}"
        )
        return result

    def _calculate_total_impact(self, reports: dict[str, ImpactReport]) -> ImpactLevel:
        """전체 impact level 계산"""
        if not reports:
            return ImpactLevel.NONE

        max_impact = max(r.total_impact for r in reports.values())
        total_nodes = sum(len(r.impacted_nodes) for r in reports.values())

        # 매직 숫자 대신 상수 사용
        if total_nodes >= IMPACT_THRESHOLD_CRITICAL:
            return ImpactLevel.CRITICAL

        critical_count = sum(
            1 for r in reports.values() for n in r.impacted_nodes if n.impact_level == ImpactLevel.CRITICAL
        )
        if critical_count > 0:
            return ImpactLevel.CRITICAL

        high_count = sum(1 for r in reports.values() for n in r.impacted_nodes if n.impact_level == ImpactLevel.HIGH)
        if high_count >= IMPACT_THRESHOLD_HIGH:
            return ImpactLevel.CRITICAL
        if high_count >= IMPACT_THRESHOLD_MEDIUM:
            return ImpactLevel.HIGH

        return max_impact
