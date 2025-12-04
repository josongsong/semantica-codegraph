"""
Agent Layer

LLM-powered code agent with FSM-based mode architecture.

Components:
- types: Core type definitions (AgentMode, Task, Result, ModeContext)
- fsm: Finite State Machine for mode transitions
- modes: Specialized mode implementations
- orchestrator: High-level agent orchestration and workflow management
- tools: Tool-based interface for code operations
- llm_helper: LLM integration utilities
- observability: Metrics, logging, and tracing
- streaming: Async streaming executor for real-time output
- conversation: Multi-turn context management with compression
- tool_executor: Parallel tool execution with dependencies
- approval: Human-in-the-loop approval system
"""

from typing import TYPE_CHECKING

from src.contexts.agent_automation.infrastructure.types import (
    AgentMode,
    ApprovalLevel,
    Change,
    ModeContext,
    Result,
    Task,
)

if TYPE_CHECKING:
    from src.contexts.agent_automation.infrastructure.approval import ApprovalManager, ApprovalRequest
    from src.contexts.agent_automation.infrastructure.conversation import ConversationManager, Message
    from src.contexts.agent_automation.infrastructure.fsm import AgentFSM, ModeHandler
    from src.contexts.agent_automation.infrastructure.llm_helper import LLMHelper
    from src.contexts.agent_automation.infrastructure.observability import AgentMetrics, FSMObserver
    from src.contexts.agent_automation.infrastructure.orchestrator import AgentOrchestrator, ChangeApplicator
    from src.contexts.agent_automation.infrastructure.streaming import StreamEvent, StreamingExecutor
    from src.contexts.agent_automation.infrastructure.tool_executor import ParallelToolExecutor, ToolCall, ToolChain

__version__ = "0.3.0"


def __getattr__(name: str):
    """Lazy import for heavy classes."""
    if name == "AgentFSM":
        from src.contexts.agent_automation.infrastructure.fsm import AgentFSM

        return AgentFSM
    if name == "ModeHandler":
        from src.contexts.agent_automation.infrastructure.fsm import ModeHandler

        return ModeHandler
    if name == "AgentOrchestrator":
        from src.contexts.agent_automation.infrastructure.orchestrator import AgentOrchestrator

        return AgentOrchestrator
    if name == "ChangeApplicator":
        from src.contexts.agent_automation.infrastructure.orchestrator import ChangeApplicator

        return ChangeApplicator
    if name == "LLMHelper":
        from src.contexts.agent_automation.infrastructure.llm_helper import LLMHelper

        return LLMHelper
    if name == "FSMObserver":
        from src.contexts.agent_automation.infrastructure.observability import FSMObserver

        return FSMObserver
    if name == "AgentMetrics":
        from src.contexts.agent_automation.infrastructure.observability import AgentMetrics

        return AgentMetrics
    if name == "create_observed_fsm":
        from src.contexts.agent_automation.infrastructure.observability import create_observed_fsm

        return create_observed_fsm
    # New streaming/execution components
    if name == "StreamingExecutor":
        from src.contexts.agent_automation.infrastructure.streaming import StreamingExecutor

        return StreamingExecutor
    if name == "StreamEvent":
        from src.contexts.agent_automation.infrastructure.streaming import StreamEvent

        return StreamEvent
    if name == "ConversationManager":
        from src.contexts.agent_automation.infrastructure.conversation import ConversationManager

        return ConversationManager
    if name == "Message":
        from src.contexts.agent_automation.infrastructure.conversation import Message

        return Message
    if name == "ParallelToolExecutor":
        from src.contexts.agent_automation.infrastructure.tool_executor import ParallelToolExecutor

        return ParallelToolExecutor
    if name == "ToolCall":
        from src.contexts.agent_automation.infrastructure.tool_executor import ToolCall

        return ToolCall
    if name == "ToolChain":
        from src.contexts.agent_automation.infrastructure.tool_executor import ToolChain

        return ToolChain
    if name == "ApprovalManager":
        from src.contexts.agent_automation.infrastructure.approval import ApprovalManager

        return ApprovalManager
    if name == "ApprovalRequest":
        from src.contexts.agent_automation.infrastructure.approval import ApprovalRequest

        return ApprovalRequest
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def cli_approval(*args, **kwargs):
    """Lazy import for cli_approval function."""
    from src.contexts.agent_automation.infrastructure.orchestrator import cli_approval as _cli_approval

    return _cli_approval(*args, **kwargs)


__all__ = [
    # FSM & Orchestrator (heavy - lazy import via TYPE_CHECKING)
    "AgentFSM",
    "AgentOrchestrator",
    "ChangeApplicator",
    "ModeHandler",
    # Types (lightweight)
    "AgentMode",
    "ApprovalLevel",
    "Change",
    "ModeContext",
    "Result",
    "Task",
    # LLM & Observability
    "LLMHelper",
    "FSMObserver",
    "AgentMetrics",
    "create_observed_fsm",
    # Streaming & Execution
    "StreamingExecutor",
    "StreamEvent",
    "ConversationManager",
    "Message",
    "ParallelToolExecutor",
    "ToolCall",
    "ToolChain",
    # Approval
    "ApprovalManager",
    "ApprovalRequest",
    # Functions (lazy import)
    "cli_approval",
]
