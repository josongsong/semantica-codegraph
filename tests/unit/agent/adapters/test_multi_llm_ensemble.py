"""
Tests for Multi-LLM Ensemble Generator

Tests TRAE-style multi-provider strategy generation
"""

import pytest

from apps.orchestrator.orchestrator.adapters.llm.multi_llm_ensemble import (
    EnsembleConfig,
    LLMConfig,
    MultiLLMEnsemble,
    create_default_ensemble_config,
    create_fast_ensemble_config,
)


class TestEnsembleConfig:
    """Test ensemble configuration"""

    def test_total_strategies_calculation(self):
        """Test total strategies calculation"""
        config = EnsembleConfig(
            llm_configs=[
                LLMConfig(provider="openai", model="gpt-4o-mini", enabled=True),
                LLMConfig(provider="anthropic", model="claude-3.5-sonnet", enabled=True),
            ],
            temperatures=[0.2, 0.6, 1.0],
            samples_per_config=3,
        )

        # 2 LLMs × 3 temps × 3 samples = 18
        assert config.total_strategies() == 18

    def test_disabled_llm_not_counted(self):
        """Test disabled LLMs are not counted"""
        config = EnsembleConfig(
            llm_configs=[
                LLMConfig(provider="openai", model="gpt-4o-mini", enabled=True),
                LLMConfig(provider="anthropic", model="claude", enabled=False),  # Disabled
            ],
            temperatures=[0.2, 0.6],
            samples_per_config=2,
        )

        # 1 LLM × 2 temps × 2 samples = 4
        assert config.total_strategies() == 4


class TestDefaultConfigs:
    """Test default configuration factories"""

    def test_default_config(self):
        """Test default ensemble config"""
        config = create_default_ensemble_config()

        assert len(config.llm_configs) == 2  # OpenAI + Anthropic
        assert config.temperatures == [0.2, 0.6, 1.0]
        assert config.samples_per_config == 3
        assert config.total_strategies() == 18

    def test_fast_config(self):
        """Test fast ensemble config"""
        config = create_fast_ensemble_config()

        assert len(config.llm_configs) == 2
        assert config.temperatures == [0.3, 0.8]
        assert config.samples_per_config == 2
        assert config.total_strategies() == 8  # 2 × 2 × 2


@pytest.mark.asyncio
class TestMultiLLMEnsemble:
    """Test Multi-LLM Ensemble generator"""

    @pytest.fixture
    def mock_config(self):
        """Create mock config for testing"""
        return EnsembleConfig(
            llm_configs=[
                LLMConfig(provider="openai", model="gpt-4o-mini", enabled=True),
            ],
            temperatures=[0.5],
            samples_per_config=2,
            max_parallel=2,
        )

    async def test_initialization(self, mock_config):
        """Test ensemble initialization"""
        ensemble = MultiLLMEnsemble(mock_config)

        assert ensemble.config == mock_config
        # Adapters should be initialized (if API keys available)

    async def test_generate_diverse_strategies(self, mock_config, monkeypatch):
        """Test diverse strategy generation"""

        # Mock LiteLLM adapter
        class MockAdapter:
            async def chat(self, messages, temperature, max_tokens):
                return f"Strategy with temp={temperature}"

        ensemble = MultiLLMEnsemble(mock_config)
        ensemble._adapters["openai"] = MockAdapter()

        # Generate
        strategies = await ensemble.generate_diverse_strategies(
            prompt="Fix bug",
            context={"task": "Fix NullPointerException"},
        )

        # Should generate 1 LLM × 1 temp × 2 samples = 2 strategies
        assert len(strategies) == 2
        assert all(s.success for s in strategies)
        assert all(s.llm_provider == "openai" for s in strategies)

    async def test_parallel_generation(self, mock_config, monkeypatch):
        """Test parallel generation with semaphore"""
        import asyncio

        call_count = 0

        class MockAdapter:
            async def chat(self, messages, temperature, max_tokens):
                nonlocal call_count
                call_count += 1
                await asyncio.sleep(0.01)  # Simulate delay
                return f"Strategy {call_count}"

        ensemble = MultiLLMEnsemble(mock_config)
        ensemble._adapters["openai"] = MockAdapter()

        start = asyncio.get_event_loop().time()
        strategies = await ensemble.generate_diverse_strategies(
            prompt="Test",
            context={},
        )
        elapsed = asyncio.get_event_loop().time() - start

        # Should be parallel (< 0.02s for 2 calls with 0.01s each)
        assert elapsed < 0.03  # Parallel execution
        assert len(strategies) == 2

    async def test_max_strategies_limit(self, mock_config, monkeypatch):
        """Test max_strategies parameter"""

        class MockAdapter:
            async def chat(self, messages, temperature, max_tokens):
                return "Strategy"

        ensemble = MultiLLMEnsemble(mock_config)
        ensemble._adapters["openai"] = MockAdapter()

        # Limit to 1
        strategies = await ensemble.generate_diverse_strategies(
            prompt="Test",
            context={},
            max_strategies=1,
        )

        assert len(strategies) == 1

    async def test_error_handling(self, mock_config):
        """Test error handling in generation"""

        class FailingAdapter:
            async def chat(self, messages, temperature, max_tokens):
                raise RuntimeError("API Error")

        ensemble = MultiLLMEnsemble(mock_config)
        ensemble._adapters["openai"] = FailingAdapter()

        # Should not crash, return failed strategies
        strategies = await ensemble.generate_diverse_strategies(
            prompt="Test",
            context={},
        )

        # Should handle errors gracefully (return failed strategies)
        # Since we're catching exceptions in _generate_one, we get 2 failed strategies
        assert len(strategies) == 2
        assert all(not s.success for s in strategies)
        assert all(s.error is not None for s in strategies)
