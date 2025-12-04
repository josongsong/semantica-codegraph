"""
Agent Observability

Provides metrics, structured logging, and tracing for the agent FSM.

Features:
- Mode transition metrics
- Execution timing
- Success/failure rates
- Structured event logging
- Transition flow visualization
"""

import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.types import AgentMode

if TYPE_CHECKING:
    from src.contexts.agent_automation.infrastructure.fsm import AgentFSM
    from src.contexts.agent_automation.infrastructure.types import Result, Task

logger = get_logger(__name__)
# ============================================================
# Metrics Collection
# ============================================================


@dataclass
class ModeMetrics:
    """Metrics for a single mode."""

    execution_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_duration_ms: float = 0.0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0.0
    last_executed_at: datetime | None = None

    @property
    def avg_duration_ms(self) -> float:
        """Average execution duration."""
        if self.execution_count == 0:
            return 0.0
        return self.total_duration_ms / self.execution_count

    @property
    def success_rate(self) -> float:
        """Success rate (0-1)."""
        if self.execution_count == 0:
            return 0.0
        return self.success_count / self.execution_count


@dataclass
class TransitionMetrics:
    """Metrics for mode transitions."""

    count: int = 0
    avg_duration_ms: float = 0.0


@dataclass
class AgentMetrics:
    """Aggregated agent metrics."""

    mode_metrics: dict[AgentMode, ModeMetrics] = field(default_factory=dict)
    transition_counts: dict[tuple[AgentMode, AgentMode], int] = field(default_factory=lambda: defaultdict(int))
    total_tasks: int = 0
    total_duration_ms: float = 0.0
    started_at: datetime = field(default_factory=datetime.now)

    def record_mode_execution(
        self,
        mode: AgentMode,
        duration_ms: float,
        success: bool,
    ) -> None:
        """Record mode execution metrics."""
        if mode not in self.mode_metrics:
            self.mode_metrics[mode] = ModeMetrics()

        metrics = self.mode_metrics[mode]
        metrics.execution_count += 1
        metrics.total_duration_ms += duration_ms
        metrics.min_duration_ms = min(metrics.min_duration_ms, duration_ms)
        metrics.max_duration_ms = max(metrics.max_duration_ms, duration_ms)
        metrics.last_executed_at = datetime.now()

        if success:
            metrics.success_count += 1
        else:
            metrics.failure_count += 1

    def record_transition(self, from_mode: AgentMode, to_mode: AgentMode) -> None:
        """Record mode transition."""
        self.transition_counts[(from_mode, to_mode)] += 1

    def get_summary(self) -> dict[str, Any]:
        """Get metrics summary."""
        mode_summaries = {}
        for mode, metrics in self.mode_metrics.items():
            mode_summaries[mode.value] = {
                "executions": metrics.execution_count,
                "success_rate": f"{metrics.success_rate * 100:.1f}%",
                "avg_duration_ms": f"{metrics.avg_duration_ms:.1f}",
                "min_duration_ms": f"{metrics.min_duration_ms:.1f}"
                if metrics.min_duration_ms != float("inf")
                else "N/A",
                "max_duration_ms": f"{metrics.max_duration_ms:.1f}",
            }

        transition_summaries = {}
        for (from_m, to_m), count in self.transition_counts.items():
            key = f"{from_m.value} -> {to_m.value}"
            transition_summaries[key] = count

        return {
            "total_tasks": self.total_tasks,
            "total_duration_ms": self.total_duration_ms,
            "uptime_seconds": (datetime.now() - self.started_at).total_seconds(),
            "modes": mode_summaries,
            "transitions": transition_summaries,
        }


# ============================================================
# Structured Event Logging
# ============================================================


@dataclass
class AgentEvent:
    """Structured agent event."""

    timestamp: datetime
    event_type: str
    mode: AgentMode | None
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "mode": self.mode.value if self.mode else None,
            **self.data,
        }


class EventLogger:
    """Structured event logger for agent operations."""

    def __init__(self, max_events: int = 1000):
        """
        Initialize event logger.

        Args:
            max_events: Maximum events to keep in memory
        """
        self.events: list[AgentEvent] = []
        self.max_events = max_events
        self._callbacks: list[Callable[[AgentEvent], None]] = []

    def log(
        self,
        event_type: str,
        mode: AgentMode | None = None,
        **data,
    ) -> AgentEvent:
        """
        Log an event.

        Args:
            event_type: Type of event
            mode: Current mode
            **data: Event data

        Returns:
            Created event
        """
        event = AgentEvent(
            timestamp=datetime.now(),
            event_type=event_type,
            mode=mode,
            data=data,
        )

        self.events.append(event)

        # Trim if needed
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events :]

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.warning(f"Event callback failed: {e}")

        # Also log to standard logger
        logger.info(f"[{event_type}] mode={mode.value if mode else 'N/A'} {data}")

        return event

    def on_event(self, callback: Callable[[AgentEvent], None]) -> None:
        """Register event callback."""
        self._callbacks.append(callback)

    def get_events(
        self,
        event_type: str | None = None,
        mode: AgentMode | None = None,
        limit: int = 100,
    ) -> list[AgentEvent]:
        """
        Get filtered events.

        Args:
            event_type: Filter by event type
            mode: Filter by mode
            limit: Maximum events to return

        Returns:
            List of events
        """
        filtered = self.events

        if event_type:
            filtered = [e for e in filtered if e.event_type == event_type]

        if mode:
            filtered = [e for e in filtered if e.mode == mode]

        return filtered[-limit:]

    def clear(self) -> None:
        """Clear all events."""
        self.events.clear()


