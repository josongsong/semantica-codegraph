"""
Self-Reflection Judge (v8.1)

SOTA: Graph Stability + Execution Trace Analysis
"""

import logging

from .reflection_models import (
    ReflectionInput,
    ReflectionOutput,
    ReflectionRules,
    ReflectionVerdict,
    StabilityLevel,
)

logger = logging.getLogger(__name__)


class SelfReflectionJudge:
    """
    Self-Reflection Judge (Domain Service)

    책임:
    - Graph Impact 분석
    - Execution Trace 검증
    - Accept/Revise/Rollback 판정

    SOTA 기법:
    - Multi-Criteria Decision Making
    - Graph Stability Analysis (CFG/DFG/PDG)
    - Regression Detection
    """

    def __init__(self, weights: dict[str, float] | None = None):
        """
        Args:
            weights: 커스텀 가중치 (Optional)
        """
        self.weights = weights or ReflectionRules.get_weights()

        # 가중치 검증
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total}")

        logger.info(f"Self-Reflection Judge initialized with weights: {self.weights}")

    def judge(self, input: ReflectionInput) -> ReflectionOutput:
        """
        판정 (핵심 비즈니스 로직)

        Decision Flow:
        1. Critical Issues Check (즉시 거부)
        2. Graph Stability Analysis
        3. Execution Trace Validation
        4. Multi-Criteria Scoring
        5. Verdict 결정

        Args:
            input: ReflectionInput

        Returns:
            ReflectionOutput
        """
        logger.info(f"Judging strategy: {input.strategy_id}")

        # Step 1: Critical Issues (Fast Fail)
        critical_issues = self._check_critical_issues(input)
        if critical_issues:
            return self._create_rollback_output(input, critical_issues, "Critical issues detected - immediate rollback")

        # Step 2: Graph Stability
        input.graph_impact.impact_score = input.graph_impact.calculate_impact_score()
        input.graph_impact.stability_level = input.graph_impact.determine_stability()

        if input.graph_impact.stability_level == StabilityLevel.CRITICAL:
            return self._create_rollback_output(
                input, ["Graph stability critical"], "Massive graph changes - rollback recommended"
            )

        # Step 3: Execution Trace
        if input.execution_trace.has_regressions():
            return self._create_revise_output(
                input, ["Regressions detected in execution trace"], "Performance or coverage degraded"
            )

        # Step 4: Multi-Criteria Scoring
        score = self._calculate_confidence_score(input)

        # Step 5: Verdict
        verdict = self._determine_verdict(input, score)

        # Build Output
        return self._create_output(input, verdict, score)

    # ========================================================================
    # Critical Checks
    # ========================================================================

    def _check_critical_issues(self, input: ReflectionInput) -> list[str]:
        """
        치명적 이슈 확인

        Returns:
            List of critical issues (empty if none)
        """
        issues = []

        # Execution Failure
        if not input.execution_success:
            issues.append("Execution failed")

        # Test Pass Rate Too Low
        if input.test_pass_rate < ReflectionRules.MIN_TEST_PASS_RATE:
            issues.append(f"Test pass rate {input.test_pass_rate:.0%} < {ReflectionRules.MIN_TEST_PASS_RATE:.0%}")

        # New Exceptions
        if len(input.execution_trace.new_exceptions) > 0:
            issues.append(f"New exceptions: {', '.join(input.execution_trace.new_exceptions[:3])}")

        return issues

    # ========================================================================
    # Scoring
    # ========================================================================

    def _calculate_confidence_score(self, input: ReflectionInput) -> float:
        """
        신뢰도 점수 계산 (Multi-Criteria)

        Returns:
            0.0 ~ 1.0
        """
        # 1. Execution Score
        exec_score = input.test_pass_rate  # 0.0 ~ 1.0

        # 2. Graph Score (낮은 impact = 높은 점수)
        graph_score = 1.0 - input.graph_impact.impact_score

        # 3. Trace Score
        trace_score = self._score_execution_trace(input.execution_trace)

        # 4. Historical Score
        historical_score = self._score_historical(input)

        # Weighted Sum
        total_score = (
            exec_score * self.weights["execution"]
            + graph_score * self.weights["graph"]
            + trace_score * self.weights["trace"]
            + historical_score * self.weights["historical"]
        )

        logger.debug(
            f"Confidence: exec={exec_score:.2f}, graph={graph_score:.2f}, "
            f"trace={trace_score:.2f}, hist={historical_score:.2f} "
            f"→ total={total_score:.2f}"
        )

        return min(total_score, 1.0)

    def _score_execution_trace(self, trace) -> float:
        """실행 추적 점수"""
        score = 1.0

        # Coverage 증가는 보너스
        coverage_delta = trace.coverage_after - trace.coverage_before
        if coverage_delta > 0:
            score += min(coverage_delta, 0.1)  # max +0.1
        elif coverage_delta < -0.05:
            score -= 0.2  # 5% 이상 감소는 페널티

        # Performance 개선은 보너스
        if trace.execution_time_delta < 0:  # 빨라짐
            score += 0.05
        elif trace.execution_time_delta > 1.0:  # 1초 이상 느려짐
            score -= 0.1

        # Exception 수정은 보너스
        if len(trace.fixed_exceptions) > 0:
            score += min(len(trace.fixed_exceptions) * 0.05, 0.15)

        return max(min(score, 1.0), 0.0)

    def _score_historical(self, input: ReflectionInput) -> float:
        """과거 성공률 점수"""
        # 유사 실패가 많으면 낮은 점수
        if input.similar_failures_count > 5:
            return 0.3
        elif input.similar_failures_count > 2:
            return 0.6
        else:
            return 0.9

    # ========================================================================
    # Verdict Decision
    # ========================================================================

    def _determine_verdict(self, input: ReflectionInput, score: float) -> ReflectionVerdict:
        """
        Verdict 결정 (Business Rule)

        Logic:
        - score >= 0.8 AND stable → ACCEPT
        - score >= 0.6 AND moderate → REVISE
        - score < 0.6 OR unstable → RETRY
        - critical → ROLLBACK
        """
        stability = input.graph_impact.stability_level

        # High Confidence + Stable → Accept
        if score >= 0.8 and stability == StabilityLevel.STABLE:
            return ReflectionVerdict.ACCEPT

        # Medium Confidence + Moderate → Revise
        if score >= 0.6 and stability in (StabilityLevel.STABLE, StabilityLevel.MODERATE):
            return ReflectionVerdict.REVISE

        # Unstable → Retry
        if stability == StabilityLevel.UNSTABLE:
            return ReflectionVerdict.RETRY

        # Low Confidence → Retry
        if score < 0.5:
            return ReflectionVerdict.RETRY

        # Default: Revise
        return ReflectionVerdict.REVISE

    # ========================================================================
    # Output Builders
    # ========================================================================

    def _create_output(self, input: ReflectionInput, verdict: ReflectionVerdict, score: float) -> ReflectionOutput:
        """일반 Output 생성"""

        # Warnings
        warnings = []
        if input.graph_impact.stability_level == StabilityLevel.MODERATE:
            warnings.append("Moderate graph changes - review carefully")

        if input.execution_trace.execution_time_delta > 0.5:
            warnings.append(f"Performance degradation: +{input.execution_trace.execution_time_delta:.1f}s")

        # Suggestions
        suggestions = self._generate_suggestions(input, verdict)

        # Reasoning
        reasoning = self._generate_reasoning(input, verdict, score)

        return ReflectionOutput(
            verdict=verdict,
            confidence=score,
            reasoning=reasoning,
            graph_stability=input.graph_impact.stability_level,
            impact_score=input.graph_impact.impact_score,
            warnings=warnings,
            suggested_fixes=suggestions,
        )

    def _create_rollback_output(self, input: ReflectionInput, issues: list[str], reasoning: str) -> ReflectionOutput:
        """Rollback Output"""
        return ReflectionOutput(
            verdict=ReflectionVerdict.ROLLBACK,
            confidence=0.0,
            reasoning=reasoning,
            graph_stability=input.graph_impact.stability_level,
            impact_score=input.graph_impact.impact_score,
            critical_issues=issues,
            suggested_fixes=["Rollback to previous version", "Investigate root cause"],
        )

    def _create_revise_output(self, input: ReflectionInput, warnings: list[str], reasoning: str) -> ReflectionOutput:
        """Revise Output"""
        score = self._calculate_confidence_score(input)

        return ReflectionOutput(
            verdict=ReflectionVerdict.REVISE,
            confidence=score,
            reasoning=reasoning,
            graph_stability=input.graph_impact.stability_level,
            impact_score=input.graph_impact.impact_score,
            warnings=warnings,
            suggested_fixes=self._generate_suggestions(input, ReflectionVerdict.REVISE),
        )

    # ========================================================================
    # Helpers
    # ========================================================================

    def _generate_suggestions(self, input: ReflectionInput, verdict: ReflectionVerdict) -> list[str]:
        """제안 생성"""
        suggestions = []

        if verdict == ReflectionVerdict.REVISE:
            if input.test_pass_rate < 0.9:
                suggestions.append("Add more test coverage")

            if input.graph_impact.impact_score > 0.4:
                suggestions.append("Reduce graph impact - smaller changes")

            if len(input.execution_trace.new_exceptions) > 0:
                suggestions.append("Fix new exceptions before proceeding")

        elif verdict == ReflectionVerdict.RETRY:
            suggestions.append("Try alternative strategy")
            suggestions.append("Break into smaller changes")

        return suggestions

    def _generate_reasoning(self, input: ReflectionInput, verdict: ReflectionVerdict, score: float) -> str:
        """판정 근거 생성"""
        stability = input.graph_impact.stability_level.value

        if verdict == ReflectionVerdict.ACCEPT:
            return (
                f"✅ ACCEPT (confidence={score:.2f})\n"
                f"  - Test pass rate: {input.test_pass_rate:.0%}\n"
                f"  - Graph stability: {stability}\n"
                f"  - Impact: {input.graph_impact.impact_score:.2f}\n"
                f"  → Safe to proceed"
            )

        elif verdict == ReflectionVerdict.REVISE:
            return (
                f"⚠️ REVISE (confidence={score:.2f})\n"
                f"  - Needs improvement before acceptance\n"
                f"  - Review warnings and fix suggested issues"
            )

        elif verdict == ReflectionVerdict.RETRY:
            return f"🔄 RETRY (confidence={score:.2f})\n  - Current approach not optimal\n  - Try alternative strategy"

        else:  # ROLLBACK
            return "❌ ROLLBACK\n  - Critical issues detected\n  - Immediate rollback recommended"
