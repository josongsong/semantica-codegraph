"""
Multi-Agent Debate

여러 에이전트가 토론하여 최선의 답을 도출.
"""

from .agent_roles import AgentRole, DebateAgent
from .consensus_builder import ConsensusBuilder
from .debate_models import DebateConfig, DebateResult, DebateRound, Position
from .debate_orchestrator import DebateOrchestrator

# Alias for backward compatibility
DebateEngine = DebateOrchestrator
DebatePosition = Position  # Alias

__all__ = [
    "AgentRole",
    "DebateAgent",
    "ConsensusBuilder",
    "DebateConfig",
    "DebateResult",
    "DebateRound",
    "Position",
    "DebateOrchestrator",
    "DebateEngine",  # Alias
    "DebatePosition",  # Alias
]
