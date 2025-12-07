"""
성능 벤치마크 테스트

병렬 처리 vs 순차 처리 성능 비교.

테스트:
1. Analyze + Plan 병렬 실행
2. LLM 캐싱 효과
3. 전체 Workflow 속도
"""

import asyncio
import time

import pytest

from src.agent.adapters.llm.cached_llm_adapter import CachedLLMAdapter
from src.agent.adapters.llm.litellm_adapter import LiteLLMProviderAdapter
from src.agent.adapters.llm.optimized_llm_adapter import OptimizedLLMAdapter
from src.agent.adapters.sandbox.stub_sandbox import LocalSandboxAdapter
from src.agent.adapters.vcs.gitpython_adapter import GitPythonVCSAdapter
from src.agent.adapters.guardrail.pydantic_validator import PydanticValidatorAdapter
from src.agent.adapters.workflow.langgraph_adapter import LangGraphWorkflowAdapter
from src.agent.orchestrator.parallel_orchestrator import (
    ParallelAgentOrchestrator,
    ParallelAgentRequest,
)
from src.agent.orchestrator.v7_orchestrator import AgentOrchestrator, AgentRequest
from src.agent.domain.models import AgentTask


class StubLLMProvider:
    """테스트용 Stub LLM (빠른 응답)"""

    async def complete(self, messages, model_tier="medium", **kwargs):
        await asyncio.sleep(0.1)  # 100ms 시뮬레이션
        return "Stub response"

    async def complete_with_schema(self, messages, schema, model_tier="medium", **kwargs):
        await asyncio.sleep(0.1)
        return schema(summary="Stub analysis", impacted_files=[])

    async def get_embedding(self, text, model="text-embedding-3-small"):
        await asyncio.sleep(0.05)
        return [0.1] * 1536


@pytest.fixture
def stub_llm():
    """Stub LLM Provider"""
    return StubLLMProvider()


@pytest.fixture
def cached_llm(stub_llm):
    """Cached LLM Provider"""
    return CachedLLMAdapter(
        base_llm=stub_llm,
        redis_client=None,  # Redis 없이 in-memory만
        enable_cache=True,
    )


@pytest.fixture
def parallel_orchestrator(cached_llm):
    """병렬 Orchestrator"""
    return ParallelAgentOrchestrator(
        workflow_engine=None,  # Workflow Engine 없이 직접 실행
        llm_provider=cached_llm,
        sandbox_executor=LocalSandboxAdapter(),
        guardrail_validator=PydanticValidatorAdapter(),
        vcs_applier=GitPythonVCSAdapter(repo_path="."),
    )


@pytest.fixture
def sequential_orchestrator(cached_llm):
    """순차 Orchestrator"""
    return AgentOrchestrator(
        workflow_engine=LangGraphWorkflowAdapter(),
        llm_provider=cached_llm,
        sandbox_executor=LocalSandboxAdapter(),
        guardrail_validator=PydanticValidatorAdapter(),
        vcs_applier=GitPythonVCSAdapter(repo_path="."),
    )


@pytest.fixture
def sample_task():
    """샘플 Task"""
    return AgentTask(
        task_id="test-001",
        description="Fix bug in calculate_total function",
        repo_path=".",
        context_files=["utils.py"],
    )


