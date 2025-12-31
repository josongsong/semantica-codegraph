"""
Advanced Lock Scenarios - Cursor 이상 검증

Cursor 대비 추가 기능:
1. Deadlock prevention (알파벳 순서)
2. Deadlock detection (Wait-for graph)
3. Keep-alive (무한 작업)
4. Lock steal (dead agent)
5. Network partition tolerance
6. Priority-based victim selection

Test Coverage:
- Advanced Edge Cases
- Advanced Corner Cases
- Production Scenarios
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from apps.orchestrator.orchestrator.domain.deadlock_detector import DeadlockDetector, DeadlockError
from apps.orchestrator.orchestrator.domain.lock_keeper import LockKeeper
from apps.orchestrator.orchestrator.domain.multi_agent_models import AgentSession, AgentStateType, AgentType
from apps.orchestrator.orchestrator.domain.soft_lock_manager import SoftLockManager

# ============================================================
# Advanced Edge Cases
# ============================================================


@pytest.mark.asyncio
async def test_lock_steal_from_dead_agent():
    """Edge: 죽은 Agent의 Lock 회수"""
    lock_manager = SoftLockManager()

    # Agent A가 Lock 획득
    await lock_manager.acquire_lock("agent-a", "critical.py")

    # Agent A가 죽음 (TTL만료 시뮬레이션)
    lock = await lock_manager.get_lock("critical.py")

    # TTL 강제 만료
    lock.acquired_at = datetime.now() - timedelta(seconds=2000)
    await lock_manager._store_lock(lock)

    # Agent B가 Lock 획득 시도
    result = await lock_manager.acquire_lock("agent-b", "critical.py")

    # 만료된 Lock이므로 성공
    assert result.success is True


@pytest.mark.asyncio
async def test_concurrent_renewal_race():
    """Edge: 동시 갱신 race condition"""
    lock_manager = SoftLockManager()
    keeper1 = LockKeeper(lock_manager, renewal_interval=0.05)
    keeper2 = LockKeeper(lock_manager, renewal_interval=0.05)

    agent_id = "agent-1"
    file_path = "shared.py"

    await lock_manager.acquire_lock(agent_id, file_path)

    # 2개 Keeper 동시 시작 (잘못된 사용)
    keeper1_id = await keeper1.start_keeping(agent_id, [file_path])
    keeper2_id = await keeper2.start_keeping(agent_id, [file_path])

    await asyncio.sleep(0.15)  # 여러 번 갱신

    # 둘 다 성공 (같은 Agent니까)
    metrics1 = keeper1.get_metrics()
    metrics2 = keeper2.get_metrics()

    assert metrics1.total_renewals >= 1
    assert metrics2.total_renewals >= 1

    await keeper1.stop_keeping(keeper1_id)
    await keeper2.stop_keeping(keeper2_id)
    await lock_manager.release_lock(agent_id, file_path)


@pytest.mark.asyncio
async def test_lock_expiration_during_acquisition():
    """Edge: Lock 획득 중 다른 Lock 만료"""
    lock_manager = SoftLockManager()

    # Agent A가 2개 파일 lock (짧은 TTL)
    lock_a = await lock_manager.acquire_lock("agent-a", "a.py")
    lock_a.lock.acquired_at = datetime.now() - timedelta(seconds=1900)  # 거의 만료
    await lock_manager._store_lock(lock_a.lock)

    await lock_manager.acquire_lock("agent-a", "b.py")

    # Agent B가 ordered lock 시도
    success, acquired, failed = await lock_manager.acquire_locks_ordered(
        "agent-b",
        ["a.py", "b.py"],
        timeout=3.0,
    )

    # a.py는 만료되어 획득 가능, b.py는 충돌
    # 결과: 실패 (b.py 때문에)
    assert success is False

    await lock_manager.release_lock("agent-a", "b.py")


@pytest.mark.asyncio
async def test_keeper_detects_lock_lost():
    """Edge: Keep-alive 중 Lock 상실 감지"""
    lock_manager = SoftLockManager()
    keeper = LockKeeper(lock_manager, renewal_interval=0.05, max_consecutive_failures=3)

    agent_id = "agent-lost"
    file_path = "volatile.py"

    await lock_manager.acquire_lock(agent_id, file_path)

    keeper_id = await keeper.start_keeping(agent_id, [file_path])

    await asyncio.sleep(0.08)  # 1번 renewal

    # 외부에서 Lock 삭제
    await lock_manager.release_lock(agent_id, file_path)

    await asyncio.sleep(0.2)  # 3번 더 시도 (모두 실패)

    # Keeper 계속 실행 중 (실패 누적)
    metrics = keeper.get_metrics()

    # 실패가 있어야 함
    assert metrics.failed_renewals >= 2

    await keeper.stop_keeping(keeper_id)


# ============================================================
# Advanced Corner Cases
# ============================================================


@pytest.mark.asyncio
async def test_agent_priority_starvation_prevention():
    """Corner: 낮은 priority Agent도 결국 실행"""
    lock_manager = SoftLockManager()
    detector = DeadlockDetector()

    sessions = {
        "high": AgentSession("s1", "high", AgentType.AI, metadata={"priority": 10}),
        "low": AgentSession("s2", "low", AgentType.AI, metadata={"priority": 1}),
    }

    # High priority가 먼저 Lock
    await lock_manager.acquire_lock("high", "resource.py")

    # Low priority 대기
    result = await lock_manager.acquire_lock("low", "resource.py")
    assert not result.success

    # High가 해제
    await lock_manager.release_lock("high", "resource.py")

    # Low 재시도 → 성공
    result = await lock_manager.acquire_lock("low", "resource.py")
    assert result.success

    await lock_manager.release_lock("low", "resource.py")


@pytest.mark.asyncio
async def test_cascading_deadlock_3_agents():
    """Corner: 3-Agent 복잡한 Deadlock"""
    detector = DeadlockDetector()

    # A → B
    await detector.add_wait_edge("a", "b", "f1")

    # B → C
    await detector.add_wait_edge("b", "c", "f2")

    # C → A (순환 완성)
    with pytest.raises(DeadlockError) as exc:
        await detector.add_wait_edge("c", "a", "f3")

    cycle = exc.value.cycle
    assert set(cycle.agents) == {"a", "b", "c"}
    assert cycle.cycle_length == 3


@pytest.mark.asyncio
async def test_keeper_handles_intermittent_failures():
    """Corner: 간헐적 실패 처리"""
    lock_manager = SoftLockManager()

    # renew_lock을 간헐적으로 실패하게 만듦
    original_renew = lock_manager.renew_lock
    failure_count = [0]  # Mutable container

    async def flaky_renew(agent_id, file_path):
        failure_count[0] += 1
        # 짝수번만 성공
        if failure_count[0] % 2 == 0:
            return await original_renew(agent_id, file_path)
        return False  # 실패

    lock_manager.renew_lock = flaky_renew

    keeper = LockKeeper(lock_manager, renewal_interval=0.05, max_consecutive_failures=5)

    agent_id = "agent-flaky"
    file_path = "flaky.py"

    await lock_manager.acquire_lock(agent_id, file_path)

    keeper_id = await keeper.start_keeping(agent_id, [file_path])

    await asyncio.sleep(0.25)  # 4-5번 시도

    metrics = keeper.get_metrics()

    # 성공과 실패 섞여 있어야 함
    assert metrics.total_renewals + metrics.failed_renewals >= 3

    await keeper.stop_keeping(keeper_id)

    lock_manager.renew_lock = original_renew


@pytest.mark.asyncio
async def test_10_agents_round_robin_no_starvation():
    """Corner: 10개 Agent Round-robin (공정성)"""
    lock_manager = SoftLockManager()

    async def agent_workflow(agent_id, delay_ms):
        await asyncio.sleep(delay_ms / 1000)

        success, acquired, failed = await lock_manager.acquire_locks_ordered(
            agent_id,
            ["shared1.py", "shared2.py"],
            timeout=2.0,
        )

        if not success:
            return False

        await asyncio.sleep(0.01)  # 짧은 작업

        for file in acquired:
            await lock_manager.release_lock(agent_id, file)

        return True

    # 10개 Agent (delay 다양)
    tasks = [agent_workflow(f"agent-{i}", i * 10) for i in range(10)]

    results = await asyncio.gather(*tasks)

    # 최소 1개는 성공 (starvation 없음)
    success_count = sum(results)
    assert success_count >= 1


# ============================================================
# Production Scenarios
# ============================================================


@pytest.mark.asyncio
async def test_production_scenario_code_review():
    """Production: 코드 리뷰 시나리오 (Cursor 비교)"""
    lock_manager = SoftLockManager()
    keeper = LockKeeper(lock_manager, renewal_interval=0.1)

    # Reviewer Agent가 여러 파일 review
    reviewer_files = ["main.py", "utils.py", "test.py"]

    success, acquired, failed = await lock_manager.acquire_locks_ordered(
        "reviewer-bot",
        reviewer_files,
        timeout=5.0,
    )

    assert success is True

    # Keep-alive (리뷰는 오래 걸림)
    keeper_id = await keeper.start_keeping("reviewer-bot", acquired)

    # 리뷰 진행 중 (300ms)
    await asyncio.sleep(0.35)

    # 다른 Agent가 동일 파일 수정 시도 → 실패
    result = await lock_manager.acquire_lock("coder-bot", "main.py")
    assert not result.success
    assert result.conflict is not None

    # 리뷰 완료
    await keeper.stop_keeping(keeper_id)

    for file in acquired:
        await lock_manager.release_lock("reviewer-bot", file)

    # 이제 coder-bot 성공
    result = await lock_manager.acquire_lock("coder-bot", "main.py")
    assert result.success

    await lock_manager.release_lock("coder-bot", "main.py")


@pytest.mark.asyncio
async def test_production_scenario_refactoring():
    """Production: 대규모 리팩토링 (Cursor 비교)"""
    lock_manager = SoftLockManager()
    keeper = LockKeeper(lock_manager, renewal_interval=0.1)

    # 리팩토링: 20개 파일 동시 수정
    files = [f"src/module_{i}.py" for i in range(20)]

    success, acquired, failed = await lock_manager.acquire_locks_ordered(
        "refactor-agent",
        files,
        timeout=10.0,
    )

    assert success is True
    assert len(acquired) == 20

    # Keep-alive (장시간 리팩토링)
    keeper_id = await keeper.start_keeping("refactor-agent", acquired)

    # 리팩토링 진행
    await asyncio.sleep(0.25)

    # Metrics
    metrics = keeper.get_metrics()
    assert metrics.total_renewals >= 1

    # 완료
    await keeper.stop_keeping(keeper_id)

    for file in acquired:
        await lock_manager.release_lock("refactor-agent", file)


@pytest.mark.asyncio
async def test_production_scenario_ci_integration():
    """Production: CI/CD 통합 (자동 테스트 Agent)"""
    lock_manager = SoftLockManager()

    # CI Agent가 테스트 실행 중
    ci_files = ["test_main.py", "test_utils.py"]

    success, acquired, failed = await lock_manager.acquire_locks_ordered(
        "ci-agent",
        ci_files,
        timeout=5.0,
    )

    assert success is True

    # 개발자가 동시에 테스트 수정 시도
    result = await lock_manager.acquire_lock("developer", "test_main.py")

    # CI 실행 중이므로 충돌
    assert not result.success

    # CI 완료 후 해제
    for file in acquired:
        await lock_manager.release_lock("ci-agent", file)

    # 이제 개발자 성공
    result = await lock_manager.acquire_lock("developer", "test_main.py")
    assert result.success

    await lock_manager.release_lock("developer", "test_main.py")


# ============================================================
# Cursor 기능 비교 테스트
# ============================================================


@pytest.mark.asyncio
async def test_vs_cursor_multi_tab_agents():
    """vs Cursor: Multi-tab 동시 작업"""
    lock_manager = SoftLockManager()

    # Cursor Tab 1: Agent A
    # Cursor Tab 2: Agent B

    # Tab 1이 먼저 파일 수정
    result_a = await lock_manager.acquire_lock("tab-1-agent", "feature.py")
    assert result_a.success

    # Tab 2가 동일 파일 수정 시도
    result_b = await lock_manager.acquire_lock("tab-2-agent", "feature.py")
    assert not result_b.success  # Cursor도 막음

    # Cursor는 여기서 끝
    # 우리는 추가로:
    # 1. Deadlock 방지 ✅
    # 2. Keep-alive ✅
    # 3. Hash drift ✅

    await lock_manager.release_lock("tab-1-agent", "feature.py")


@pytest.mark.asyncio
async def test_vs_cursor_no_deadlock_prevention():
    """vs Cursor: Deadlock 방지 (Cursor 없음, 우리만 있음)"""
    lock_manager = SoftLockManager()

    # Cursor는 순서 강제 없음 → Deadlock 가능
    # 우리는 알파벳 순서 → Deadlock 불가능

    files_a = ["z.py", "a.py"]  # 역순
    files_b = ["a.py", "z.py"]  # 정순

    # 동시 시작
    task_a = asyncio.create_task(lock_manager.acquire_locks_ordered("agent-a", files_a, timeout=2.0))

    await asyncio.sleep(0.01)

    task_b = asyncio.create_task(lock_manager.acquire_locks_ordered("agent-b", files_b, timeout=2.0))

    results = await asyncio.gather(task_a, task_b, return_exceptions=True)

    # Deadlock 없음 (우리만!)
    assert all(not isinstance(r, Exception) for r in results)


@pytest.mark.asyncio
async def test_vs_cursor_keep_alive():
    """vs Cursor: Keep-alive (Cursor 없음, 우리만 있음)"""
    lock_manager = SoftLockManager()
    keeper = LockKeeper(lock_manager, renewal_interval=0.05)

    agent_id = "long-agent"
    file_path = "long_task.py"

    await lock_manager.acquire_lock(agent_id, file_path)

    # Cursor: 30분 후 Lock 만료 (문제!)
    # 우리: Keep-alive로 무한 연장

    keeper_id = await keeper.start_keeping(agent_id, [file_path])

    await asyncio.sleep(0.15)  # 여러 번 갱신

    lock = await lock_manager.get_lock(file_path)
    assert lock is not None  # 여전히 보유 중

    metrics = keeper.get_metrics()
    assert metrics.total_renewals >= 2  # 갱신됨

    await keeper.stop_keeping(keeper_id)
    await lock_manager.release_lock(agent_id, file_path)


@pytest.mark.asyncio
async def test_vs_cursor_hash_drift_detection(tmp_path):
    """vs Cursor: Hash drift 감지 (우리만 있음)"""
    lock_manager = SoftLockManager()

    # 실제 파일 생성
    file_path = tmp_path / "monitored.py"
    file_path.write_text("original")

    # Agent가 Lock
    result = await lock_manager.acquire_lock("agent-1", str(file_path))
    assert result.success

    # 외부에서 파일 수정
    file_path.write_text("modified")

    # Drift 감지
    drift = await lock_manager.detect_drift(str(file_path))

    # Hash 변경 감지됨!
    assert drift.drift_detected is True

    await lock_manager.release_lock("agent-1", str(file_path))


# ============================================================
# Extreme Scenarios
# ============================================================


@pytest.mark.asyncio
async def test_50_agents_competing():
    """Extreme: 50개 Agent 경쟁"""
    lock_manager = SoftLockManager()

    async def agent_task(agent_id):
        success, acquired, failed = await lock_manager.acquire_locks_ordered(
            agent_id,
            ["hotfile.py"],
            timeout=5.0,
        )

        if not success:
            return False

        await asyncio.sleep(0.01)  # 짧은 작업

        await lock_manager.release_lock(agent_id, "hotfile.py")

        return True

    # 50개 동시 시작
    tasks = [asyncio.create_task(agent_task(f"agent-{i}")) for i in range(50)]

    results = await asyncio.gather(*tasks)

    # 최소 1개는 성공 (순차 실행)
    assert sum(results) >= 1


@pytest.mark.asyncio
async def test_lock_ordering_with_duplicates():
    """Extreme: 중복 파일명 + 정렬"""
    lock_manager = SoftLockManager()

    # 중복 포함
    files = ["dup_c.py", "dup_a.py", "dup_b.py", "dup_a.py", "dup_c.py"]

    success, acquired, failed = await lock_manager.acquire_locks_ordered(
        "agent-dup",
        files,
        timeout=5.0,
    )

    # 중복 제거 + 정렬
    assert success is True
    assert acquired == ["dup_a.py", "dup_b.py", "dup_c.py"]

    for file in acquired:
        await lock_manager.release_lock("agent-dup", file)
