"""Agent State for LangGraph."""

from typing import Any, TypedDict

from src.contexts.agent_automation.infrastructure.types import ModeContext


class AgentStateRequired(TypedDict):
    """Required fields in agent state."""

    # Input (required)
    task: str  # Original user task
    repo_id: str
    repo_path: str
    current_commit: str


class AgentState(AgentStateRequired, total=False):
    """Shared state for multi-agent workflow.

    This state is passed between nodes in the LangGraph graph
    and accumulates results from parallel agents.
    """

    # Planning
    plan: list[dict]  # List of subtasks with metadata
    parallel_allowed: bool  # Can subtasks run in parallel?
    dependency_graph: dict  # Task dependencies

    # Agent execution
    agent_results: dict[str, Any]  # Results keyed by agent/subtask ID
    context: ModeContext  # Shared FSM context
    file_locks: dict[str, Any]  # File-level locks for coordination

    # Patches
    patches: list[dict]  # Generated patches from agents
    conflicts: list[dict]  # Detected conflicts

    # Merging
    merged_patches: list[dict]  # Merged patches after conflict resolution
    merge_success: bool

    # Validation
    validation_result: dict  # Test results, lint results, etc.
    validation_passed: bool

    # Control flow
    retry_count: int
    max_retries: int
    should_retry: bool
    errors: list[str]
