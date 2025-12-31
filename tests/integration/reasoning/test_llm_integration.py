"""
LLM Integration Tests

실제 LLM 연동 테스트.
"""

import pytest

from apps.orchestrator.orchestrator.adapters.llm_adapter import MockLLMAdapter
from apps.orchestrator.orchestrator.shared.reasoning.beam import BeamCandidate, BeamConfig, BeamSearchEngine
from apps.orchestrator.orchestrator.shared.reasoning.constitutional import Constitution, SafetyChecker
from apps.orchestrator.orchestrator.shared.reasoning.debate import DebateConfig, DebateOrchestrator


class TestMockLLMIntegration:
    """Mock LLM 통합 테스트"""

    @pytest.mark.asyncio
    async def test_mock_llm_generate(self):
        """Mock LLM 기본 생성"""
        llm = MockLLMAdapter(responses=["Test response"])
        result = await llm.generate("test prompt")
        assert result == "Test response"

    @pytest.mark.asyncio
    async def test_mock_llm_batch(self):
        """Mock LLM 배치 생성"""
        llm = MockLLMAdapter(responses=["Response 1", "Response 2"])
        results = await llm.generate_batch(["prompt1", "prompt2"])
        assert len(results) == 2
        assert results[0] == "Response 1"
        assert results[1] == "Response 2"


class TestBeamSearchIntegration:
    """Beam Search + LLM 통합"""

    @pytest.mark.asyncio
    async def test_beam_search_with_mock_llm(self):
        """Beam Search + Mock LLM"""
        llm = MockLLMAdapter(
            responses=[
                "def add(a, b):\n    return a + b",
                "def add(x, y):\n    return x + y",
            ]
        )

        config = BeamConfig(beam_width=2, max_depth=1)
        engine = BeamSearchEngine(config)

        # Expand function (동기 버전)
        def expand_fn(candidate: BeamCandidate) -> list[BeamCandidate]:
            # Mock expansion
            return [
                BeamCandidate(
                    candidate_id=f"c{i}",
                    depth=candidate.depth + 1,
                    code_diff=f"def func{i}(): pass",
                    compile_success=True,
                    test_pass_rate=0.8,
                )
                for i in range(2)
            ]

        # Evaluate function
        def evaluate_fn(candidate: BeamCandidate) -> float:
            return candidate.test_pass_rate

        # Execute
        result = await engine.search("initial", expand_fn, evaluate_fn)

        assert result is not None
        assert result.total_candidates > 0
        assert result.best_candidate is not None


class TestConstitutionalIntegration:
    """Constitutional AI 통합"""

    def test_constitutional_check_with_real_code(self):
        """실제 코드 검증"""
        checker = SafetyChecker(Constitution())

        # 안전한 코드
        safe_code = """
def calculate_sum(numbers: list[int]) -> int:
    return sum(numbers)
"""
        assert checker.is_safe(safe_code)

        # 위험한 코드
        unsafe_code = """
password = "hardcoded_secret_123"
api_key = "sk-1234567890"
"""
        assert not checker.is_safe(unsafe_code)
        violations = checker.check(unsafe_code)
        # password, api_key 중 하나 이상 탐지되어야 함
        assert len(violations) >= 1

    def test_constitutional_severity_levels(self):
        """심각도별 분류"""
        from apps.orchestrator.orchestrator.shared.reasoning.constitutional import RuleSeverity

        checker = SafetyChecker()

        # SQL injection (CRITICAL)
        sql_code = "cursor.execute('SELECT * FROM users WHERE id=' + user_id)"
        violations = checker.check(sql_code)
        critical = [v for v in violations if v.severity == RuleSeverity.CRITICAL]
        assert len(critical) > 0


class TestDebateIntegration:
    """Multi-Agent Debate 통합"""

    @pytest.mark.asyncio
    async def test_debate_with_mock_llm(self):
        """Debate + Mock LLM"""
        llm = MockLLMAdapter(
            responses=[
                "I propose solution A",
                "I propose solution B",
                "I critique solution A",
                "Final decision: solution B is better",
            ]
        )

        config = DebateConfig(max_rounds=2, num_proposers=2, num_critics=1)
        orchestrator = DebateOrchestrator(config)

        # Generate function
        async def generate_fn(prompt: str) -> str:
            return await llm.generate(prompt)

        # Execute
        result = await orchestrator.orchestrate_debate("test problem", generate_fn)

        assert result is not None
        assert result.final_decision is not None
        assert result.total_rounds > 0
        assert len(result.rounds) > 0


@pytest.mark.skip(reason="Real LLM tests require OPENAI_API_KEY")
class TestRealLLMIntegration:
    """실제 LLM 테스트 (optional)"""

    @pytest.mark.asyncio
    async def test_openai_adapter(self):
        """OpenAI Adapter 실제 호출"""
        import os

        from apps.orchestrator.orchestrator.adapters.llm_adapter import OpenAIAdapter

        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

        llm = OpenAIAdapter()
        result = await llm.generate("Say hello", max_tokens=10)

        assert isinstance(result, str)
        assert len(result) > 0
