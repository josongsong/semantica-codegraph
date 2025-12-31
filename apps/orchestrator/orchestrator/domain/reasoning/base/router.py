"""
Dynamic Reasoning Router (v8.1)

System 1/System 2 분기 결정
순수 Domain Logic - 외부 의존성 없음
"""

import logging
from typing import TYPE_CHECKING

from .models import QueryFeatures, ReasoningDecision, ReasoningPath

if TYPE_CHECKING:
    from codegraph_agent.ports.reasoning import IComplexityAnalyzer, IRiskAssessor

logger = logging.getLogger(__name__)


class DynamicReasoningRouter:
    """
    Dynamic Reasoning Router (Domain Service)

    책임:
    - Query 복잡도 분석
    - 위험도 평가
    - System 1/2 경로 결정

    원칙:
    - 순수 비즈니스 로직
    - Framework 독립적
    - 쉬운 테스트 (Mock 불필요)
    """

    # ======================================================================
    # Default Values (Class Constants)
    # ======================================================================

    DEFAULT_COMPLEXITY_THRESHOLD = 0.3
    DEFAULT_RISK_THRESHOLD = 0.4

    # System 1 (Fast Path) 비용/시간
    SYSTEM_1_COST = 0.01  # $0.01
    SYSTEM_1_TIME = 5.0  # 5 seconds

    # System 2 (Slow Path) 비용/시간
    SYSTEM_2_COST = 0.15  # $0.15
    SYSTEM_2_TIME = 45.0  # 45 seconds

    def __init__(
        self,
        complexity_analyzer: "IComplexityAnalyzer | None" = None,
        risk_assessor: "IRiskAssessor | None" = None,
        complexity_threshold: float | None = None,
        risk_threshold: float | None = None,
    ):
        """
        Args:
            complexity_analyzer: 복잡도 분석 Port (Optional)
            risk_assessor: 위험도 평가 Port (Optional)
            complexity_threshold: 복잡도 임계값 (기본: 0.3)
            risk_threshold: 위험도 임계값 (기본: 0.4)
        """
        self._complexity_analyzer = complexity_analyzer
        self._risk_assessor = risk_assessor

        # Instance variables (Thread-safe)
        self.complexity_threshold = (
            complexity_threshold if complexity_threshold is not None else self.DEFAULT_COMPLEXITY_THRESHOLD
        )
        self.risk_threshold = risk_threshold if risk_threshold is not None else self.DEFAULT_RISK_THRESHOLD

    def decide(self, features: QueryFeatures) -> ReasoningDecision:
        """
        System 1/2 경로 결정 (핵심 비즈니스 로직)

        Decision Logic:
        1. Complexity < 0.3 AND Risk < 0.4 → System 1 (Fast)
        2. Otherwise → System 2 (Slow with ToT)

        Args:
            features: Query 피처

        Returns:
            ReasoningDecision
        """
        # Domain Logic: Feature에서 점수 계산
        complexity = features.calculate_complexity_score()
        risk = features.calculate_risk_score()
        confidence_penalty = features.calculate_confidence_penalty()

        # Business Rule 1: Simple & Safe → Fast Path
        if self._is_fast_path_eligible(complexity, risk, features):
            return self._create_fast_path_decision(complexity, risk, confidence_penalty)

        # Business Rule 2: Complex or Risky → Slow Path
        return self._create_slow_path_decision(complexity, risk, confidence_penalty)

    def _is_fast_path_eligible(self, complexity: float, risk: float, features: QueryFeatures) -> bool:
        """
        Fast Path 자격 확인 (Business Rule)

        조건:
        1. 복잡도 < 임계값
        2. 위험도 < 임계값
        3. 이전 실패 < 3회
        4. 보안 sink 없음 (Security → 무조건 System 2)
        """
        # Security Sink가 있으면 무조건 System 2
        if features.touches_security_sink:
            return False

        return complexity < self.complexity_threshold and risk < self.risk_threshold and features.previous_attempts < 3

    def _create_fast_path_decision(
        self, complexity: float, risk: float, confidence_penalty: float
    ) -> ReasoningDecision:
        """Fast Path Decision 생성"""

        # 신뢰도 계산 (높은 신뢰도)
        base_confidence = 0.9
        confidence = max(base_confidence - confidence_penalty, 0.5)

        reasoning = (
            f"✅ Fast Path (System 1)\n"
            f"  - Complexity: {complexity:.2f} (< {self.complexity_threshold})\n"
            f"  - Risk: {risk:.2f} (< {self.risk_threshold})\n"
            f"  - Using v7 Linear Engine"
        )

        logger.info(f"Router Decision: SYSTEM_1 (confidence={confidence:.2f})")

        return ReasoningDecision(
            path=ReasoningPath.SYSTEM_1,
            confidence=confidence,
            reasoning=reasoning,
            complexity_score=complexity,
            risk_score=risk,
            estimated_cost=self.SYSTEM_1_COST,
            estimated_time=self.SYSTEM_1_TIME,
        )

    def _create_slow_path_decision(
        self, complexity: float, risk: float, confidence_penalty: float
    ) -> ReasoningDecision:
        """Slow Path Decision 생성"""

        # 신뢰도 계산 (중간 신뢰도, ToT로 보완)
        base_confidence = 0.7
        confidence = max(base_confidence - confidence_penalty, 0.4)

        # 복잡도/위험도 수준 판단
        complexity_level = "High" if complexity > 0.6 else "Medium"
        risk_level = "High" if risk > 0.6 else "Medium"

        reasoning = (
            f"🔄 Slow Path (System 2)\n"
            f"  - Complexity: {complexity:.2f} ({complexity_level})\n"
            f"  - Risk: {risk:.2f} ({risk_level})\n"
            f"  - Using v8 ReAct + ToT Engine"
        )

        logger.info(f"Router Decision: SYSTEM_2 (confidence={confidence:.2f})")

        return ReasoningDecision(
            path=ReasoningPath.SYSTEM_2,
            confidence=confidence,
            reasoning=reasoning,
            complexity_score=complexity,
            risk_score=risk,
            estimated_cost=self.SYSTEM_2_COST,
            estimated_time=self.SYSTEM_2_TIME,
        )

    # ======================================================================
    # Configuration Methods (Business Rule Tuning)
    # ======================================================================

    def adjust_thresholds(self, complexity_threshold: float | None = None, risk_threshold: float | None = None):
        """
        임계값 조정 (인스턴스별 튜닝)

        Args:
            complexity_threshold: 새로운 복잡도 임계값
            risk_threshold: 새로운 위험도 임계값
        """
        if complexity_threshold is not None:
            if not 0.0 <= complexity_threshold <= 1.0:
                raise ValueError("Complexity threshold must be in [0.0, 1.0]")
            self.complexity_threshold = complexity_threshold
            logger.info(f"[Instance] Complexity threshold updated: {complexity_threshold}")

        if risk_threshold is not None:
            if not 0.0 <= risk_threshold <= 1.0:
                raise ValueError("Risk threshold must be in [0.0, 1.0]")
            self.risk_threshold = risk_threshold
            logger.info(f"[Instance] Risk threshold updated: {risk_threshold}")

    def get_current_config(self) -> dict:
        """현재 설정 조회"""
        return {
            "complexity_threshold": self.complexity_threshold,
            "risk_threshold": self.risk_threshold,
            "system_1_cost": self.SYSTEM_1_COST,
            "system_1_time": self.SYSTEM_1_TIME,
            "system_2_cost": self.SYSTEM_2_COST,
            "system_2_time": self.SYSTEM_2_TIME,
        }
