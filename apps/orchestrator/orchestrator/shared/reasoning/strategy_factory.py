"""
Reasoning Strategy Factory

추론 전략을 선택하고 실행하는 팩토리.
"""

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ReasoningStrategy(str, Enum):
    """추론 전략"""

    # 기존
    LATS = "lats"
    TOT = "tot"
    REFLECTION = "reflection"

    # 신규
    BEAM_SEARCH = "beam_search"
    ALPHACODE = "alphacode"
    O1 = "o1"
    R1 = "r1"
    TEST_TIME_COMPUTE = "ttc"
    DEBATE = "debate"
    CRITIC = "critic"
    CONSTITUTIONAL = "constitutional"


class StrategyFactory:
    """전략 팩토리"""

    def __init__(self):
        self._strategies = {}
        self._initialize_strategies()

    def _initialize_strategies(self) -> None:
        """전략 초기화"""
        try:
            # Beam Search
            from .beam import BeamConfig, BeamSearchEngine

            self._strategies[ReasoningStrategy.BEAM_SEARCH] = {
                "engine": BeamSearchEngine,
                "config": BeamConfig,
            }

            # AlphaCode Sampling
            from .sampling import AlphaCodeConfig, AlphaCodeSampler

            self._strategies[ReasoningStrategy.ALPHACODE] = {
                "engine": AlphaCodeSampler,
                "config": AlphaCodeConfig,
            }

            # o1/r1 Deep Reasoning
            from .deep import DeepReasoningConfig, O1Engine, R1Engine

            self._strategies[ReasoningStrategy.O1] = {
                "engine": O1Engine,
                "config": DeepReasoningConfig,
            }
            self._strategies[ReasoningStrategy.R1] = {
                "engine": R1Engine,
                "config": DeepReasoningConfig,
            }

            # Test-Time Compute
            from .ttc import ComputeAllocator, TTCConfig

            self._strategies[ReasoningStrategy.TEST_TIME_COMPUTE] = {
                "engine": ComputeAllocator,
                "config": TTCConfig,
            }

            # Multi-Agent Debate
            from .debate import DebateConfig, DebateOrchestrator

            self._strategies[ReasoningStrategy.DEBATE] = {
                "engine": DebateOrchestrator,
                "config": DebateConfig,
            }

            # Critic Model
            from .critic import CriticConfig, CriticModel

            self._strategies[ReasoningStrategy.CRITIC] = {
                "engine": CriticModel,
                "config": CriticConfig,
            }

            # Constitutional AI
            from .constitutional import Constitution, SafetyChecker

            self._strategies[ReasoningStrategy.CONSTITUTIONAL] = {
                "engine": SafetyChecker,
                "config": None,  # Constitution을 직접 전달
            }

            logger.info(f"Initialized {len(self._strategies)} reasoning strategies")

        except ImportError as e:
            logger.warning(f"Failed to import some strategies: {e}")

    def get_strategy(self, strategy: ReasoningStrategy, config: Any = None) -> Any:
        """
        전략 인스턴스 가져오기

        Args:
            strategy: 전략
            config: 설정 (선택)

        Returns:
            전략 인스턴스
        """
        if strategy not in self._strategies:
            raise ValueError(f"Unknown strategy: {strategy}")

        strategy_info = self._strategies[strategy]
        engine_class = strategy_info["engine"]
        config_class = strategy_info["config"]

        # 설정 생성
        if config is None and config_class is not None:
            config = config_class()

        # 엔진 생성
        if config is not None:
            return engine_class(config)
        else:
            return engine_class()

    def list_strategies(self) -> list[ReasoningStrategy]:
        """
        사용 가능한 전략 리스트

        Returns:
            전략 리스트
        """
        return list(self._strategies.keys())


# Singleton
_factory_instance = None


def get_strategy_factory() -> StrategyFactory:
    """전략 팩토리 싱글톤 가져오기"""
    global _factory_instance
    if _factory_instance is None:
        _factory_instance = StrategyFactory()
    return _factory_instance
