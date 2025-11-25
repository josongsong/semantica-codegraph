"""
Agent FSM (Finite State Machine)

Manages agent mode transitions based on triggers and context.

Architecture:
- AgentFSM: Core state machine engine
- ModeHandler: Protocol for mode implementations
- Transition: Rule-based transition definition
- ModeTransitionRules: Centralized transition rules with priority/condition support
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from src.agent.types import AgentMode, ModeContext, Result, Task

logger = logging.getLogger(__name__)


@dataclass
class Transition:
    """Mode transition rule."""

    from_mode: AgentMode
    to_mode: AgentMode
    trigger: str  # Transition trigger (intent, error, completion, etc.)
    condition: Callable[[dict], bool] | None = None  # Optional transition condition
    priority: int = 0  # Higher priority wins


class ModeTransitionRules:
    """Mode transition rules definition."""

    TRANSITIONS = [
        # IDLE → Start work
        Transition(AgentMode.IDLE, AgentMode.CONTEXT_NAV, trigger="search_intent", priority=10),
        Transition(AgentMode.IDLE, AgentMode.IMPLEMENTATION, trigger="code_intent", priority=10),
        Transition(AgentMode.IDLE, AgentMode.DEBUG, trigger="error_intent", priority=10),
        Transition(AgentMode.IDLE, AgentMode.DESIGN, trigger="design_intent", priority=10),
        # CONTEXT_NAV → Next step
        Transition(AgentMode.CONTEXT_NAV, AgentMode.IMPLEMENTATION, trigger="target_found", priority=9),
        Transition(AgentMode.CONTEXT_NAV, AgentMode.DEBUG, trigger="bug_located", priority=9),
        Transition(AgentMode.CONTEXT_NAV, AgentMode.DESIGN, trigger="architecture_needed", priority=8),
        # DESIGN → Implementation
        Transition(AgentMode.DESIGN, AgentMode.IMPLEMENTATION, trigger="design_approved", priority=9),
        Transition(
            AgentMode.DESIGN, AgentMode.MULTI_FILE_EDITING, trigger="large_change_planned", priority=9
        ),
        # IMPLEMENTATION → Verification and rejection handling
        Transition(AgentMode.IMPLEMENTATION, AgentMode.TEST, trigger="code_complete", priority=9),
        Transition(AgentMode.IMPLEMENTATION, AgentMode.DEBUG, trigger="error_occurred", priority=10),
        Transition(
            AgentMode.IMPLEMENTATION, AgentMode.DOCUMENTATION, trigger="doc_needed", priority=7
        ),
        Transition(AgentMode.IMPLEMENTATION, AgentMode.QA, trigger="review_needed", priority=8),
        Transition(
            AgentMode.IMPLEMENTATION, AgentMode.CONTEXT_NAV, trigger="rejected", priority=10
        ),  # When approval rejected
        # DEBUG → Fix
        Transition(AgentMode.DEBUG, AgentMode.IMPLEMENTATION, trigger="fix_identified", priority=9),
        Transition(AgentMode.DEBUG, AgentMode.TEST, trigger="reproduce_needed", priority=8),
        Transition(
            AgentMode.DEBUG, AgentMode.IMPACT_ANALYSIS, trigger="impact_check_needed", priority=8
        ),
        # TEST → Next step
        Transition(AgentMode.TEST, AgentMode.IMPLEMENTATION, trigger="test_failed", priority=10),
        Transition(AgentMode.TEST, AgentMode.QA, trigger="tests_passed", priority=9),
        # QA → Improvement/Complete
        Transition(AgentMode.QA, AgentMode.REFACTOR, trigger="improvement_needed", priority=8),
        Transition(AgentMode.QA, AgentMode.IMPLEMENTATION, trigger="issues_found", priority=9),
        Transition(AgentMode.QA, AgentMode.GIT_WORKFLOW, trigger="approved", priority=9),
        # REFACTOR → Verification
        Transition(AgentMode.REFACTOR, AgentMode.TEST, trigger="refactor_complete", priority=9),
        Transition(AgentMode.REFACTOR, AgentMode.MULTI_FILE_EDITING, trigger="large_refactor", priority=8),
        # MULTI_FILE → Verification/Complete
        Transition(
            AgentMode.MULTI_FILE_EDITING, AgentMode.IMPACT_ANALYSIS, trigger="impact_check", priority=9
        ),
        Transition(AgentMode.MULTI_FILE_EDITING, AgentMode.TEST, trigger="changes_ready", priority=9),
        Transition(
            AgentMode.MULTI_FILE_EDITING, AgentMode.GIT_WORKFLOW, trigger="commit_ready", priority=8
        ),
        # IMPACT → Action
        Transition(
            AgentMode.IMPACT_ANALYSIS, AgentMode.TEST, trigger="affected_tests", priority=9
        ),
        Transition(
            AgentMode.IMPACT_ANALYSIS,
            AgentMode.IMPLEMENTATION,
            trigger="additional_fixes",
            priority=8,
        ),
        # GIT → Complete
        Transition(AgentMode.GIT_WORKFLOW, AgentMode.IDLE, trigger="committed", priority=9),
        # PLANNING → Execution modes
        Transition(
            AgentMode.AGENT_PLANNING, AgentMode.IMPLEMENTATION, trigger="plan_ready", priority=9
        ),
        Transition(
            AgentMode.AGENT_PLANNING, AgentMode.MULTI_FILE_EDITING, trigger="complex_plan", priority=9
        ),
        Transition(
            AgentMode.AGENT_PLANNING, AgentMode.MIGRATION, trigger="migration_plan", priority=8
        ),
    ]

    # Indexed transition lookup for O(1) performance
    _index: dict[tuple[AgentMode, str], list[Transition]] = {}

    @classmethod
    def _build_index(cls) -> None:
        """Build transition index for fast lookup."""
        if cls._index:
            return
        index: dict[tuple[AgentMode, str], list[Transition]] = {}
        for t in cls.TRANSITIONS:
            key = (t.from_mode, t.trigger)
            index.setdefault(key, []).append(t)
        cls._index = index

    @classmethod
    def get_transitions_from(cls, mode: AgentMode) -> list[Transition]:
        """Get all possible transitions from a mode."""
        return [t for t in cls.TRANSITIONS if t.from_mode == mode]

    @classmethod
    def get_best_transition(
        cls, current_mode: AgentMode, trigger: str, context: dict
    ) -> Transition | None:
        """Get best transition for current situation."""
        cls._build_index()

        # O(1) lookup using index
        candidates = cls._index.get((current_mode, trigger), [])

        # Filter by condition
        valid = [t for t in candidates if t.condition is None or t.condition(context)]

        # Return highest priority
        if valid:
            return max(valid, key=lambda t: t.priority)

        return None


class ModeHandler(Protocol):
    """
    Protocol defining the interface for mode handlers.

    Each mode must implement these three lifecycle methods:
    - enter: Called when entering the mode
    - execute: Main mode logic
    - exit: Called when leaving the mode
    """

    async def enter(self, context: ModeContext) -> None:
        """Called when entering this mode"""
        ...

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """Execute mode logic and return result"""
        ...

    async def exit(self, context: ModeContext) -> None:
        """Called when exiting this mode"""
        ...


class AgentFSM:
    """
    Agent Finite State Machine.

    Manages mode transitions and executes mode handlers.
    """

    def __init__(self):
        self.current_mode = AgentMode.IDLE
        self.context = ModeContext()
        self.handlers: dict[AgentMode, ModeHandler] = {}
        self.transition_history: list[tuple[AgentMode, AgentMode, str]] = []

    def register(self, mode: AgentMode, handler: ModeHandler) -> None:
        """
        Register a mode handler.

        Args:
            mode: The mode this handler implements
            handler: The mode handler instance
        """
        self.handlers[mode] = handler
        logger.info(f"Registered handler for mode: {mode.value}")

    async def transition_to(self, to_mode: AgentMode, trigger: str = "") -> None:
        """
        Direct mode transition (for testing or manual control).

        Args:
            to_mode: Target mode
            trigger: Reason for transition (for logging)
        """
        if to_mode == self.current_mode:
            logger.debug(f"Already in mode {to_mode.value}, skipping transition")
            return

        logger.info(f"Transition: {self.current_mode.value} -> {to_mode.value} (trigger: {trigger})")

        # Exit current mode
        if current_handler := self.handlers.get(self.current_mode):
            await current_handler.exit(self.context)

        # Record transition
        old_mode = self.current_mode
        self.current_mode = to_mode
        self.context.mode_history.append(to_mode)
        self.transition_history.append((old_mode, to_mode, trigger))

        # Enter new mode
        if new_handler := self.handlers.get(to_mode):
            await new_handler.enter(self.context)

    async def transition(self, trigger: str, task: Task | None = None) -> bool:
        """
        Attempt mode transition based on trigger.

        Args:
            trigger: Trigger string (e.g., "target_found", "code_complete")
            task: Optional task context

        Returns:
            True if transition succeeded, False otherwise
        """
        # Check transition rules
        transition_rule = ModeTransitionRules.get_best_transition(
            current_mode=self.current_mode, trigger=trigger, context=self.context.to_dict()
        )

        if not transition_rule:
            logger.warning(f"No valid transition from {self.current_mode} with trigger '{trigger}'")
            return False

        to_mode = transition_rule.to_mode
        await self.transition_to(to_mode, trigger)
        return True

    async def execute(self, task: Task) -> Result:
        """
        Execute current mode with given task.

        Args:
            task: Task to execute

        Returns:
            Result from mode execution

        Raises:
            ValueError: If no handler registered for current mode
        """
        handler = self.handlers.get(self.current_mode)
        if not handler:
            raise ValueError(f"No handler registered for mode: {self.current_mode.value}")

        logger.info(f"Executing mode {self.current_mode.value} with task: {task.query[:50]}...")

        # Execute mode
        result = await handler.execute(task, self.context)

        # Auto-transition based on trigger
        if result.trigger:
            await self._auto_transition(result.trigger, task)

        return result

    async def _auto_transition(self, trigger: str, task: Task | None = None) -> None:
        """
        Automatically transition based on trigger using ModeTransitionRules.

        Args:
            trigger: Trigger string from result
            task: Optional task context
        """
        success = await self.transition(trigger, task)
        if not success:
            logger.debug(f"No auto-transition available for trigger: {trigger}")

    def get_transition_history(self) -> list[tuple[str, str, str]]:
        """
        Get mode transition history.

        Returns:
            List of (from_mode, to_mode, trigger) tuples
        """
        return [
            (from_m.value, to_m.value, trigger) for from_m, to_m, trigger in self.transition_history
        ]

    def get_available_transitions(self) -> list[Transition]:
        """Get available transitions from current mode."""
        return ModeTransitionRules.get_transitions_from(self.current_mode)

    def suggest_next_mode(self, user_query: str) -> AgentMode:
        """
        Suggest next mode based on user query (rule-based for now, ML later).

        Args:
            user_query: User's natural language query

        Returns:
            Suggested next mode
        """
        # TODO: Integrate intent classifier from retriever/intent
        # Current: simple rule-based
        query_lower = user_query.lower()

        if "테스트" in user_query or "test" in query_lower:
            return AgentMode.TEST
        elif "리뷰" in user_query or "review" in query_lower or "qa" in query_lower:
            return AgentMode.QA
        elif "리팩토링" in user_query or "refactor" in query_lower:
            return AgentMode.REFACTOR
        elif "찾" in user_query or "search" in query_lower or "find" in query_lower:
            return AgentMode.CONTEXT_NAV
        elif "구현" in user_query or "implement" in query_lower or "add" in query_lower:
            return AgentMode.IMPLEMENTATION
        elif "버그" in user_query or "bug" in query_lower or "error" in query_lower:
            return AgentMode.DEBUG
        elif "설계" in user_query or "design" in query_lower:
            return AgentMode.DESIGN
        elif "마이그레이션" in user_query or "migration" in query_lower:
            return AgentMode.MIGRATION

        return AgentMode.IDLE

    def reset(self) -> None:
        """Reset FSM to initial state"""
        self.current_mode = AgentMode.IDLE
        self.context = ModeContext()
        self.transition_history.clear()
        logger.info("FSM reset to IDLE state")
