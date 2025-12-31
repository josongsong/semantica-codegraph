"""
Fail-Safe Layer (v8.1)

System 2 실패 시 자동 복구 및 안정성 보장
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.orchestrator.orchestrator.domain.experience import AgentExperience

logger = logging.getLogger(__name__)


@dataclass
class FailureHistory:
    """실패 이력 추적"""

    consecutive_failures: int = 0
    last_failure_time: datetime | None = None
    failure_reasons: list[str] = field(default_factory=list)
    total_failures: int = 0
    total_attempts: int = 0

    def record_failure(self, reason: str):
        """실패 기록"""
        self.consecutive_failures += 1
        self.total_failures += 1
        self.total_attempts += 1
        self.last_failure_time = datetime.now()
        self.failure_reasons.append(reason)

        # 최근 10개만 유지
        if len(self.failure_reasons) > 10:
            self.failure_reasons = self.failure_reasons[-10:]

    def record_success(self):
        """성공 기록 (실패 카운터 리셋)"""
        self.consecutive_failures = 0
        self.total_attempts += 1

    def get_failure_rate(self) -> float:
        """실패율 계산"""
        if self.total_attempts == 0:
            return 0.0
        return self.total_failures / self.total_attempts


class FailSafeLayer:
    """
    Fail-Safe Layer (SOTA)

    책임:
    1. System 2 연속 실패 감지
    2. System 1 강제 폴백
    3. HITL 에스컬레이션
    4. 복구 전략 제안

    원칙:
    - 시스템이 완전히 멈추지 않도록
    - 점진적 복구 (graceful degradation)
    - 명확한 알림 및 로깅
    """

    # Constants
    MAX_CONSECUTIVE_FAILURES = 3  # 연속 실패 임계값
    COOLDOWN_PERIOD_MINUTES = 30  # 쿨다운 기간 (분)

    def __init__(self, hitl_manager=None):
        """
        Args:
            hitl_manager: Human-in-the-Loop Manager (Optional)
        """
        self.hitl = hitl_manager
        self.failure_history = FailureHistory()
        self._cooldown_until: datetime | None = None

        logger.info("FailSafeLayer initialized")

    async def execute_with_failsafe(
        self,
        system_2_callable,
        system_1_fallback,
        problem_description: str,
    ):
        """
        System 2 실행 with Fail-Safe

        Args:
            system_2_callable: System 2 실행 함수 (async)
            system_1_fallback: System 1 폴백 함수 (async)
            problem_description: 문제 설명

        Returns:
            실행 결과 (System 2 or System 1)
        """
        # Step 1: Cooldown 체크
        if self._is_in_cooldown():
            logger.warning(f"System 2 in cooldown (until {self._cooldown_until}), forcing System 1")
            return await self._execute_system_1_with_logging(system_1_fallback, reason="Cooldown period")

        # Step 2: 연속 실패 임계값 체크
        if self.failure_history.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            logger.error(
                f"System 2 consecutive failures: {self.failure_history.consecutive_failures}, forcing System 1"
            )

            # Cooldown 설정
            self._set_cooldown()

            # HITL 에스컬레이션
            await self._escalate_to_hitl(
                problem_description,
                reason=f"System 2 failed {self.failure_history.consecutive_failures} times",
            )

            return await self._execute_system_1_with_logging(system_1_fallback, reason="Consecutive failures exceeded")

        # Step 3: System 2 시도
        try:
            logger.info("Executing System 2")
            result = await system_2_callable()

            # 성공
            self.failure_history.record_success()
            logger.info("System 2 succeeded")

            return result

        except Exception as e:
            # 실패
            failure_reason = f"{type(e).__name__}: {str(e)}"
            self.failure_history.record_failure(failure_reason)

            logger.error(
                f"System 2 failed ({self.failure_history.consecutive_failures}/"
                f"{self.MAX_CONSECUTIVE_FAILURES}): {failure_reason}"
            )

            # Step 4: Fallback to System 1
            return await self._execute_system_1_with_logging(
                system_1_fallback, reason=f"System 2 error: {failure_reason}"
            )

    async def _execute_system_1_with_logging(self, system_1_callable, reason: str):
        """
        System 1 실행 with 로깅

        Args:
            system_1_callable: System 1 실행 함수
            reason: Fallback 이유

        Returns:
            System 1 실행 결과
        """
        logger.warning(f"Falling back to System 1: {reason}")

        try:
            result = await system_1_callable()
            logger.info("System 1 succeeded")
            return result

        except Exception as e:
            logger.exception(f"System 1 also failed: {e}")

            # HITL 에스컬레이션 (System 1도 실패)
            await self._escalate_to_hitl(
                "Both System 1 and 2 failed",
                reason=f"Critical failure: {str(e)}",
            )

            raise

    def _is_in_cooldown(self) -> bool:
        """Cooldown 기간인지 확인"""
        if self._cooldown_until is None:
            return False

        return datetime.now() < self._cooldown_until

    def _set_cooldown(self):
        """Cooldown 설정"""
        self._cooldown_until = datetime.now() + timedelta(minutes=self.COOLDOWN_PERIOD_MINUTES)

        logger.warning(f"System 2 cooldown set until {self._cooldown_until}")

    async def _escalate_to_hitl(self, problem: str, reason: str):
        """
        HITL 에스컬레이션

        Args:
            problem: 문제 설명
            reason: 에스컬레이션 이유
        """
        if self.hitl is None:
            logger.warning("No HITL manager configured, skipping escalation")
            return

        try:
            logger.info(f"Escalating to HITL: {reason}")

            # TODO: HITL manager에 에스컬레이션 요청
            # await self.hitl.request_manual_intervention(
            #     problem=problem,
            #     reason=reason,
            #     failure_history=self.failure_history,
            # )

        except Exception as e:
            logger.error(f"Failed to escalate to HITL: {e}")

    def get_health_status(self) -> dict:
        """
        Fail-Safe 상태 조회

        Returns:
            상태 정보
        """
        return {
            "consecutive_failures": self.failure_history.consecutive_failures,
            "total_failures": self.failure_history.total_failures,
            "total_attempts": self.failure_history.total_attempts,
            "failure_rate": self.failure_history.get_failure_rate(),
            "in_cooldown": self._is_in_cooldown(),
            "cooldown_until": self._cooldown_until.isoformat() if self._cooldown_until else None,
            "last_failure_time": (
                self.failure_history.last_failure_time.isoformat() if self.failure_history.last_failure_time else None
            ),
            "recent_failures": self.failure_history.failure_reasons[-5:],
        }


class ExperienceReliabilityManager:
    """
    Experience 신뢰도 관리 (SOTA)

    책임:
    1. 오래된 경험 필터링 (30일 기준)
    2. 성공률 낮은 경험 제외
    3. 데이터 오염 방지
    """

    TRUST_WINDOW_DAYS = 30  # 신뢰 윈도우 (일)
    MIN_SUCCESS_RATE = 0.6  # 최소 성공률

    def filter_trustworthy(self, experiences: list["AgentExperience"]) -> list["AgentExperience"]:
        """
        신뢰할 수 있는 경험만 필터링

        Args:
            experiences: 경험 리스트

        Returns:
            신뢰 가능한 경험 리스트
        """
        if not experiences:
            return []

        cutoff_date = datetime.now() - timedelta(days=self.TRUST_WINDOW_DAYS)

        trustworthy = []

        for exp in experiences:
            # Check 1: 최근 30일 내
            if hasattr(exp, "created_at") and exp.created_at:
                if isinstance(exp.created_at, str):
                    # 문자열인 경우 파싱
                    try:
                        created_at = datetime.fromisoformat(exp.created_at)
                    except (ValueError, AttributeError):
                        logger.warning(f"Invalid created_at format: {exp.created_at}")
                        continue
                else:
                    created_at = exp.created_at

                if created_at < cutoff_date:
                    continue

            # Check 2: 성공 경험
            if hasattr(exp, "success") and not exp.success:
                continue

            # Check 3: 성공률 (있는 경우)
            if hasattr(exp, "success_rate") and exp.success_rate:
                if exp.success_rate < self.MIN_SUCCESS_RATE:
                    continue

            trustworthy.append(exp)

        logger.info(
            f"Filtered experiences: {len(experiences)} → {len(trustworthy)} "
            f"(trust window: {self.TRUST_WINDOW_DAYS} days)"
        )

        return trustworthy

    def assess_experience_quality(self, experience: "AgentExperience") -> float:
        """
        경험 품질 평가

        Args:
            experience: 경험

        Returns:
            품질 점수 (0.0 ~ 1.0)
        """
        score = 1.0

        # Age penalty (오래될수록 감소)
        if hasattr(experience, "created_at") and experience.created_at:
            try:
                if isinstance(experience.created_at, str):
                    created_at = datetime.fromisoformat(experience.created_at)
                else:
                    created_at = experience.created_at

                age_days = (datetime.now() - created_at).days

                if age_days > self.TRUST_WINDOW_DAYS:
                    score *= 0.5  # 오래된 경험
                elif age_days > self.TRUST_WINDOW_DAYS / 2:
                    score *= 0.8  # 중간 정도 오래됨
                # else: 최근 경험, 페널티 없음

            except (ValueError, AttributeError, TypeError):
                score *= 0.7  # 날짜 파싱 실패

        # Success rate
        if hasattr(experience, "success_rate") and experience.success_rate:
            score *= experience.success_rate

        # ToT score
        if hasattr(experience, "tot_score") and experience.tot_score:
            score *= experience.tot_score

        return min(max(score, 0.0), 1.0)
