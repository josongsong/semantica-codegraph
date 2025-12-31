"""
Fail-Safe Layer Tests

순수 Domain Logic 테스트
"""

from datetime import datetime, timedelta

import pytest

from apps.orchestrator.orchestrator.reasoning.fail_safe import (
    ExperienceReliabilityManager,
    FailSafeLayer,
    FailureHistory,
)


class TestFailureHistory:
    """FailureHistory 테스트"""

    def test_record_failure(self):
        """실패 기록"""
        history = FailureHistory()

        history.record_failure("Error 1")
        history.record_failure("Error 2")

        assert history.consecutive_failures == 2
        assert history.total_failures == 2
        assert history.total_attempts == 2
        assert len(history.failure_reasons) == 2

    def test_record_success_resets_consecutive(self):
        """성공 시 연속 실패 카운터 리셋"""
        history = FailureHistory()

        history.record_failure("Error 1")
        history.record_failure("Error 2")
        history.record_success()

        assert history.consecutive_failures == 0
        assert history.total_failures == 2
        assert history.total_attempts == 3

    def test_failure_rate_calculation(self):
        """실패율 계산"""
        history = FailureHistory()

        history.record_failure("Error 1")
        history.record_success()
        history.record_failure("Error 2")

        rate = history.get_failure_rate()

        assert rate == pytest.approx(2 / 3)

    def test_failure_reasons_limit(self):
        """실패 이유 최대 10개 유지"""
        history = FailureHistory()

        for i in range(15):
            history.record_failure(f"Error {i}")

        assert len(history.failure_reasons) == 10
        assert history.failure_reasons[0] == "Error 5"  # 처음 5개는 제거됨
        assert history.failure_reasons[-1] == "Error 14"


class TestFailSafeLayer:
    """FailSafeLayer 테스트"""

    @pytest.mark.asyncio
    async def test_system2_success(self):
        """System 2 성공"""
        fail_safe = FailSafeLayer()

        async def system_2():
            return "system2_result"

        async def system_1():
            return "system1_result"

        result = await fail_safe.execute_with_failsafe(
            system_2_callable=system_2,
            system_1_fallback=system_1,
            problem_description="Test problem",
        )

        assert result == "system2_result"
        assert fail_safe.failure_history.consecutive_failures == 0
        assert fail_safe.failure_history.total_attempts == 1

    @pytest.mark.asyncio
    async def test_system2_failure_fallback_to_system1(self):
        """System 2 실패 → System 1 fallback"""
        fail_safe = FailSafeLayer()

        async def system_2():
            raise ValueError("System 2 failed")

        async def system_1():
            return "system1_result"

        result = await fail_safe.execute_with_failsafe(
            system_2_callable=system_2,
            system_1_fallback=system_1,
            problem_description="Test problem",
        )

        assert result == "system1_result"
        assert fail_safe.failure_history.consecutive_failures == 1
        assert fail_safe.failure_history.total_failures == 1

    @pytest.mark.asyncio
    async def test_consecutive_failures_force_system1(self):
        """연속 실패 임계값 초과 → System 1 강제"""
        fail_safe = FailSafeLayer()

        async def system_2():
            raise ValueError("System 2 failed")

        async def system_1():
            return "system1_result"

        # 3번 연속 실패
        for _ in range(3):
            await fail_safe.execute_with_failsafe(
                system_2_callable=system_2,
                system_1_fallback=system_1,
                problem_description="Test",
            )

        # 4번째: System 2 시도 안 하고 바로 System 1
        call_count = 0

        async def system_2_tracked():
            nonlocal call_count
            call_count += 1
            return "system2_result"

        result = await fail_safe.execute_with_failsafe(
            system_2_callable=system_2_tracked,
            system_1_fallback=system_1,
            problem_description="Test",
        )

        assert result == "system1_result"
        assert call_count == 0  # System 2가 호출되지 않음

    @pytest.mark.asyncio
    async def test_cooldown_period(self):
        """Cooldown 기간 동안 System 1 강제"""
        fail_safe = FailSafeLayer()

        # Cooldown 설정
        fail_safe._set_cooldown()

        async def system_2():
            return "system2_result"

        async def system_1():
            return "system1_result"

        result = await fail_safe.execute_with_failsafe(
            system_2_callable=system_2,
            system_1_fallback=system_1,
            problem_description="Test",
        )

        assert result == "system1_result"
        assert fail_safe._is_in_cooldown() is True

    def test_health_status(self):
        """Health Status 조회"""
        fail_safe = FailSafeLayer()

        status = fail_safe.get_health_status()

        assert "consecutive_failures" in status
        assert "total_failures" in status
        assert "failure_rate" in status
        assert "in_cooldown" in status

        assert status["consecutive_failures"] == 0
        assert status["in_cooldown"] is False


