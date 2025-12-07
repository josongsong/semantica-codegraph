"""
Tree-of-Thought Scoring Engine (v8.1)

SOTA: Multi-Criteria Decision Making for Code Domain
"""

import logging
from typing import TYPE_CHECKING

from .tot_models import (
    CodeStrategy,
    ExecutionResult,
    ScoringWeights,
    StrategyScore,
    ToTResult,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ToTScoringEngine:
    """
    Tree-of-Thought Scoring Engine (Domain Service)

    책임:
    - 전략별 실행 결과 평가
    - Multi-Criteria 점수 계산
    - Top-K 전략 선택

    SOTA 기법:
    - MCDM (Multi-Criteria Decision Making)
    - Weighted Sum Model
    - Pareto Optimality 고려
    """

    def __init__(self, weights: dict[str, float] | None = None):
        """
        Args:
            weights: 커스텀 가중치 (Optional)
        """
        self.weights = weights or ScoringWeights.get_weights()

        # 가중치 검증
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total}")

        logger.info(f"ToT Scoring Engine initialized with weights: {self.weights}")

    def score_strategy(self, strategy: CodeStrategy, execution_result: ExecutionResult) -> StrategyScore:
        """
        전략 점수 계산 (Multi-Criteria)

        Args:
            strategy: 전략
            execution_result: 실행 결과

        Returns:
            StrategyScore
        """
        logger.debug(f"Scoring strategy: {strategy.strategy_id}")

        # 개별 점수 계산
        correctness = self._score_correctness(execution_result)
        quality = self._score_quality(execution_result)
        security = self._score_security(execution_result)
        maintainability = self._score_maintainability(execution_result)
        performance = self._score_performance(execution_result)

        # Weighted Sum
        total_score = (
            correctness * self.weights["correctness"]
            + quality * self.weights["quality"]
            + security * self.weights["security"]
            + maintainability * self.weights["maintainability"]
            + performance * self.weights["performance"]
        )

        # Security Veto (SOTA: Critical/High 보안 이슈는 거부권)
        if execution_result.security_severity in ("critical", "high"):
            logger.warning(f"Security veto applied: {execution_result.security_severity}")
            total_score = min(total_score, 0.4)  # 강제로 낮춤

        # Confidence (LLM + 실행 결과 조합)
        confidence = self._calculate_confidence(strategy, execution_result)

        # Reasoning
        strengths, weaknesses = self._analyze_strengths_weaknesses(execution_result, correctness, quality, security)

        recommendation = self._generate_recommendation(total_score, confidence, strengths, weaknesses)

        score = StrategyScore(
            strategy_id=strategy.strategy_id,
            correctness_score=correctness,
            quality_score=quality,
            security_score=security,
            maintainability_score=maintainability,
            performance_score=performance,
            total_score=total_score,
            confidence=confidence,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendation=recommendation,
        )

        logger.info(f"Strategy {strategy.strategy_id}: total={total_score:.2f}, confidence={confidence:.2f}")

        return score

    def rank_strategies(self, strategies: list[CodeStrategy], results: dict[str, ExecutionResult]) -> ToTResult:
        """
        전략들 순위 매기기

        Args:
            strategies: 전략 리스트
            results: {strategy_id: ExecutionResult}

        Returns:
            ToTResult
        """
        logger.info(f"Ranking {len(strategies)} strategies")

        # 각 전략 점수 계산
        scores = {}
        executed_strategies = []

        for strategy in strategies:
            if strategy.strategy_id not in results:
                logger.warning(f"No result for {strategy.strategy_id}, skipping")
                continue

            result = results[strategy.strategy_id]
            score = self.score_strategy(strategy, result)
            scores[strategy.strategy_id] = score
            executed_strategies.append(strategy)

        # Best 찾기
        best_strategy_id = None
        best_score = 0.0

        if scores:
            best_strategy_id = max(scores.keys(), key=lambda sid: scores[sid].get_ranking_key())
            best_score = scores[best_strategy_id].total_score

        # 통계
        total_passed = sum(1 for score in scores.values() if score.is_acceptable())

        tot_result = ToTResult(
            all_strategies=strategies,
            executed_strategies=executed_strategies,
            scores=scores,
            best_strategy_id=best_strategy_id,
            best_score=best_score,
            total_generated=len(strategies),
            total_executed=len(executed_strategies),
            total_passed=total_passed,
        )

        logger.info(f"Ranking complete: {total_passed}/{len(executed_strategies)} passed")

        return tot_result

    # ========================================================================
    # Individual Scoring Methods (Domain Logic)
    # ========================================================================

    def _score_correctness(self, result: ExecutionResult) -> float:
        """
        정확성 점수 (Correctness)

        기준:
        - 컴파일 성공 (필수)
        - 테스트 통과율
        """
        if not result.compile_success:
            return 0.0

        # 컴파일 성공: 기본 점수 0.3
        score = 0.3

        # 테스트 통과율 (0.7)
        score += result.test_pass_rate * 0.7

        return min(score, 1.0)

    def _score_quality(self, result: ExecutionResult) -> float:
        """
        품질 점수 (Quality)

        기준:
        - Lint 에러/경고 (적을수록 좋음)
        - Type 에러 (없어야 함)
        - 복잡도 개선 (낮아지면 좋음)
        """
        score = 1.0

        # Lint 에러 페널티 (최대 -0.3)
        lint_penalty = min(result.lint_errors * 0.05, 0.3)
        score -= lint_penalty

        # Lint 경고 페널티 (최대 -0.1)
        warning_penalty = min(result.lint_warnings * 0.02, 0.1)
        score -= warning_penalty

        # Type 에러 페널티 (최대 -0.2)
        type_penalty = min(result.type_errors * 0.1, 0.2)
        score -= type_penalty

        # 복잡도 개선 보너스 (최대 +0.2)
        if result.complexity_delta < 0:  # 복잡도 감소
            complexity_bonus = min(abs(result.complexity_delta) * 0.01, 0.2)
            score += complexity_bonus
        elif result.complexity_delta > 0:  # 복잡도 증가
            complexity_penalty = min(result.complexity_delta * 0.01, 0.2)
            score -= complexity_penalty

        return max(score, 0.0)

    def _score_security(self, result: ExecutionResult) -> float:
        """
        보안 점수 (Security)

        기준:
        - 보안 이슈 수
        - 보안 심각도
        """
        if result.security_severity == "critical":
            return 0.0
        elif result.security_severity == "high":
            return 0.2
        elif result.security_severity == "medium":
            return 0.5
        elif result.security_severity == "low":
            return 0.8
        else:  # none
            return 1.0

    def _score_maintainability(self, result: ExecutionResult) -> float:
        """
        유지보수성 점수 (Maintainability)

        기준:
        - CFG 변경 (적을수록 좋음)
        - DFG 변경 (적을수록 좋음)
        """
        score = 1.0

        # CFG 변경 페널티
        cfg_changes = abs(result.cfg_nodes_added) + abs(result.cfg_nodes_removed)
        cfg_penalty = min(cfg_changes * 0.01, 0.5)
        score -= cfg_penalty

        # DFG 변경 페널티
        dfg_penalty = min(result.dfg_edges_changed * 0.01, 0.3)
        score -= dfg_penalty

        return max(score, 0.0)

    def _score_performance(self, result: ExecutionResult) -> float:
        """
        성능 점수 (Performance)

        기준:
        - 실행 시간 (빠를수록 좋음)
        - 메모리 사용 (적을수록 좋음)
        """
        score = 1.0

        # 실행 시간 페널티 (10초 기준)
        if result.execution_time > 10.0:
            time_penalty = min((result.execution_time - 10.0) * 0.05, 0.5)
            score -= time_penalty

        # 메모리 페널티 (100MB 기준)
        if result.memory_delta > 100_000_000:
            memory_penalty = min((result.memory_delta - 100_000_000) / 100_000_000 * 0.3, 0.3)
            score -= memory_penalty

        return max(score, 0.0)

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _calculate_confidence(self, strategy: CodeStrategy, result: ExecutionResult) -> float:
        """
        신뢰도 계산

        조합:
        - LLM 신뢰도 (0.4)
        - 실행 성공 (0.6)
        """
        llm_conf = strategy.llm_confidence * 0.4

        # 실행 성공도
        exec_conf = 0.0
        if result.compile_success:
            exec_conf = 0.3
            exec_conf += result.test_pass_rate * 0.3

        return min(llm_conf + exec_conf, 1.0)

    def _analyze_strengths_weaknesses(
        self, result: ExecutionResult, correctness: float, quality: float, security: float
    ) -> tuple[list[str], list[str]]:
        """강점/약점 분석"""
        strengths = []
        weaknesses = []

        # Correctness
        if correctness > 0.8:
            strengths.append(f"높은 테스트 통과율 ({result.test_pass_rate:.0%})")
        elif correctness < 0.5:
            weaknesses.append(f"낮은 테스트 통과율 ({result.test_pass_rate:.0%})")

        # Quality
        if quality > 0.8:
            strengths.append("우수한 코드 품질")
        if result.lint_errors > 5:
            weaknesses.append(f"Lint 에러 {result.lint_errors}개")

        # Security
        if security == 1.0:
            strengths.append("보안 이슈 없음")
        elif result.security_severity in ("high", "critical"):
            weaknesses.append(f"심각한 보안 이슈 ({result.security_severity})")

        # Complexity
        if result.complexity_delta < -5:
            strengths.append(f"복잡도 {abs(result.complexity_delta):.0f} 감소")
        elif result.complexity_delta > 10:
            weaknesses.append(f"복잡도 {result.complexity_delta:.0f} 증가")

        return strengths, weaknesses

    def _generate_recommendation(
        self, total_score: float, confidence: float, strengths: list[str], weaknesses: list[str]
    ) -> str:
        """추천 메시지 생성"""
        if total_score >= 0.8 and confidence >= 0.7:
            return "✅ 강력 추천: 우수한 솔루션"
        elif total_score >= 0.6 and confidence >= 0.5:
            return "⚠️ 조건부 추천: 약점 보완 필요"
        elif total_score >= 0.4:
            return "🔄 재검토 필요: 개선 여지 큼"
        else:
            return "❌ 비추천: 대안 검토 필요"
