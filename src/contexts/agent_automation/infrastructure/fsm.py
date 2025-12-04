"""
Agent FSM (Finite State Machine)

Manages agent mode transitions based on triggers and context.

Architecture:
- AgentFSM: Core state machine engine
- ModeHandler: Protocol for mode implementations
- Transition: Rule-based transition definition
- ModeTransitionRules: Centralized transition rules with priority/condition support
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task
from src.contexts.retrieval_search.infrastructure.intent import IntentKind, RuleBasedClassifier

logger = get_logger(__name__)
# Intent → AgentMode mapping
_INTENT_TO_MODE: dict[IntentKind, AgentMode] = {
    IntentKind.CODE_SEARCH: AgentMode.CONTEXT_NAV,
    IntentKind.SYMBOL_NAV: AgentMode.CONTEXT_NAV,
    IntentKind.CONCEPT_SEARCH: AgentMode.DESIGN,
    IntentKind.FLOW_TRACE: AgentMode.CONTEXT_NAV,
    IntentKind.REPO_OVERVIEW: AgentMode.CONTEXT_NAV,
}


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
        Transition(AgentMode.IDLE, AgentMode.AGENT_PLANNING, trigger="planning_intent", priority=10),
        Transition(AgentMode.IDLE, AgentMode.MIGRATION, trigger="migration_intent", priority=10),
        # CONTEXT_NAV → Next step
        Transition(AgentMode.CONTEXT_NAV, AgentMode.IMPLEMENTATION, trigger="target_found", priority=9),
        Transition(AgentMode.CONTEXT_NAV, AgentMode.DEBUG, trigger="bug_located", priority=9),
        Transition(AgentMode.CONTEXT_NAV, AgentMode.DESIGN, trigger="architecture_needed", priority=8),
        # DESIGN → Implementation
        Transition(AgentMode.DESIGN, AgentMode.IMPLEMENTATION, trigger="design_approved", priority=9),
        Transition(AgentMode.DESIGN, AgentMode.MULTI_FILE_EDITING, trigger="large_change_planned", priority=9),
        # IMPLEMENTATION → Verification and rejection handling
        Transition(AgentMode.IMPLEMENTATION, AgentMode.TEST, trigger="code_complete", priority=9),
        Transition(AgentMode.IMPLEMENTATION, AgentMode.DEBUG, trigger="error_occurred", priority=10),
        Transition(AgentMode.IMPLEMENTATION, AgentMode.DOCUMENTATION, trigger="doc_needed", priority=7),
        Transition(AgentMode.IMPLEMENTATION, AgentMode.QA, trigger="review_needed", priority=8),
        Transition(
            AgentMode.IMPLEMENTATION, AgentMode.CONTEXT_NAV, trigger="rejected", priority=10
        ),  # When approval rejected
        # DEBUG → Fix
        Transition(AgentMode.DEBUG, AgentMode.IMPLEMENTATION, trigger="fix_identified", priority=9),
        Transition(AgentMode.DEBUG, AgentMode.TEST, trigger="reproduce_needed", priority=8),
        Transition(AgentMode.DEBUG, AgentMode.IMPACT_ANALYSIS, trigger="impact_check_needed", priority=8),
        # DOCUMENTATION → Next step
        Transition(AgentMode.DOCUMENTATION, AgentMode.QA, trigger="docs_complete", priority=9),
        Transition(AgentMode.DOCUMENTATION, AgentMode.IMPLEMENTATION, trigger="code_update_needed", priority=8),
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
        Transition(AgentMode.MULTI_FILE_EDITING, AgentMode.IMPACT_ANALYSIS, trigger="impact_check", priority=9),
        Transition(AgentMode.MULTI_FILE_EDITING, AgentMode.TEST, trigger="changes_ready", priority=9),
        Transition(AgentMode.MULTI_FILE_EDITING, AgentMode.GIT_WORKFLOW, trigger="commit_ready", priority=8),
        # IMPACT → Action
        Transition(AgentMode.IMPACT_ANALYSIS, AgentMode.TEST, trigger="affected_tests", priority=9),
        Transition(
            AgentMode.IMPACT_ANALYSIS,
            AgentMode.IMPLEMENTATION,
            trigger="additional_fixes",
            priority=8,
        ),
        # GIT → Complete
        Transition(AgentMode.GIT_WORKFLOW, AgentMode.IDLE, trigger="committed", priority=9),
        # PLANNING → Execution modes
        Transition(AgentMode.AGENT_PLANNING, AgentMode.IMPLEMENTATION, trigger="plan_ready", priority=9),
        Transition(AgentMode.AGENT_PLANNING, AgentMode.MULTI_FILE_EDITING, trigger="complex_plan", priority=9),
        Transition(AgentMode.AGENT_PLANNING, AgentMode.MIGRATION, trigger="migration_plan", priority=8),
        # MIGRATION → Verification/Rollback
        Transition(AgentMode.MIGRATION, AgentMode.TEST, trigger="migration_ready", priority=9),
        Transition(AgentMode.MIGRATION, AgentMode.DESIGN, trigger="validation_failed", priority=10),
        Transition(AgentMode.MIGRATION, AgentMode.IMPLEMENTATION, trigger="code_update_needed", priority=8),
        Transition(AgentMode.MIGRATION, AgentMode.GIT_WORKFLOW, trigger="migration_complete", priority=9),
        # ============ Phase 3 Extended Modes ============
        # IDLE → Extended modes
        Transition(AgentMode.IDLE, AgentMode.DEPENDENCY_INTELLIGENCE, trigger="deps_intent", priority=10),
        Transition(AgentMode.IDLE, AgentMode.SPEC_COMPLIANCE, trigger="compliance_intent", priority=10),
        Transition(AgentMode.IDLE, AgentMode.VERIFICATION, trigger="verify_intent", priority=10),
        Transition(AgentMode.IDLE, AgentMode.PERFORMANCE_PROFILING, trigger="perf_intent", priority=10),
        Transition(AgentMode.IDLE, AgentMode.OPS_INFRA, trigger="infra_intent", priority=10),
        Transition(AgentMode.IDLE, AgentMode.ENVIRONMENT_REPRODUCTION, trigger="env_intent", priority=10),
        Transition(AgentMode.IDLE, AgentMode.BENCHMARK, trigger="benchmark_intent", priority=10),
        Transition(AgentMode.IDLE, AgentMode.DATA_ML_INTEGRATION, trigger="ml_intent", priority=10),
        Transition(AgentMode.IDLE, AgentMode.EXPLORATORY_RESEARCH, trigger="research_intent", priority=10),
        # DEPENDENCY_INTELLIGENCE → Next steps
        Transition(AgentMode.DEPENDENCY_INTELLIGENCE, AgentMode.IDLE, trigger="deps_healthy", priority=9),
        Transition(AgentMode.DEPENDENCY_INTELLIGENCE, AgentMode.IMPLEMENTATION, trigger="deps_issues", priority=9),
        Transition(AgentMode.DEPENDENCY_INTELLIGENCE, AgentMode.DEBUG, trigger="security_alert", priority=10),
        # SPEC_COMPLIANCE → Next steps
        Transition(AgentMode.SPEC_COMPLIANCE, AgentMode.QA, trigger="compliant", priority=9),
        Transition(AgentMode.SPEC_COMPLIANCE, AgentMode.IMPLEMENTATION, trigger="violations_found", priority=9),
        Transition(AgentMode.SPEC_COMPLIANCE, AgentMode.DEBUG, trigger="critical_violation", priority=10),
        # VERIFICATION → Next steps
        Transition(AgentMode.VERIFICATION, AgentMode.QA, trigger="verified", priority=9),
        Transition(AgentMode.VERIFICATION, AgentMode.DEBUG, trigger="verification_failed", priority=10),
        Transition(AgentMode.VERIFICATION, AgentMode.TEST, trigger="needs_tests", priority=8),
        # PERFORMANCE_PROFILING → Next steps
        Transition(AgentMode.PERFORMANCE_PROFILING, AgentMode.IDLE, trigger="perf_optimal", priority=9),
        Transition(AgentMode.PERFORMANCE_PROFILING, AgentMode.IMPLEMENTATION, trigger="perf_issues", priority=9),
        Transition(AgentMode.PERFORMANCE_PROFILING, AgentMode.REFACTOR, trigger="critical_perf", priority=10),
        # OPS_INFRA → Next steps
        Transition(AgentMode.OPS_INFRA, AgentMode.GIT_WORKFLOW, trigger="infra_ready", priority=9),
        Transition(AgentMode.OPS_INFRA, AgentMode.IMPLEMENTATION, trigger="infra_issues", priority=9),
        Transition(AgentMode.OPS_INFRA, AgentMode.DEBUG, trigger="infra_critical", priority=10),
        # ENVIRONMENT_REPRODUCTION → Next steps
        Transition(AgentMode.ENVIRONMENT_REPRODUCTION, AgentMode.IDLE, trigger="env_ready", priority=9),
        Transition(AgentMode.ENVIRONMENT_REPRODUCTION, AgentMode.IMPLEMENTATION, trigger="env_issues", priority=9),
        Transition(
            AgentMode.ENVIRONMENT_REPRODUCTION, AgentMode.DEPENDENCY_INTELLIGENCE, trigger="env_missing", priority=8
        ),
        # BENCHMARK → Next steps
        Transition(AgentMode.BENCHMARK, AgentMode.QA, trigger="benchmark_passed", priority=9),
        Transition(AgentMode.BENCHMARK, AgentMode.PERFORMANCE_PROFILING, trigger="benchmark_regression", priority=10),
        Transition(AgentMode.BENCHMARK, AgentMode.GIT_WORKFLOW, trigger="benchmark_improved", priority=8),
        # DATA_ML_INTEGRATION → Next steps
        Transition(AgentMode.DATA_ML_INTEGRATION, AgentMode.TEST, trigger="ml_ready", priority=9),
        Transition(AgentMode.DATA_ML_INTEGRATION, AgentMode.IMPLEMENTATION, trigger="ml_issues", priority=9),
        Transition(AgentMode.DATA_ML_INTEGRATION, AgentMode.VERIFICATION, trigger="data_quality", priority=8),
        # EXPLORATORY_RESEARCH → Next steps
        Transition(AgentMode.EXPLORATORY_RESEARCH, AgentMode.IDLE, trigger="research_complete", priority=9),
        Transition(AgentMode.EXPLORATORY_RESEARCH, AgentMode.CONTEXT_NAV, trigger="needs_deeper_analysis", priority=8),
        Transition(AgentMode.EXPLORATORY_RESEARCH, AgentMode.DEBUG, trigger="found_issues", priority=9),
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
    def get_best_transition(cls, current_mode: AgentMode, trigger: str, context: dict) -> Transition | None:
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
    Integrates with memory system for context recall and learning.
    """

    def __init__(self, memory_system=None, project_id: str = "default"):
        """
        Initialize FSM.

        Args:
            memory_system: Optional ProductionMemorySystem for memory recall/storage
            project_id: Project ID for memory operations
        """
        self.current_mode = AgentMode.IDLE
        self.context = ModeContext()
        self.handlers: dict[AgentMode, ModeHandler] = {}
        self.transition_history: list[tuple[AgentMode, AgentMode, str]] = []
        self.memory_system = memory_system
        self.project_id = project_id
        self._working_memory = None

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

    async def execute(self, task: Task, enable_reflection: bool = True) -> Result:
        """
        Execute current mode with given task.

        Args:
            task: Task to execute
            enable_reflection: Enable reflection loop (default: True)

        Returns:
            Result from mode execution

        Raises:
            ValueError: If no handler registered for current mode
        """
        handler = self.handlers.get(self.current_mode)
        if not handler:
            raise ValueError(f"No handler registered for mode: {self.current_mode.value}")

        logger.info(f"Executing mode {self.current_mode.value} with task: {task.query[:50]}...")

        # Recall relevant memories before execution
        await self._recall_memories(task)

        # Record task start in working memory
        self._record_task_start(task)

        # Execute mode
        result = await handler.execute(task, self.context)

        # Reflection loop (if enabled)
        if enable_reflection and self._should_reflect(result):
            result = await self._reflection_loop(result, task, handler)

        # Record execution result
        self._record_result(result)

        # Auto-transition based on trigger
        if result.trigger:
            await self._auto_transition(result.trigger, task)

        return result

    async def _recall_memories(self, task: Task) -> None:
        """
        Recall relevant memories for the task.

        Populates context with:
        - Similar past episodes
        - Relevant patterns
        - Guidance from memory system
        """
        if not self.memory_system:
            return

        try:
            from src.contexts.session_memory.infrastructure.models import TaskType

            # Determine task type from mode
            task_type_map = {
                AgentMode.DEBUG: TaskType.DEBUG,
                AgentMode.IMPLEMENTATION: TaskType.IMPLEMENTATION,
                AgentMode.REFACTOR: TaskType.REFACTOR,
                AgentMode.TEST: TaskType.TEST,
                AgentMode.DESIGN: TaskType.FEATURE,
                AgentMode.QA: TaskType.REVIEW,
            }
            task_type = task_type_map.get(self.current_mode)

            # Recall memories
            memories = await self.memory_system.recall(
                query=task.query,
                project_id=self.project_id,
                task_type=task_type,
                include_episodes=True,
                include_facts=True,
                include_patterns=True,
                limit=5,
            )

            # Set memories in context
            self.context.set_memories(memories)

            # Log guidance if available
            if guidance_summary := self.context.get_guidance_summary():
                logger.info(f"Memory guidance:\n{guidance_summary}")

        except Exception as e:
            logger.warning(f"Failed to recall memories: {e}")

    def _record_task_start(self, task: Task) -> None:
        """Record task start in working memory."""
        if not self.memory_system:
            return

        try:
            # Create working memory if not exists
            if not self._working_memory:
                self._working_memory = self.memory_system.create_working_memory()

            # Record task
            self._working_memory.set_task(task.query, self.current_mode.value)
            self.context.current_task = task.query

        except Exception as e:
            logger.warning(f"Failed to record task start: {e}")

    def _record_result(self, result: Result) -> None:
        """Record execution result in working memory."""
        if not self._working_memory:
            return

        try:
            # Record action
            self._working_memory.record_action(
                action_type=result.mode.value,
                tool_name=result.mode.value,
                result={
                    "trigger": result.trigger,
                    "requires_approval": result.requires_approval,
                    "success": result.trigger not in ("error_occurred", "test_failed"),
                },
            )

            # Record any errors
            if result.trigger == "error_occurred":
                self._working_memory.record_error(
                    error_type="execution_error",
                    message=result.explanation,
                )

        except Exception as e:
            logger.warning(f"Failed to record result: {e}")

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
        return [(from_m.value, to_m.value, trigger) for from_m, to_m, trigger in self.transition_history]

    def get_available_transitions(self) -> list[Transition]:
        """Get available transitions from current mode."""
        return ModeTransitionRules.get_transitions_from(self.current_mode)

    def suggest_next_mode(self, user_query: str) -> AgentMode:
        """
        Suggest next mode based on user query using intent classifier.

        Uses RuleBasedClassifier from retriever/intent for intent detection,
        then maps intent to appropriate AgentMode.

        Args:
            user_query: User's natural language query

        Returns:
            Suggested next mode
        """
        # Use intent classifier
        classifier = RuleBasedClassifier()
        intent = classifier.classify(user_query)

        # Map intent to mode (high confidence threshold)
        if intent.confidence >= 0.5:
            if mode := _INTENT_TO_MODE.get(intent.kind):
                logger.debug(f"Intent classified: {intent.kind.value} -> {mode.value} (conf={intent.confidence:.2f})")
                return mode

        # Fallback: Agent-specific keyword matching for modes not covered by intent
        query_lower = user_query.lower()

        if "테스트" in user_query or "test" in query_lower:
            return AgentMode.TEST
        elif "리뷰" in user_query or "review" in query_lower or "qa" in query_lower:
            return AgentMode.QA
        elif "리팩토링" in user_query or "refactor" in query_lower:
            return AgentMode.REFACTOR
        elif "구현" in user_query or "implement" in query_lower or "add" in query_lower:
            return AgentMode.IMPLEMENTATION
        elif "버그" in user_query or "bug" in query_lower or "error" in query_lower or "fix" in query_lower:
            return AgentMode.DEBUG
        elif "마이그레이션" in user_query or "migration" in query_lower:
            return AgentMode.MIGRATION

        # Default to intent-based mode if available
        if mode := _INTENT_TO_MODE.get(intent.kind):
            return mode

        return AgentMode.IDLE

    def reset(self) -> None:
        """Reset FSM to initial state"""
        self.current_mode = AgentMode.IDLE
        self.context = ModeContext()
        self.transition_history.clear()
        self._working_memory = None
        logger.info("FSM reset to IDLE state")

    async def end_session(self, success: bool = True) -> str | None:
        """
        End session and consolidate working memory to long-term storage.

        Call this when a task/session completes to save learnings.

        Args:
            success: Whether the session completed successfully

        Returns:
            Episode ID if saved, None otherwise
        """
        if not self.memory_system or not self._working_memory:
            return None

        try:
            # Mark completion status
            if success:
                self._working_memory.mark_success()
            else:
                self._working_memory.mark_failure()

            # Add any session facts from context
            for fact in self.context.session_facts:
                await self.memory_system.remember(
                    fact=fact,
                    project_id=self.project_id,
                    source="session",
                )

            # Consolidate to long-term memory
            episode_id = await self.memory_system.consolidate_session(
                working_memory=self._working_memory,
                project_id=self.project_id,
            )

            logger.info(f"Session consolidated: {episode_id}")

            # Reset working memory
            self._working_memory = None

            return episode_id

        except Exception as e:
            logger.error(f"Failed to consolidate session: {e}")
            return None

    async def remember_fact(self, fact: str) -> None:
        """
        Store a fact for this session and future recall.

        Args:
            fact: Fact to remember (e.g., "User prefers TDD approach")
        """
        # Add to session context
        self.context.add_fact(fact)

        # Store in memory system immediately
        if self.memory_system:
            try:
                await self.memory_system.remember(
                    fact=fact,
                    project_id=self.project_id,
                    source="user",
                )
            except Exception as e:
                logger.warning(f"Failed to store fact: {e}")

    def _should_reflect(self, result: Result) -> bool:
        """
        Reflection이 필요한지 판단.

        Args:
            result: 실행 결과

        Returns:
            Reflection 필요 여부
        """
        # 특정 모드에서만 reflection 수행
        reflection_modes = {
            AgentMode.IMPLEMENTATION,
            AgentMode.DEBUG,
            AgentMode.REFACTOR,
            AgentMode.TEST,
        }

        if self.current_mode not in reflection_modes:
            return False

        # 에러가 있으면 reflection
        if self.context.errors:
            return True

        # Pending changes가 많으면 reflection
        if len(self.context.pending_changes) > 10:
            return True

        # 기본적으로 reflection 수행
        return True

    async def _reflection_loop(
        self,
        result: Result,
        task: Task,
        handler,
    ) -> Result:
        """
        Reflection loop 실행.

        Args:
            result: 원본 결과
            task: 실행한 태스크
            handler: Mode handler

        Returns:
            개선된 결과 (또는 원본)
        """
        try:
            from src.contexts.agent_automation.infrastructure.reflection import ReflectionEngine

            # Reflection engine 생성 (lazy)
            if not hasattr(self, "_reflection_engine"):
                self._reflection_engine = ReflectionEngine(
                    llm_client=None,  # TODO: LLM client 주입
                    quality_threshold=0.7,
                    max_iterations=3,
                )

            # Reflection 수행
            reflection = await self._reflection_engine.reflect(
                result=result,
                task=task,
                context=self.context,
            )

            logger.info(
                f"Reflection: score={reflection.quality_score:.2f}, needs_improvement={reflection.needs_improvement}"
            )

            # 개선 필요 시 1회만 재시도 (무한 루프 방지)
            if reflection.needs_improvement and reflection.quality_score < 0.5:
                logger.info("Low quality detected, retrying with feedback")

                # Feedback 추가
                task.context["reflection_feedback"] = {
                    "issues": reflection.issues,
                    "suggestions": reflection.suggestions,
                }

                # 재실행
                improved_result = await handler.execute(task, self.context)

                # 메타데이터 추가
                improved_result.metadata["reflection_iteration"] = 2
                improved_result.metadata["original_score"] = reflection.quality_score

                return improved_result

            # 품질 기준 만족 시 원본 반환
            result.metadata["reflection_score"] = reflection.quality_score
            result.metadata["reflection_performed"] = True

            return result

        except Exception as e:
            logger.warning(f"Reflection loop failed: {e}")
            return result  # Fallback to original