# ============================================================
# FSM Observer
# ============================================================


class FSMObserver:
    """
    Observer for FSM operations.

    Integrates metrics collection and event logging with the FSM.

    Usage:
        observer = FSMObserver()
        fsm = AgentFSM()

        # Instrument FSM
        observer.instrument(fsm)

        # ... use FSM ...

        # Get metrics
        print(observer.metrics.get_summary())
    """

    def __init__(self):
        """Initialize observer."""
        self.metrics = AgentMetrics()
        self.event_logger = EventLogger()
        self._original_methods: dict[str, Callable] = {}

    def instrument(self, fsm: "AgentFSM") -> None:  # noqa: F821
        """
        Instrument FSM with observability.

        Args:
            fsm: FSM instance to instrument
        """
        # Store original methods
        self._original_methods["transition_to"] = fsm.transition_to
        self._original_methods["execute"] = fsm.execute

        # Wrap transition_to
        original_transition_to = fsm.transition_to

        async def instrumented_transition_to(to_mode: AgentMode, trigger: str = "") -> None:
            from_mode = fsm.current_mode

            self.event_logger.log(
                "transition_start",
                mode=from_mode,
                to_mode=to_mode.value,
                trigger=trigger,
            )

            start_time = time.time()
            await original_transition_to(to_mode, trigger)
            duration_ms = (time.time() - start_time) * 1000

            self.metrics.record_transition(from_mode, to_mode)

            self.event_logger.log(
                "transition_complete",
                mode=to_mode,
                from_mode=from_mode.value,
                duration_ms=f"{duration_ms:.1f}",
            )

        fsm.transition_to = instrumented_transition_to

        # Wrap execute
        original_execute = fsm.execute

        async def instrumented_execute(task: "Task") -> "Result":  # noqa: F821
            mode = fsm.current_mode
            self.metrics.total_tasks += 1

            self.event_logger.log(
                "execution_start",
                mode=mode,
                task_query=task.query[:100],
            )

            start_time = time.time()
            success = True

            try:
                result = await original_execute(task)
                success = not result.metadata.get("error")
                return result
            except Exception:
                success = False
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                self.metrics.total_duration_ms += duration_ms
                self.metrics.record_mode_execution(mode, duration_ms, success)

                self.event_logger.log(
                    "execution_complete",
                    mode=mode,
                    success=success,
                    duration_ms=f"{duration_ms:.1f}",
                )

        fsm.execute = instrumented_execute

    def get_transition_graph(self) -> dict[str, list[tuple[str, int]]]:
        """
        Get transition graph for visualization.

        Returns:
            Dict mapping source modes to list of (target_mode, count) tuples
        """
        graph: dict[str, list[tuple[str, int]]] = defaultdict(list)

        for (from_mode, to_mode), count in self.metrics.transition_counts.items():
            graph[from_mode.value].append((to_mode.value, count))

        return dict(graph)

    def print_summary(self) -> None:
        """Print metrics summary to logger."""
        summary = self.metrics.get_summary()

        logger.info("=" * 50)
        logger.info("Agent FSM Metrics Summary")
        logger.info("=" * 50)
        logger.info(f"Total Tasks: {summary['total_tasks']}")
        logger.info(f"Total Duration: {summary['total_duration_ms']:.1f}ms")
        logger.info(f"Uptime: {summary['uptime_seconds']:.1f}s")

        logger.info("\nMode Metrics:")
        for mode, metrics in summary["modes"].items():
            logger.info(f"  {mode}:")
            logger.info(f"    Executions: {metrics['executions']}")
            logger.info(f"    Success Rate: {metrics['success_rate']}")
            logger.info(f"    Avg Duration: {metrics['avg_duration_ms']}ms")

        logger.info("\nTransitions:")
        for transition, count in summary["transitions"].items():
            logger.info(f"  {transition}: {count}")

        logger.info("=" * 50)


# ============================================================
# Convenience Functions
# ============================================================


def create_observed_fsm() -> tuple["AgentFSM", FSMObserver]:  # noqa: F821
    """
    Create FSM with observability.

    Returns:
        Tuple of (FSM, Observer)
    """
    from src.contexts.agent_automation.infrastructure.fsm import AgentFSM

    fsm = AgentFSM()
    observer = FSMObserver()
    observer.instrument(fsm)

    return fsm, observer