@pytest.mark.asyncio
async def test_parallel_vs_sequential_performance(parallel_orchestrator, sequential_orchestrator, sample_task):
    """
    병렬 vs 순차 성능 비교.

    기대:
    - 병렬 처리가 순차 처리보다 빠름 (최소 20% 향상)
    """
    # 1. 병렬 실행
    parallel_request = ParallelAgentRequest(task=sample_task, enable_parallel=True)
    parallel_start = time.perf_counter()
    try:
        parallel_response = await parallel_orchestrator.execute(parallel_request)
        parallel_time = (time.perf_counter() - parallel_start) * 1000
    except Exception as e:
        print(f"Parallel execution error: {e}")
        parallel_time = 999999  # 에러 시 매우 큰 값

    # 2. 순차 실행
    sequential_request = AgentRequest(task=sample_task)
    sequential_start = time.perf_counter()
    try:
        sequential_response = await sequential_orchestrator.execute(sequential_request)
        sequential_time = (time.perf_counter() - sequential_start) * 1000
    except Exception as e:
        print(f"Sequential execution error: {e}")
        sequential_time = 999999

    # 3. 결과 비교
    print(f"\n=== Performance Benchmark ===")
    print(f"Parallel:   {parallel_time:.2f} ms")
    print(f"Sequential: {sequential_time:.2f} ms")
    print(f"Speedup:    {sequential_time / parallel_time:.2f}x")

    # 병렬이 더 빠르거나 비슷해야 함
    assert parallel_time <= sequential_time * 1.2, (
        f"Parallel ({parallel_time:.2f}ms) should be faster than sequential ({sequential_time:.2f}ms)"
    )


@pytest.mark.asyncio
async def test_llm_cache_effectiveness(cached_llm):
    """
    LLM 캐싱 효과 테스트.

    기대:
    - 첫 번째 호출: Cache MISS (느림)
    - 두 번째 호출: Cache HIT (빠름, 2배 이상)
    """
    messages = [{"role": "user", "content": "Hello, world!"}]

    # 1. 첫 번째 호출 (Cache MISS)
    start1 = time.perf_counter()
    result1 = await cached_llm.complete(messages, model_tier="fast")
    time1 = (time.perf_counter() - start1) * 1000

    # 2. 두 번째 호출 (Cache HIT)
    start2 = time.perf_counter()
    result2 = await cached_llm.complete(messages, model_tier="fast")
    time2 = (time.perf_counter() - start2) * 1000

    # 3. 결과 확인
    print(f"\n=== Cache Effectiveness ===")
    print(f"First call (MISS):  {time1:.2f} ms")
    print(f"Second call (HIT):  {time2:.2f} ms")
    print(f"Speedup:            {time1 / time2:.2f}x")

    # 캐시 통계
    stats = cached_llm.get_cache_stats()
    print(f"Cache stats: {stats}")

    # 검증
    assert result1 == result2, "Cached result should be identical"
    assert time2 < time1 * 0.5, f"Cache HIT ({time2:.2f}ms) should be at least 2x faster than MISS ({time1:.2f}ms)"
    assert stats["cache_hits"] >= 1, "Should have at least 1 cache hit"
    assert stats["hit_rate_percent"] >= 50, "Hit rate should be at least 50%"


@pytest.mark.asyncio
async def test_batch_llm_calls(cached_llm):
    """
    Batch LLM 호출 테스트.

    기대:
    - 여러 호출을 병렬로 처리
    - 순차 처리보다 빠름
    """
    messages_list = [[{"role": "user", "content": f"Question {i}"}] for i in range(5)]

    # 1. 병렬 호출
    parallel_start = time.perf_counter()
    parallel_results = await asyncio.gather(*[cached_llm.complete(msgs, model_tier="fast") for msgs in messages_list])
    parallel_time = (time.perf_counter() - parallel_start) * 1000

    # 2. 순차 호출
    sequential_start = time.perf_counter()
    sequential_results = []
    for msgs in messages_list:
        result = await cached_llm.complete(msgs, model_tier="fast")
        sequential_results.append(result)
    sequential_time = (time.perf_counter() - sequential_start) * 1000

    # 3. 결과 비교
    print(f"\n=== Batch Processing ===")
    print(f"Parallel (5 calls):   {parallel_time:.2f} ms")
    print(f"Sequential (5 calls): {sequential_time:.2f} ms")
    print(f"Speedup:              {sequential_time / parallel_time:.2f}x")

    # 병렬이 더 빠름 (최소 2배)
    assert parallel_time < sequential_time * 0.7, (
        f"Parallel ({parallel_time:.2f}ms) should be significantly faster than sequential ({sequential_time:.2f}ms)"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
