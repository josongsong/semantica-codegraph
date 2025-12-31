"""
Decide Reasoning Path UseCase

Application Layer - 사용자 시나리오 Orchestration
"""

import logging
from typing import TYPE_CHECKING

from apps.orchestrator.orchestrator.shared.reasoning import QueryFeatures, ReasoningDecision

if TYPE_CHECKING:
    from codegraph_agent.ports.reasoning import IComplexityAnalyzer, IRiskAssessor
    from apps.orchestrator.orchestrator.shared.reasoning import DynamicReasoningRouter

logger = logging.getLogger(__name__)


class DecideReasoningPathUseCase:
    """
    추론 경로 결정 UseCase (Application Layer)

    책임:
    1. Adapter들로부터 메트릭 수집
    2. QueryFeatures 조합
    3. Router (Domain Service)에 전달
    4. 결과 반환

    헥사고날 아키텍처:
    User → UseCase (Application) → Router (Domain) → Ports → Adapters
    """

    def __init__(
        self,
        router: "DynamicReasoningRouter",
        complexity_analyzer: "IComplexityAnalyzer",
        risk_assessor: "IRiskAssessor",
    ):
        """
        Args:
            router: Dynamic Reasoning Router (Domain Service)
            complexity_analyzer: 복잡도 분석 Adapter
            risk_assessor: 위험도 평가 Adapter
        """
        self._router = router
        self._complexity = complexity_analyzer
        self._risk = risk_assessor

    def execute(
        self,
        problem_description: str,
        target_files: list[str],
        code_snippet: str | None = None,
    ) -> ReasoningDecision:
        """
        추론 경로 결정 (UseCase Orchestration)

        Steps:
        1. 복잡도 메트릭 수집 (Adapter)
        2. 위험도 메트릭 수집 (Adapter)
        3. QueryFeatures 조합
        4. Router에 전달
        5. 결과 반환

        Args:
            problem_description: 문제 설명
            target_files: 변경 대상 파일들
            code_snippet: 참조 코드 (Optional)

        Returns:
            ReasoningDecision
        """
        logger.info(f"Deciding reasoning path for: {problem_description[:50]}...")

        # Step 1: 복잡도 메트릭 수집
        complexity_metrics = self._gather_complexity_metrics(target_files, code_snippet)

        # Step 2: 위험도 메트릭 수집
        risk_metrics = self._gather_risk_metrics(problem_description, target_files, code_snippet)

        # Step 3: QueryFeatures 조합 (Application Layer 책임)
        features = QueryFeatures(
            file_count=len(target_files),
            impact_nodes=complexity_metrics["impact_nodes"],
            cyclomatic_complexity=complexity_metrics["cyclomatic"],
            has_test_failure=risk_metrics["has_test_failure"],
            touches_security_sink=risk_metrics["touches_security_sink"],
            regression_risk=risk_metrics["regression_risk"],
            similar_success_rate=0.8,  # TODO: Experience Store v2
            previous_attempts=0,  # TODO: Session tracking
        )

        # Step 4: Domain Service 호출
        decision = self._router.decide(features)

        logger.info(f"Decision: {decision.path.value} (confidence={decision.confidence:.2f})")

        return decision

    def _gather_complexity_metrics(self, target_files: list[str], code_snippet: str | None) -> dict:
        """
        복잡도 메트릭 수집

        Returns:
            {
                "cyclomatic": float,
                "cognitive": float,
                "impact_nodes": int,
            }
        """
        # 코드 스니펫이 있으면 사용, 없으면 첫 파일
        code = code_snippet
        if not code and target_files:
            try:
                from pathlib import Path

                code = Path(target_files[0]).read_text()
            except Exception:
                code = ""

        if not code:
            # 코드 없으면 기본값
            return {
                "cyclomatic": 0.0,
                "cognitive": 0.0,
                "impact_nodes": 0,
            }

        # Adapter 호출
        cyclomatic = self._complexity.analyze_cyclomatic(code)
        cognitive = self._complexity.analyze_cognitive(code)

        # 영향 노드 수 (첫 파일 기준)
        impact_nodes = 0
        if target_files:
            impact_nodes = self._complexity.count_impact_nodes(target_files[0])

        return {
            "cyclomatic": cyclomatic,
            "cognitive": cognitive,
            "impact_nodes": impact_nodes,
        }

    def _gather_risk_metrics(self, problem_description: str, target_files: list[str], code_snippet: str | None) -> dict:
        """
        위험도 메트릭 수집

        Returns:
            {
                "regression_risk": float,
                "has_test_failure": bool,
                "touches_security_sink": bool,
            }
        """
        # Adapter 호출
        regression_risk = self._risk.assess_regression_risk(problem_description, target_files)

        has_test_failure = self._risk.check_test_failure(target_files)

        # 보안 sink (코드 스니펫 필요)
        touches_security_sink = False
        if code_snippet:
            touches_security_sink = self._risk.check_security_sink(code_snippet)

        return {
            "regression_risk": regression_risk,
            "has_test_failure": has_test_failure,
            "touches_security_sink": touches_security_sink,
        }
