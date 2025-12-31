"""
Speculative Execution Executor

패치 시뮬레이션 전담
"""

import logging
from dataclasses import dataclass
from typing import Any

from ...domain.speculative_models import RiskLevel, RiskReport, SpeculativePatch

logger = logging.getLogger(__name__)


# 매직 숫자 상수화
RISK_THRESHOLD_BREAKING = 3


@dataclass
class SpeculativeResult:
    """Speculative 실행 결과"""

    patch_id: str
    risk_report: RiskReport
    delta_graph: Any

    def is_safe(self) -> bool:
        """안전하게 적용 가능한지"""
        return self.risk_report.risk_level in [RiskLevel.SAFE, RiskLevel.LOW]


class SpeculativeExecutor:
    """
    Speculative 실행 전담 실행자

    책임: 패치 시뮬레이션 및 위험도 분석
    입력: SpeculativePatch, base_graph
    출력: SpeculativeResult
    """

    def __init__(self, simulator: Any, risk_analyzer: Any):
        """
        Args:
            simulator: SimulatorAdapter (DI)
            risk_analyzer: RiskAnalyzerAdapter (DI)
        """
        self._simulator = simulator
        self._risk_analyzer = risk_analyzer

    def execute(self, patch: SpeculativePatch, base_graph: Any) -> SpeculativeResult:
        """
        Speculative 실행

        Args:
            patch: 적용할 패치
            base_graph: 기본 그래프

        Returns:
            SpeculativeResult
        """
        logger.info(f"Simulating patch: {patch.patch_id}")

        # Simulate patch
        delta_graph = self._simulator.simulate_patch(patch)

        # Analyze risk
        risk_report = self._risk_analyzer.analyze_risk(patch, delta_graph, base_graph)

        result = SpeculativeResult(
            patch_id=patch.patch_id,
            risk_report=risk_report,
            delta_graph=delta_graph,
        )

        logger.info(f"Simulation complete: risk={risk_report.risk_level.value}, safe={result.is_safe()}")
        return result

    def execute_batch(
        self,
        patches: list[SpeculativePatch],
        base_graph: Any,
    ) -> list[SpeculativeResult]:
        """
        여러 패치 실행

        Args:
            patches: 패치 목록
            base_graph: 기본 그래프

        Returns:
            List of SpeculativeResult
        """
        results = []
        for patch in patches:
            result = self.execute(patch, base_graph)
            results.append(result)
        return results

    def calculate_total_risk(self, results: list[SpeculativeResult]) -> RiskLevel:
        """전체 위험도 계산"""
        if not results:
            return RiskLevel.SAFE

        max_risk = max(r.risk_report.risk_level for r in results)
        breaking_count = sum(1 for r in results if r.risk_report.is_breaking())

        # 매직 숫자 대신 상수 사용
        if breaking_count >= RISK_THRESHOLD_BREAKING:
            if max_risk == RiskLevel.HIGH:
                return RiskLevel.BREAKING

        return max_risk