class TestExperienceReliabilityManager:
    """ExperienceReliabilityManager 테스트"""

    def test_filter_trustworthy_recent_success(self):
        """최근 성공 경험 필터링"""
        from dataclasses import dataclass

        @dataclass
        class MockExperience:
            created_at: datetime
            success: bool
            success_rate: float = 1.0

        manager = ExperienceReliabilityManager()

        # 최근 성공 경험
        recent_success = MockExperience(
            created_at=datetime.now() - timedelta(days=5),
            success=True,
        )

        experiences = [recent_success]
        result = manager.filter_trustworthy(experiences)

        assert len(result) == 1

    def test_filter_trustworthy_old_experience(self):
        """오래된 경험 제외"""
        from dataclasses import dataclass

        @dataclass
        class MockExperience:
            created_at: datetime
            success: bool

        manager = ExperienceReliabilityManager()

        # 40일 전 경험 (TRUST_WINDOW_DAYS = 30)
        old_experience = MockExperience(
            created_at=datetime.now() - timedelta(days=40),
            success=True,
        )

        experiences = [old_experience]
        result = manager.filter_trustworthy(experiences)

        assert len(result) == 0

    def test_filter_trustworthy_failed_experience(self):
        """실패 경험 제외"""
        from dataclasses import dataclass

        @dataclass
        class MockExperience:
            created_at: datetime
            success: bool

        manager = ExperienceReliabilityManager()

        failed_exp = MockExperience(
            created_at=datetime.now() - timedelta(days=1),
            success=False,
        )

        experiences = [failed_exp]
        result = manager.filter_trustworthy(experiences)

        assert len(result) == 0

    def test_filter_trustworthy_low_success_rate(self):
        """낮은 성공률 경험 제외"""
        from dataclasses import dataclass

        @dataclass
        class MockExperience:
            created_at: datetime
            success: bool
            success_rate: float

        manager = ExperienceReliabilityManager()

        low_success = MockExperience(
            created_at=datetime.now() - timedelta(days=1),
            success=True,
            success_rate=0.3,  # MIN_SUCCESS_RATE = 0.6
        )

        experiences = [low_success]
        result = manager.filter_trustworthy(experiences)

        assert len(result) == 0

    def test_assess_experience_quality_recent(self):
        """최근 경험 품질 평가"""
        from dataclasses import dataclass

        @dataclass
        class MockExperience:
            created_at: datetime
            success_rate: float = 0.9
            tot_score: float = 0.9

        manager = ExperienceReliabilityManager()

        recent_exp = MockExperience(
            created_at=datetime.now() - timedelta(days=1),
        )

        quality = manager.assess_experience_quality(recent_exp)

        # Recent (no penalty) * success_rate * tot_score
        assert quality >= 0.8

    def test_assess_experience_quality_old(self):
        """오래된 경험 품질 평가"""
        from dataclasses import dataclass

        @dataclass
        class MockExperience:
            created_at: datetime
            success_rate: float = 0.9
            tot_score: float = 0.9

        manager = ExperienceReliabilityManager()

        old_exp = MockExperience(
            created_at=datetime.now() - timedelta(days=40),
        )

        quality = manager.assess_experience_quality(old_exp)

        # Old (0.5 penalty) * success_rate * tot_score
        assert quality < 0.5


# Standalone execution
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
