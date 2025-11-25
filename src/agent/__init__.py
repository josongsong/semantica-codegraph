"""
Agent Layer

LLM-powered code agent with FSM-based mode architecture.

Components:
- types: Core type definitions (AgentMode, Task, Result, ModeContext)
- fsm: Finite State Machine for mode transitions
- modes: Specialized mode implementations
- orchestrator: High-level agent orchestration and workflow management
"""

from src.agent.fsm import AgentFSM, ModeHandler
from src.agent.orchestrator import AgentOrchestrator, ChangeApplicator, cli_approval
from src.agent.types import AgentMode, ApprovalLevel, Change, ModeContext, Result, Task

__version__ = "0.2.0"

__all__ = [
    "AgentFSM",
    "AgentMode",
    "AgentOrchestrator",
    "ApprovalLevel",
    "Change",
    "ChangeApplicator",
    "ModeContext",
    "ModeHandler",
    "Result",
    "Task",
    "cli_approval",
]
