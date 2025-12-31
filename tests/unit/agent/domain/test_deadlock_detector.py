"""
Deadlock Detector Unit Tests (SOTA급)

Test Coverage:
- Base Cases: 정상 순환 감지
- Edge Cases: 경계 조건 (자기 순환, 빈 그래프)
- Corner Cases: 복잡한 순환 (3+개 Agent)
- Extreme Cases: 100개 Agent

NO Fake/Stub - Real 컴포넌트
"""

import asyncio
from datetime import datetime

import pytest

from apps.orchestrator.orchestrator.domain.deadlock_detector import (
    DeadlockCycle,
    DeadlockDetector,
    DeadlockError,
    WaitEdge,
)
from apps.orchestrator.orchestrator.domain.multi_agent_models import AgentSession, AgentStateType, AgentType

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def detector():
    """Real DeadlockDetector"""
    return DeadlockDetector(enable_auto_break=True, max_cycle_length=10)


@pytest.fixture
def sessions():
    """Real AgentSession 맵"""
    return {
        "agent-a": AgentSession(
            session_id="sess-a",
            agent_id="agent-a",
            agent_type=AgentType.AI,
            metadata={"priority": 5},
        ),
        "agent-b": AgentSession(
            session_id="sess-b",
            agent_id="agent-b",
            agent_type=AgentType.AI,
            metadata={"priority": 3},
        ),
        "agent-c": AgentSession(
            session_id="sess-c",
            agent_id="agent-c",
            agent_type=AgentType.AI,
            metadata={"priority": 7},
        ),
    }


# ============================================================
# Base Cases (정상 동작)
# ============================================================


@pytest.mark.asyncio
async def test_detect_simple_cycle_2_agents(detector):
    """Base: 2개 Agent 순환 (A → B → A)"""
    # A waits for B
    await detector.add_wait_edge("agent-a", "agent-b", "file1.py")

    # B waits for A → Deadlock!
    with pytest.raises(DeadlockError) as exc_info:
        await detector.add_wait_edge("agent-b", "agent-a", "file2.py")

    # Cycle 확인
    cycle = exc_info.value.cycle
    assert cycle.cycle_length == 2
    assert set(cycle.agents) == {"agent-a", "agent-b"}


@pytest.mark.asyncio
async def test_detect_cycle_3_agents(detector):
    """Base: 3개 Agent 순환 (A → B → C → A)"""
    # A → B
    await detector.add_wait_edge("agent-a", "agent-b", "file1.py")

    # B → C
    await detector.add_wait_edge("agent-b", "agent-c", "file2.py")

    # C → A → Deadlock!
    with pytest.raises(DeadlockError) as exc_info:
        await detector.add_wait_edge("agent-c", "agent-a", "file3.py")

    cycle = exc_info.value.cycle
    assert cycle.cycle_length == 3
    assert set(cycle.agents) == {"agent-a", "agent-b", "agent-c"}


@pytest.mark.asyncio
async def test_no_cycle_linear_chain(detector):
    """Base: 선형 체인 (A → B → C, 순환 없음)"""
    await detector.add_wait_edge("agent-a", "agent-b", "file1.py")
    await detector.add_wait_edge("agent-b", "agent-c", "file2.py")

    # 순환 없음
    cycle = detector.detect_cycle()
    assert cycle is None


@pytest.mark.asyncio
async def test_remove_wait_edge_prevents_deadlock(detector):
    """Base: Edge 제거로 Deadlock 방지"""
    # A → B
    await detector.add_wait_edge("agent-a", "agent-b", "file1.py")

    # Edge 제거
    await detector.remove_wait_edge("agent-a", "agent-b")

    # B → A (이제 순환 아님)
    await detector.add_wait_edge("agent-b", "agent-a", "file2.py")  # OK

    cycle = detector.detect_cycle()
    assert cycle is None


# ============================================================
# Edge Cases (경계 조건)
# ============================================================


@pytest.mark.asyncio
async def test_self_wait_ignored(detector):
    """Edge: 자기 자신 wait → 무시"""
    # A waits for A (무시됨)
    await detector.add_wait_edge("agent-a", "agent-a", "file.py")

    # Wait graph 비어있음
    assert len(detector.wait_graph) == 0


@pytest.mark.asyncio
async def test_empty_wait_graph(detector):
    """Edge: 빈 그래프 → 순환 없음"""
    cycle = detector.detect_cycle()
    assert cycle is None


@pytest.mark.asyncio
async def test_single_agent_no_cycle(detector):
    """Edge: 단일 Agent → 순환 불가"""
    await detector.add_wait_edge("agent-a", "agent-b", "file.py")

    # agent-a만 (나가는 edge)
    # agent-b는 그래프에 없음 (들어오는 edge만)

    cycle = detector.detect_cycle()
    assert cycle is None  # B가 대기 안 하므로 순환 없음


@pytest.mark.asyncio
async def test_max_cycle_length_exceeded(detector):
    """Edge: 순환 길이 초과 → 로그만 (예외 없음)"""
    detector_short = DeadlockDetector(max_cycle_length=2)

    # 3개 순환 생성
    await detector_short.add_wait_edge("a", "b", "f1")
    await detector_short.add_wait_edge("b", "c", "f2")

    # c → a (3개 순환, max=2)
    # detect_cycle()에서 max_cycle_length 체크 → 무시 (예외 없음)
    await detector_short.add_wait_edge("c", "a", "f3")  # OK (예외 없음)

    # 하지만 detect_cycle()로 직접 확인하면 None (무시됨)
    cycle = detector_short.detect_cycle()
    assert cycle is None or cycle.cycle_length <= 2


