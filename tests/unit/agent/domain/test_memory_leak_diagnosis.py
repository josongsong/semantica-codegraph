"""
메모리 누수 진단 테스트

목적: 정확히 어디서 누수가 발생하는지 파악
"""

import asyncio
import gc
import tracemalloc

import pytest

from apps.orchestrator.orchestrator.domain.lock_keeper import LockKeeper
from apps.orchestrator.orchestrator.domain.soft_lock_manager import SoftLockManager


@pytest.mark.asyncio
async def test_diagnose_lock_keeper_leak():
    """LockKeeper 메모리 누수 진단"""
    tracemalloc.start()
    gc.collect()

    lock_manager = SoftLockManager()
    keeper = LockKeeper(lock_manager, renewal_interval=0.01)

    agent_id = "agent-1"
    file_path = "main.py"

    await lock_manager.acquire_lock(agent_id, file_path)

    snapshot1 = tracemalloc.take_snapshot()

    # 100번 반복
    for i in range(100):
        keeper_id = await keeper.start_keeping(agent_id, [file_path])
        await asyncio.sleep(0.001)
        await keeper.stop_keeping(keeper_id)

        if i % 10 == 0:
            gc.collect()  # 강제 GC

    gc.collect()
    snapshot2 = tracemalloc.take_snapshot()

    # Top 차이 분석
    top_stats = snapshot2.compare_to(snapshot1, "lineno")

    print("\n=== Top 10 메모리 증가 ===")
    for stat in top_stats[:10]:
        print(stat)

    # 전체 메모리 증가
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    await lock_manager.release_lock(agent_id, file_path)


@pytest.mark.asyncio
async def test_diagnose_softlock_class_variable():
    """SoftLockManager 클래스 변수 누수 진단"""
    # 클래스 변수 초기 상태
    initial_locks = len(SoftLockManager._shared_memory_locks)

    lock_manager = SoftLockManager()

    # 1000번 acquire/release
    for i in range(1000):
        await lock_manager.acquire_lock(f"agent-{i}", f"file_{i}.py")
        await lock_manager.release_lock(f"agent-{i}", f"file_{i}.py")

    # 클래스 변수 정리되었는지
    final_locks = len(SoftLockManager._shared_memory_locks)

    print(f"\n클래스 변수: {initial_locks} → {final_locks}")
    assert final_locks == initial_locks  # 원상복구
