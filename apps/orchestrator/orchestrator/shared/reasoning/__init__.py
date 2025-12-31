"""
Shared Reasoning Engines

범용 추론 알고리즘 (모든 agent contexts 사용):
- LATS (Language Agent Tree Search)
- ToT (Tree of Thoughts)
- Self-Reflection
- Beam Search
- AlphaCode Sampling
- o1/r1 Deep Reasoning
- Test-Time Compute
- Multi-Agent Debate
- Critic Model
- Constitutional AI

Usage:
    from apps.orchestrator.orchestrator.shared.reasoning import LATSSearchEngine
    from apps.orchestrator.orchestrator.shared.reasoning import BeamSearchEngine
    from apps.orchestrator.orchestrator.shared.reasoning import O1Engine
"""

# Re-export from submodules
from .base import (
    DynamicReasoningRouter,
    QueryFeatures,
    ReasoningDecision,
    ReasoningPath,
)
from .lats import (
    LATSNode,
    LATSSearchEngine,
    LATSSearchMetrics,
    WinningPath,
)
from .reflection import (
    ReflectionVerdict,
    SelfReflectionJudge,
)

# New strategies
from .strategy_factory import (
    ReasoningStrategy,
    StrategyFactory,
    get_strategy_factory,
)
from .tot import (
    CodeStrategy,
    ToTResult,
    ToTScoringEngine,
)

__all__ = [
    # Base
    "DynamicReasoningRouter",
    "QueryFeatures",
    "ReasoningDecision",
    "ReasoningPath",
    # LATS
    "LATSSearchEngine",
    "LATSNode",
    "LATSSearchMetrics",
    "WinningPath",
    # ToT
    "ToTScoringEngine",
    "CodeStrategy",
    "ToTResult",
    # Reflection
    "SelfReflectionJudge",
    "ReflectionVerdict",
    # Strategy Factory
    "ReasoningStrategy",
    "StrategyFactory",
    "get_strategy_factory",
]