# ============================================================
# Corner Cases (복잡한 시나리오)
# ============================================================


@pytest.mark.asyncio
async def test_multiple_cycles_in_graph(detector):
    """Corner: 여러 순환 존재"""
    # Cycle 1: A → B → A
    await detector.add_wait_edge("a", "b", "f1")

    # Cycle 2 시도: C → D → C
    await detector.add_wait_edge("c", "d", "f3")

    # A → B → A 완성 → Deadlock
    with pytest.raises(DeadlockError) as exc1:
        await detector.add_wait_edge("b", "a", "f2")

    # 첫 번째 순환만 감지
    assert exc1.value.cycle.cycle_length == 2


@pytest.mark.asyncio
async def test_complex_wait_graph_no_cycle(detector):
    """Corner: 복잡한 그래프, 순환 없음"""
    # 다이아몬드 구조
    # A → B, A → C
    # B → D, C → D
    await detector.add_wait_edge("a", "b", "f1")
    await detector.add_wait_edge("a", "c", "f2")
    await detector.add_wait_edge("b", "d", "f3")
    await detector.add_wait_edge("c", "d", "f4")

    # 순환 없음
    cycle = detector.detect_cycle()
    assert cycle is None


@pytest.mark.asyncio
async def test_break_deadlock_by_priority(detector, sessions):
    """Corner: Priority 기반 해결"""
    # Cycle: A → B → A
    await detector.add_wait_edge("agent-a", "agent-b", "file1.py")

    try:
        await detector.add_wait_edge("agent-b", "agent-a", "file2.py")
    except DeadlockError as e:
        cycle = e.cycle

        # Priority: A=5, B=3
        # → B가 더 낮음 → B abort
        resolution = await detector.break_deadlock(cycle, sessions)

        assert resolution.success
        assert resolution.victim_agent == "agent-b"  # 낮은 priority
        assert resolution.strategy == "priority_based"

        # NOTE: DeadlockDetector는 Session 수정 안 함 (SRP 준수)
        # Caller가 Session abort 책임
        # Wait-for graph만 정리됨
        assert "agent-b" not in detector.wait_graph


# ============================================================
# Extreme Cases (극한 검증)
# ============================================================


@pytest.mark.asyncio
async def test_100_agents_no_deadlock():
    """Extreme: 100개 Agent, 순환 없음"""
    detector = DeadlockDetector()

    # 선형 체인: 0 → 1 → 2 → ... → 99
    for i in range(99):
        await detector.add_wait_edge(f"agent-{i}", f"agent-{i + 1}", f"file{i}.py")

    # 순환 없음
    cycle = detector.detect_cycle()
    assert cycle is None

    # Wait graph 크기
    assert len(detector.wait_graph) == 99


@pytest.mark.asyncio
async def test_100_agents_single_cycle():
    """Extreme: 100개 Agent 순환"""
    detector = DeadlockDetector(max_cycle_length=100)

    # 99개 edge
    for i in range(99):
        await detector.add_wait_edge(f"agent-{i}", f"agent-{i + 1}", f"file{i}.py")

    # 마지막 edge → 순환 완성
    with pytest.raises(DeadlockError) as exc:
        await detector.add_wait_edge("agent-99", "agent-0", "file99.py")

    cycle = exc.value.cycle
    assert cycle.cycle_length == 100


@pytest.mark.asyncio
async def test_rapid_add_remove(detector):
    """Extreme: 빠른 추가/제거 (1000회)"""
    for i in range(1000):
        agent_a = f"agent-{i % 10}"
        agent_b = f"agent-{(i + 1) % 10}"

        await detector.add_wait_edge(agent_a, agent_b, f"file{i}.py")
        await detector.remove_wait_edge(agent_a, agent_b)

    # 그래프 비어있음
    assert len(detector.wait_graph) == 0


# ============================================================
# Statistics Tests
# ============================================================


@pytest.mark.asyncio
async def test_statistics_collection(detector, sessions):
    """Statistics: 통계 수집"""
    # Deadlock 발생 + 해결
    await detector.add_wait_edge("agent-a", "agent-b", "f1")

    try:
        await detector.add_wait_edge("agent-b", "agent-a", "f2")
    except DeadlockError as e:
        await detector.break_deadlock(e.cycle, sessions)

    # 통계 확인
    stats = detector.get_statistics()

    assert stats["total_detections"] == 1
    assert stats["total_resolutions"] == 1
    assert len(stats["detected_cycles"]) == 1


# ============================================================
# Error Cases
# ============================================================


@pytest.mark.asyncio
async def test_break_deadlock_no_sessions(detector):
    """Error: Session 없이 break → Fallback"""
    cycle = DeadlockCycle(agents=["a", "b"], resources=["f1", "f2"])

    # 빈 session map
    resolution = await detector.break_deadlock(cycle, {})

    # Fallback: 첫 Agent
    assert resolution.victim_agent == "a"


@pytest.mark.asyncio
async def test_remove_nonexistent_edge(detector):
    """Error: 없는 Edge 제거 → 안전"""
    # 예외 없음
    await detector.remove_wait_edge("agent-a", "agent-b")
