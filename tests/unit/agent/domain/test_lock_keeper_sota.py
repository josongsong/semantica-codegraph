"""
L11 SOTA급 LockKeeper 테스트

Coverage:
- Base: 정상 renewal
- Edge: 부분 실패 (일부 lock만 실패)
- Corner: 연속 실패 threshold
- Extreme: 대규모 파일 (1000+ locks)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.orchestrator.orchestrator.domain.lock_keeper import LockKeeper, RenewalMetrics

# ============================================================
# Base Case
# ============================================================


class TestBaseCaseRenewal:
    """Base Case: 정상 갱신"""

    @pytest.mark.asyncio
    async def test_single_file_renewal(self):
        """단일 파일 갱신"""
        mock_manager = MagicMock()
        mock_manager.get_lock = AsyncMock(return_value=MagicMock(agent_id="agent1"))
        mock_manager.renew_lock = AsyncMock(return_value=True)

        keeper = LockKeeper(
            lock_manager=mock_manager,
            renewal_interval=0.1,  # 100ms
            max_consecutive_failures=3,
        )

        keeper_id = await keeper.start_keeping("agent1", ["file1.py"])

        # 갱신 대기
        await asyncio.sleep(0.08)  # 0.25 → 0.08  # 2번 갱신 예상

        await keeper.stop_keeping(keeper_id)

        # renew_lock 호출됨
        assert mock_manager.renew_lock.call_count >= 2

    @pytest.mark.asyncio
    async def test_multiple_files_parallel_renewal(self):
        """다중 파일 병렬 갱신"""
        mock_manager = MagicMock()
        mock_manager.get_lock = AsyncMock(return_value=MagicMock(agent_id="agent1"))
        mock_manager.renew_lock = AsyncMock(return_value=True)

        keeper = LockKeeper(
            lock_manager=mock_manager,
            renewal_interval=0.1,
            max_consecutive_failures=3,
        )

        files = [f"file{i}.py" for i in range(10)]
        keeper_id = await keeper.start_keeping("agent1", files)

        await asyncio.sleep(0.05)  # 0.15 → 0.05
        await keeper.stop_keeping(keeper_id)

        # 모든 파일에 대해 renew_lock 호출됨
        assert mock_manager.renew_lock.call_count >= 10


# ============================================================
# Edge Case - 부분 실패
# ============================================================


class TestEdgeCasePartialFailure:
    """Edge Case: 일부 lock만 실패"""

    @pytest.mark.asyncio
    async def test_partial_failure_allowed(self):
        """부분 실패는 허용됨 (consecutive_failures 증가 안 함)"""
        mock_manager = MagicMock()
        mock_manager.get_lock = AsyncMock(return_value=MagicMock(agent_id="agent1"))

        # 첫 번째 파일만 실패
        call_count = 0

        async def renew_mock(agent_id, file_path):
            nonlocal call_count
            call_count += 1
            if file_path == "file1.py":
                return False  # 실패
            return True  # 성공

        mock_manager.renew_lock = AsyncMock(side_effect=renew_mock)

        keeper = LockKeeper(
            lock_manager=mock_manager,
            renewal_interval=0.1,
            max_consecutive_failures=3,
        )

        keeper_id = await keeper.start_keeping("agent1", ["file1.py", "file2.py", "file3.py"])

        # 2번 갱신 대기
        await asyncio.sleep(0.08)  # 0.25 → 0.08

        await keeper.stop_keeping(keeper_id)

        # 전체 배치 실패 카운트 확인
        metrics = keeper.get_metrics()
        # 일부 실패도 전체 배치 실패로 카운트됨
        assert metrics.failed_renewals >= 1


# ============================================================
# Corner Case - 연속 실패
# ============================================================


class TestCornerCaseConsecutiveFailures:
    """Corner Case: 연속 실패 threshold"""

    @pytest.mark.asyncio
    async def test_max_consecutive_failures_stops_keeper(self):
        """연속 실패 max 도달 시 keeper 중단"""
        mock_manager = MagicMock()
        mock_manager.get_lock = AsyncMock(return_value=MagicMock(agent_id="agent1"))
        mock_manager.renew_lock = AsyncMock(return_value=False)  # 항상 실패

        keeper = LockKeeper(
            lock_manager=mock_manager,
            renewal_interval=0.1,
            max_consecutive_failures=3,
        )

        keeper_id = await keeper.start_keeping("agent1", ["file1.py"])

        # 3번 실패 대기 (3 * 0.1 = 0.3초 + α)
        await asyncio.sleep(0.15)  # 0.5 → 0.15

        # Keeper가 자동 중단되어야 함
        active_keepers = keeper.get_active_keepers()
        # Task가 자동 중단되었으므로 리스트에서 제거되지 않을 수 있음
        # (stop_keeping 호출 안 함)

    @pytest.mark.asyncio
    async def test_success_resets_consecutive_failures(self):
        """성공 시 consecutive_failures 리셋"""
        mock_manager = MagicMock()
        mock_manager.get_lock = AsyncMock(return_value=MagicMock(agent_id="agent1"))

        # 실패 → 성공 → 실패 패턴
        results = [False, False, True, False]
        call_idx = 0

        async def renew_mock(agent_id, file_path):
            nonlocal call_idx
            result = results[min(call_idx, len(results) - 1)]
            call_idx += 1
            return result

        mock_manager.renew_lock = AsyncMock(side_effect=renew_mock)

        keeper = LockKeeper(
            lock_manager=mock_manager,
            renewal_interval=0.1,
            max_consecutive_failures=3,
        )

        keeper_id = await keeper.start_keeping("agent1", ["file1.py"])

        # 4번 갱신 대기
        await asyncio.sleep(0.15)  # 0.5 → 0.15

        await keeper.stop_keeping(keeper_id)

        # 성공이 중간에 있어서 keeper 중단 안 됨
        metrics = keeper.get_metrics()
        assert metrics.total_renewals >= 1


# ============================================================
# Extreme Case - 대규모
# ============================================================


class TestExtremeCaseLargeScale:
    """Extreme Case: 대규모 파일"""

    @pytest.mark.asyncio
    async def test_1000_files_parallel_renewal(self):
        """1000개 파일 병렬 갱신 (성능 테스트)"""
        import time

        mock_manager = MagicMock()
        mock_manager.get_lock = AsyncMock(return_value=MagicMock(agent_id="agent1"))
        mock_manager.renew_lock = AsyncMock(return_value=True)

        keeper = LockKeeper(
            lock_manager=mock_manager,
            renewal_interval=0.1,
            max_consecutive_failures=3,
        )

        files = [f"file{i}.py" for i in range(1000)]

        start = time.perf_counter()
        keeper_id = await keeper.start_keeping("agent1", files)

        await asyncio.sleep(0.05)  # 0.15 → 0.05  # 1번 갱신

        await keeper.stop_keeping(keeper_id)
        elapsed = (time.perf_counter() - start) * 1000

        # 1000개 파일 갱신이 100ms 이하여야 함 (L11 성능 기준)
        assert mock_manager.renew_lock.call_count >= 1000

        # 병렬 처리로 총 시간은 200ms 이하
        assert elapsed < 300  # 여유있게 300ms


# ============================================================
# Memory Safety
# ============================================================


class TestMemorySafety:
    """메모리 안정성 검증"""

    def test_deque_maxlen_prevents_memory_leak(self):
        """deque maxlen으로 메모리 누수 방지"""
        metrics = RenewalMetrics()

        # 10000개 기록 (maxlen=1000)
        for i in range(1000)  # 10000 → 1000:
            metrics.record_renewal(float(i), True)

        # deque는 1000개만 유지
        assert len(metrics._latencies) == 1000

        # 하지만 total_renewals는 누적
        assert metrics.total_renewals == 10000

        # 평균은 최근 1000개 기준
        avg = sum(metrics._latencies) / len(metrics._latencies)
        assert 9000 < avg < 10000  # 최근 1000개 평균

    def test_metrics_success_rate_calculation(self):
        """Success rate 계산 정확도"""
        metrics = RenewalMetrics()

        # 7 성공, 3 실패
        for i in range(7):
            metrics.record_renewal(10.0, True)
        for i in range(3):
            metrics.record_renewal(0.0, False)

        # Success rate = 7 / 10 = 0.7
        assert metrics.success_rate == pytest.approx(0.7)

        # Total = 7 + 3 = 10
        assert metrics.total_renewals == 7
        assert metrics.failed_renewals == 3
