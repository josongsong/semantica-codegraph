"""
Reasoning Strategies Performance Benchmarks

추론 전략 성능 벤치마크.
"""

import time

import pytest

from apps.orchestrator.orchestrator.adapters.llm_adapter import MockLLMAdapter
from apps.orchestrator.orchestrator.shared.reasoning.beam import BeamCandidate, BeamConfig, BeamSearchEngine
from apps.orchestrator.orchestrator.shared.reasoning.constitutional import SafetyChecker
from apps.orchestrator.orchestrator.shared.reasoning.sampling import AlphaCodeConfig, AlphaCodeSampler
from apps.orchestrator.orchestrator.shared.reasoning.ttc import ComputeAllocator, TTCConfig


class TestBeamSearchPerformance:
    """Beam Search 성능"""

    def test_beam_search_scaling(self, benchmark):
        """Beam width 증가에 따른 성능"""

        def run_beam_search():
            config = BeamConfig(beam_width=5, max_depth=2)
            engine = BeamSearchEngine(config)

            # Mock functions
            def expand_fn(candidate):
                return [
                    BeamCandidate(
                        f"c{i}",
                        candidate.depth + 1,
                        compile_success=True,
                        test_pass_rate=0.7 + i * 0.05,
                    )
                    for i in range(3)
                ]

            def evaluate_fn(candidate):
                return candidate.test_pass_rate

            return engine.search_sync("test", expand_fn, evaluate_fn)

        result = benchmark(run_beam_search)
        assert result.total_candidates > 0

    @pytest.mark.parametrize("beam_width", [3, 5, 10])
    def test_beam_width_impact(self, beam_width, benchmark):
        """Beam width별 성능 비교"""

        def run():
            config = BeamConfig(beam_width=beam_width, max_depth=2)
            engine = BeamSearchEngine(config)

            def expand_fn(c):
                return [BeamCandidate(f"c{i}", c.depth + 1) for i in range(5)]

            def evaluate_fn(c):
                return 0.8

            return engine.search_sync("test", expand_fn, evaluate_fn)

        result = benchmark(run)
        assert result is not None


class TestConstitutionalPerformance:
    """Constitutional AI 성능"""

    def test_safety_check_performance(self, benchmark):
        """안전성 검사 성능"""
        checker = SafetyChecker()

        code = """
def process_user_data(user_id: int, data: dict) -> dict:
    # Process user data
    result = {"user_id": user_id, "processed": True}
    return result
"""

        def run():
            return checker.check(code)

        violations = benchmark(run)
        assert isinstance(violations, list)

    @pytest.mark.parametrize("code_size", [100, 500, 1000])
    def test_code_size_impact(self, code_size, benchmark):
        """코드 크기별 성능"""
        checker = SafetyChecker()

        # 코드 생성
        code = "\n".join([f"var{i} = {i}" for i in range(code_size)])

        result = benchmark(checker.check, code)
        assert isinstance(result, list)


class TestTTCPerformance:
    """Test-Time Compute 성능"""

    def test_difficulty_estimation_performance(self, benchmark):
        """난이도 추정 성능"""
        allocator = ComputeAllocator(TTCConfig())

        tasks = [
            "simple task",
            "complex difficult task",
            "extremely complex intricate task",
        ]

        def run():
            return [allocator.allocate(task) for task in tasks]

        results = benchmark(run)
        assert len(results) == 3


class TestMemoryUsage:
    """메모리 사용량 테스트"""

    def test_beam_search_memory(self):
        """Beam Search 메모리 사용량"""
        import tracemalloc

        tracemalloc.start()

        config = BeamConfig(beam_width=10, max_depth=3)
        engine = BeamSearchEngine(config)

        def expand_fn(c):
            return [BeamCandidate(f"c{i}", c.depth + 1) for i in range(5)]

        def evaluate_fn(c):
            return 0.7

        result = engine.search_sync("test", expand_fn, evaluate_fn)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # 메모리 사용량 확인 (10MB 이하)
        assert peak < 10 * 1024 * 1024  # 10 MB
        assert result.total_candidates > 0


class TestConcurrency:
    """동시성 테스트"""

    @pytest.mark.asyncio
    async def test_concurrent_llm_calls(self):
        """병렬 LLM 호출"""
        import asyncio

        llm = MockLLMAdapter(responses=["Response"] * 10)

        start = time.time()
        tasks = [llm.generate(f"prompt {i}") for i in range(10)]
        results = await asyncio.gather(*tasks)
        duration = time.time() - start

        assert len(results) == 10
        # 병렬이므로 1초 이내
        assert duration < 1.0
