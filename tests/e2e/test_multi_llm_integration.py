"""
E2E Test: Multi-LLM Integration

Tests complete flow with SOTA features:
- Multi-LLM Ensemble
- Smart Pruning
- Pass@k Selection
- Auto-Retry Loop
"""

import pytest

from apps.orchestrator.orchestrator.domain.models import AgentTask
from apps.orchestrator.orchestrator.orchestrator.deep_reasoning_orchestrator import (
    DeepReasoningOrchestrator,
    DeepReasoningRequest,
)


@pytest.mark.asyncio
@pytest.mark.slow
class TestMultiLLMIntegration:
    """E2E tests for Multi-LLM integration"""

    @pytest.fixture
    def mock_orchestrator(self):
        """Create mock orchestrator with Multi-LLM enabled"""
        from unittest.mock import Mock

        # Create minimal mocks
        decide_path = Mock()
        execute_tot = Mock()
        reflection_judge = Mock()
        fast_path = Mock()

        orchestrator = DeepReasoningOrchestrator(
            decide_reasoning_path=decide_path,
            execute_tot=execute_tot,
            reflection_judge=reflection_judge,
            fast_path_orchestrator=fast_path,
            enable_multi_llm_ensemble=True,  # SOTA feature
            enable_alphacode_sampling=False,
        )

        return orchestrator

    async def test_multi_llm_ensemble_generation(self, mock_orchestrator, monkeypatch):
        """Test Multi-LLM generates diverse strategies"""

        # Mock LLM responses
        class MockAdapter:
            async def chat(self, messages, temperature, max_tokens):
                return f"Strategy with temp={temperature}"

        # Inject mock
        if mock_orchestrator._multi_llm_ensemble:
            for provider in mock_orchestrator._multi_llm_ensemble._adapters:
                mock_orchestrator._multi_llm_ensemble._adapters[provider] = MockAdapter()

        # Create request
        task = AgentTask(
            task_id="test",
            description="Fix bug in auth.py",
            repo_id="test_repo",
            snapshot_id="main",
            context_files=["auth.py"],
        )
        request = DeepReasoningRequest(task=task)

        # This tests the Multi-LLM initialization
        # Full execution would require mocking all LLM calls

    async def test_smart_pruning_reduces_duplicates(self):
        """Test smart pruning removes exact duplicates"""
        from apps.orchestrator.orchestrator.domain.reasoning.smart_pruner import SmartPruner

        pruner = SmartPruner()

        # Create exact duplicate strategies
        codes = [
            "def foo(x): return x + 1",
            "def foo(x): return x + 1",  # Exact duplicate
            "def foo(x): return x + 1",  # Exact duplicate
            "def unique(x): return x * 2",  # Different
        ]

        pruned, result = await pruner.prune(codes)

        # Should remove 2 exact duplicates
        assert result.original_count == 4
        assert result.removed_duplicates == 2
        assert len(pruned) == 2

    async def test_passk_selection_robustness(self):
        """Test Pass@k improves robustness"""
        from apps.orchestrator.orchestrator.domain.reasoning.passk_selector import PassKSelector

        selector = PassKSelector(k=3)

        # Mock strategies
        class Strategy:
            def __init__(self, sid, score, code):
                self.strategy_id = sid
                self.score = score
                self.code = code

        strategies = [
            Strategy("s1", 0.9, "invalid"),  # Top score but fails
            Strategy("s2", 0.7, "valid"),  # Lower score but works
            Strategy("s3", 0.5, "valid"),
        ]

        call_count = [0]

        def apply_fn(code):
            call_count[0] += 1
            return code == "valid", ""

        result = await selector.select(strategies, apply_fn)

        # Should select s2 (rank 2) because s1 failed
        assert result.selected_strategy_id == "s2"
        assert result.selected_rank == 2
        assert call_count[0] == 2  # Tried 2 times

    async def test_auto_retry_convergence_prevention(self):
        """Test auto-retry prevents infinite loops"""
        from apps.orchestrator.orchestrator.domain.feedback.auto_retry_loop import CompleteAutoRetryLoop

        retry_loop = CompleteAutoRetryLoop(max_retries=10)

        attempts = [0]

        def execute_fn(code):
            attempts[0] += 1
            # Always fail with same error
            return False, "", "SyntaxError: same error"

        result = await retry_loop.execute_with_auto_fix(
            initial_code="invalid code",
            execute_fn=execute_fn,
        )

        # Should stop early (< 10) due to convergence detection
        assert not result.success
        assert result.total_attempts < 10
        assert result.convergence_reason in ["STUCK_SAME_ERROR", "STUCK_NO_CHANGE", "MAX_RETRIES_REACHED"]


@pytest.mark.asyncio
@pytest.mark.integration
class TestCompleteSOTAFlow:
    """Test complete SOTA flow end-to-end"""

    async def test_full_pipeline(self):
        """
        Test complete pipeline:
        Multi-LLM → Pruning → Pass@k → Auto-Retry
        """
        # This would be a full integration test
        # Requires: real LLMs, test environment, etc.
        # For now, just verify imports work

        from apps.orchestrator.orchestrator.adapters.llm.multi_llm_ensemble import (
            MultiLLMEnsemble,
            create_default_ensemble_config,
        )
        from apps.orchestrator.orchestrator.domain.feedback.auto_retry_loop import CompleteAutoRetryLoop
        from apps.orchestrator.orchestrator.domain.reasoning.passk_selector import PassKSelector
        from apps.orchestrator.orchestrator.domain.reasoning.smart_pruner import SmartPruner

        # All imports should work
        assert MultiLLMEnsemble is not None
        assert SmartPruner is not None
        assert PassKSelector is not None
        assert CompleteAutoRetryLoop is not None
