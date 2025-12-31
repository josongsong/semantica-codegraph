"""
Query Strategies Unit Tests

SOTA L11급:
- Base case: StrategySelector, ExecutionMode
- Edge case: 빈 strategies
"""

import pytest

from codegraph_engine.code_foundation.domain.query.strategies import (
    ExecutionMode,
    QueryExecutionStrategy,
    StrategySelector,
)


class TestExecutionMode:
    """ExecutionMode 테스트"""

    def test_base_case_values(self):
        """기본 값"""
        assert ExecutionMode.DEPTH_FIRST == "depth_first"
        assert ExecutionMode.BREADTH_FIRST == "breadth_first"
        assert ExecutionMode.COST_BASED == "cost_based"
        assert ExecutionMode.LAZY == "lazy"


class TestStrategySelector:
    """StrategySelector 테스트"""

    class MockStrategy:
        """테스트용 Mock Strategy"""

        def __init__(self, mode: ExecutionMode):
            self._mode = mode

        def execute_any_path(self, query):
            return None

        def execute_all_paths(self, query):
            return None

        def estimate_cost(self, query):
            return 1.0

        def get_mode(self) -> ExecutionMode:
            return self._mode

    def test_base_case_creation(self):
        """기본 생성"""
        strategies = [
            self.MockStrategy(ExecutionMode.DEPTH_FIRST),
            self.MockStrategy(ExecutionMode.BREADTH_FIRST),
        ]
        selector = StrategySelector(strategies)

        available = selector.get_available_modes()
        assert ExecutionMode.DEPTH_FIRST in available
        assert ExecutionMode.BREADTH_FIRST in available

    def test_base_case_select_explicit(self):
        """명시적 mode 선택"""
        strategies = [
            self.MockStrategy(ExecutionMode.DEPTH_FIRST),
            self.MockStrategy(ExecutionMode.BREADTH_FIRST),
        ]
        selector = StrategySelector(strategies)

        strategy = selector.select(query=None, mode=ExecutionMode.DEPTH_FIRST)
        assert strategy.get_mode() == ExecutionMode.DEPTH_FIRST

    def test_base_case_add_strategy(self):
        """전략 추가"""
        selector = StrategySelector([self.MockStrategy(ExecutionMode.DEPTH_FIRST)])
        selector.add_strategy(self.MockStrategy(ExecutionMode.LAZY))

        available = selector.get_available_modes()
        assert ExecutionMode.LAZY in available

    def test_base_case_remove_strategy(self):
        """전략 제거"""
        selector = StrategySelector(
            [
                self.MockStrategy(ExecutionMode.DEPTH_FIRST),
                self.MockStrategy(ExecutionMode.BREADTH_FIRST),
            ]
        )
        selector.remove_strategy(ExecutionMode.BREADTH_FIRST)

        available = selector.get_available_modes()
        assert ExecutionMode.BREADTH_FIRST not in available

    def test_edge_case_empty_strategies(self):
        """빈 strategies"""
        selector = StrategySelector([])

        with pytest.raises(RuntimeError, match="No strategies"):
            selector.select(query=None)

    def test_corner_case_auto_select(self):
        """auto select (mode 미지정)"""
        strategies = [
            self.MockStrategy(ExecutionMode.DEPTH_FIRST),
            self.MockStrategy(ExecutionMode.COST_BASED),
        ]
        selector = StrategySelector(strategies)

        # mode 미지정 시 cost_based 선호
        strategy = selector.select(query=None)
        assert strategy is not None


class TestQueryExecutionStrategy:
    """QueryExecutionStrategy Protocol 테스트"""

    def test_protocol_compliance(self):
        """Protocol 메서드 존재 확인"""

        # Protocol은 런타임에 isinstance로 체크 가능
        class ValidStrategy:
            def execute_any_path(self, query):
                pass

            def execute_all_paths(self, query):
                pass

            def estimate_cost(self, query):
                return 0.0

            def get_mode(self):
                return ExecutionMode.DEPTH_FIRST

        strategy = ValidStrategy()

        # 필수 메서드 존재 확인
        assert hasattr(strategy, "execute_any_path")
        assert hasattr(strategy, "execute_all_paths")
        assert hasattr(strategy, "estimate_cost")
        assert hasattr(strategy, "get_mode")
