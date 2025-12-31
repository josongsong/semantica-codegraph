"""
Strategy Factory 테스트
"""

import pytest

from apps.orchestrator.orchestrator.shared.reasoning import (
    ReasoningStrategy,
    StrategyFactory,
    get_strategy_factory,
)


class TestStrategyFactory:
    """StrategyFactory 테스트"""

    def test_singleton(self):
        """싱글톤 보장"""
        f1 = get_strategy_factory()
        f2 = get_strategy_factory()
        assert f1 is f2

    def test_list_strategies(self):
        """전략 리스트"""
        factory = get_strategy_factory()
        strategies = factory.list_strategies()
        assert len(strategies) > 0
        assert ReasoningStrategy.BEAM_SEARCH in strategies

    def test_get_beam_search(self):
        """Beam Search 생성"""
        factory = get_strategy_factory()
        engine = factory.get_strategy(ReasoningStrategy.BEAM_SEARCH)
        assert engine is not None

    def test_get_o1(self):
        """o1 생성"""
        factory = get_strategy_factory()
        engine = factory.get_strategy(ReasoningStrategy.O1)
        assert engine is not None

    def test_get_constitutional(self):
        """Constitutional AI 생성"""
        factory = get_strategy_factory()
        checker = factory.get_strategy(ReasoningStrategy.CONSTITUTIONAL)
        assert checker is not None

    def test_unknown_strategy_raises_error(self):
        """알 수 없는 전략 = 에러"""
        factory = get_strategy_factory()
        with pytest.raises(ValueError, match="Unknown strategy"):
            factory.get_strategy("nonexistent")  # type: ignore


class TestReasoningStrategy:
    """ReasoningStrategy Enum 테스트"""

    def test_all_strategies_exist(self):
        """모든 전략 존재"""
        strategies = [
            ReasoningStrategy.BEAM_SEARCH,
            ReasoningStrategy.ALPHACODE,
            ReasoningStrategy.O1,
            ReasoningStrategy.R1,
            ReasoningStrategy.TEST_TIME_COMPUTE,
            ReasoningStrategy.DEBATE,
            ReasoningStrategy.CRITIC,
            ReasoningStrategy.CONSTITUTIONAL,
        ]
        assert all(isinstance(s, ReasoningStrategy) for s in strategies)
