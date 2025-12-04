"""
Working Memory Manager

Manages short-term memory for the current agent session:
- Current task state
- Execution history (recent steps)
- Active context (files, symbols, hypotheses)
- Recent results buffer (circular buffer for last N results)
"""

from collections import deque
from datetime import datetime
from typing import Any
from uuid import uuid4

from src.infra.observability import get_logger, record_counter, record_histogram

from .models import (
    Decision,
    Discovery,
    Episode,
    ErrorRecord,
    FileState,
    Hypothesis,
    PatchSummary,
    StepRecord,
    SymbolInfo,
    TaskStatus,
    TaskType,
    ToolUsageSummary,
)

logger = get_logger(__name__)


class CircularBuffer:
    """Circular buffer for storing recent items."""

    def __init__(self, maxlen: int = 10):
        """
        Initialize circular buffer.

        Args:
            maxlen: Maximum number of items to store
        """
        self._buffer: deque = deque(maxlen=maxlen)

    def push(self, item: Any) -> None:
        """Add item to buffer (oldest is dropped if full)."""
        self._buffer.append(item)

    def to_list(self) -> list:
        """Convert buffer to list."""
        return list(self._buffer)

    def clear(self) -> None:
        """Clear all items."""
        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)


class WorkingMemoryManager:
    """
    Manages working memory for current agent session.

    Working memory is volatile - it persists only during the current session
    and is consolidated to episodic memory when the session ends.
    """

    def __init__(self, session_id: str | None = None, max_buffer_size: int = 10):
        """
        Initialize working memory manager.

        Args:
            session_id: Session identifier (generates UUID if None)
            max_buffer_size: Maximum size for circular buffers
        """
        self.session_id = session_id or str(uuid4())
        self.max_buffer_size = max_buffer_size
        self.started_at = datetime.now()

        # Memory limits to prevent leaks
        self.max_steps = 1000  # Maximum steps to keep
        self.max_hypotheses = 50  # Maximum hypotheses
        self.max_decisions = 100  # Maximum decisions
        self.max_files = 200  # Maximum tracked files

        # Current task
        self.current_task: dict[str, Any] | None = None

        # Execution state
        self.current_plan: dict[str, Any] | None = None
        self.current_step: int = 0
        self.steps_completed: list[StepRecord] = []
        self.pending_actions: list[dict] = []

        # Active context
        self.active_files: dict[str, FileState] = {}
        self.active_symbols: dict[str, SymbolInfo] = {}
        self.hypotheses: list[Hypothesis] = []
        self.decisions: list[Decision] = []

        # Recent buffers
        self.recent_tool_results: CircularBuffer = CircularBuffer(max_buffer_size)
        self.recent_errors: CircularBuffer = CircularBuffer(max_buffer_size // 2)
        self.recent_discoveries: CircularBuffer = CircularBuffer(max_buffer_size)

        # Session statistics
        self.stats = {
            "tool_calls": 0,
            "tokens_used": 0,
            "errors_encountered": 0,
            "patches_proposed": 0,
            "patches_applied": 0,
        }

        logger.info("working_memory_initialized", session_id=self.session_id, max_buffer_size=max_buffer_size)
        record_counter("memory_sessions_total", labels={"type": "working"})

    # ============================================================
    # Task Management
    # ============================================================

    def init_task(self, task: dict[str, Any]) -> None:
        """
        Initialize a new task with type safety.

        Args:
            task: Task information (query, type, files, etc.)
        """
        # Safe TaskType conversion
        task_type_str = task.get("type", "unknown")
        try:
            task_type = TaskType(task_type_str)
        except ValueError:
            logger.warning("invalid_task_type", task_type=task_type_str, default="UNKNOWN")
            record_counter("memory_task_errors_total", labels={"error": "invalid_type"})
            task_type = TaskType.UNKNOWN

        self.current_task = {
            "id": str(uuid4()),
            "description": task.get("query", ""),
            "type": task_type,
            "status": TaskStatus.RUNNING,
            "started_at": datetime.now(),
        }
        task_preview = self.current_task["description"][:50]
        logger.info("task_initialized", task_preview=task_preview, task_type=task_type.value)
        record_counter("memory_tasks_total", labels={"type": task_type.value})

    def update_task_status(self, status: TaskStatus) -> None:
        """Update current task status."""
        if self.current_task:
            self.current_task["status"] = status
            logger.info("task_status_updated", status=status.value, task_id=self.current_task["id"])
            record_counter("memory_task_status_updates_total", labels={"status": status.value})

    # ============================================================
    # Step Recording
    # ============================================================

    def record_step(
        self, tool_name: str, tool_input: dict, tool_result: Any, success: bool = True, error: str | None = None
    ) -> str:
        """
        Record execution step.

        Args:
            tool_name: Name of tool executed
            tool_input: Input to tool
            tool_result: Tool execution result
            success: Whether step succeeded
            error: Error message if failed

        Returns:
            Step ID
        """
        step_id = str(uuid4())
        step = StepRecord(
            id=step_id,
            step_number=self.current_step + 1,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_result=tool_result,
            success=success,
            error=error,
            timestamp=datetime.now(),
        )

        self.steps_completed.append(step)
        self.current_step += 1
        self.stats["tool_calls"] += 1

        # Limit steps to prevent memory leak
        if len(self.steps_completed) > self.max_steps:
            # Keep most recent steps
            self.steps_completed = self.steps_completed[-self.max_steps :]
            logger.debug("steps_trimmed", max_steps=self.max_steps, kept=len(self.steps_completed))
            record_counter("memory_steps_trimmed_total")

        # Add to recent buffer
        self.recent_tool_results.push(tool_result)

        # Record error if failed
        if error:
            self.stats["errors_encountered"] += 1
            error_record = ErrorRecord(
                step_id=step_id, error=Exception(error), context={"tool": tool_name, "input": tool_input}
            )
            self.recent_errors.push(error_record)
            record_counter("memory_step_errors_total", labels={"tool": tool_name})

        logger.debug("step_recorded", tool_name=tool_name, success=success, step_number=self.current_step)
        record_counter("memory_steps_total", labels={"tool": tool_name, "success": str(success)})
        return step_id

    # ============================================================
    # Hypothesis Management
    # ============================================================

    def add_hypothesis(self, description: str, confidence: float, evidence: list[str] | None = None) -> str:
        """
        Add a new hypothesis with memory limits.

        Args:
            description: Hypothesis description
            confidence: Confidence level (0.0 to 1.0)
            evidence: Supporting evidence

        Returns:
            Hypothesis ID
        """
        # Check for duplicates
        for existing in self.hypotheses:
            if existing.description == description:
                # Update existing hypothesis
                existing.confidence = max(existing.confidence, confidence)
                if evidence:
                    existing.evidence.extend(evidence)
                desc_preview = description[:50]
                logger.debug(
                    "hypothesis_updated_existing", description_preview=desc_preview, confidence=existing.confidence
                )
                return existing.id

        # Limit hypothesis count to prevent memory leak
        if len(self.hypotheses) >= self.max_hypotheses:
            # Remove oldest rejected or lowest confidence hypothesis
            rejected = [h for h in self.hypotheses if h.status == "rejected"]
            if rejected:
                self.hypotheses.remove(rejected[0])
            else:
                # Remove oldest with lowest confidence
                self.hypotheses.sort(key=lambda h: (h.created_at, h.confidence))
                removed = self.hypotheses.pop(0)
                removed_preview = removed.description[:30]
                logger.debug(
                    "hypothesis_removed_for_space", removed_preview=removed_preview, confidence=removed.confidence
                )
                record_counter("memory_hypotheses_trimmed_total")

        # Create new hypothesis
        hypothesis_id = str(uuid4())
        hypothesis = Hypothesis(
            id=hypothesis_id, description=description, confidence=confidence, evidence=evidence or []
        )
        self.hypotheses.append(hypothesis)
        desc_preview = description[:50]
        logger.info(
            "hypothesis_added", description_preview=desc_preview, confidence=confidence, hypothesis_id=hypothesis_id
        )
        record_counter("memory_hypotheses_total")
        record_histogram("memory_hypothesis_confidence", confidence)
        return hypothesis_id

    def update_hypothesis(self, hypothesis_id: str, **updates) -> None:
        """
        Update hypothesis.

        Args:
            hypothesis_id: Hypothesis ID
            **updates: Fields to update
        """
        for hypothesis in self.hypotheses:
            if hypothesis.id == hypothesis_id:
                for key, value in updates.items():
                    if hasattr(hypothesis, key):
                        setattr(hypothesis, key, value)

                # Auto-promote to decision if confirmed
                if hypothesis.confidence >= 0.9 and hypothesis.status == "confirmed":
                    self._promote_to_decision(hypothesis)

                # Remove if rejected
                elif hypothesis.status == "rejected":
                    self.hypotheses.remove(hypothesis)

                logger.debug("hypothesis_updated", hypothesis_id=hypothesis_id, updates=list(updates.keys()))
                record_counter("memory_hypothesis_updates_total", labels={"status": hypothesis.status})
                break

    def _promote_to_decision(self, hypothesis: Hypothesis) -> None:
        """Promote confirmed hypothesis to decision."""
        decision = Decision(
            id=str(uuid4()),
            description=f"Confirmed: {hypothesis.description}",
            rationale=f"Hypothesis confirmed with {hypothesis.confidence:.2%} confidence",
            accepted=True,
        )
        self.decisions.append(decision)
        self.hypotheses.remove(hypothesis)
        desc_preview = hypothesis.description[:50]
        logger.info(
            "hypothesis_promoted_to_decision", description_preview=desc_preview, confidence=hypothesis.confidence
        )
        record_counter("memory_hypothesis_promotions_total")

    # ============================================================
    # Decision Recording
    # ============================================================

    def record_decision(
        self, description: str, rationale: str, alternatives: list[str] | None = None, accepted: bool = True
    ) -> str:
        """
        Record a decision with memory limits.

        Args:
            description: Decision description
            rationale: Reasoning behind decision
            alternatives: Alternative options considered
            accepted: Whether decision was accepted

        Returns:
            Decision ID
        """
        decision_id = str(uuid4())
        decision = Decision(
            id=decision_id,
            description=description,
            rationale=rationale,
            alternatives=alternatives or [],
            accepted=accepted,
            context_snapshot=self._capture_context_snapshot(),
        )
        self.decisions.append(decision)

        # Limit decision count
        if len(self.decisions) > self.max_decisions:
            self.decisions = self.decisions[-self.max_decisions :]
            logger.debug("decisions_trimmed", max_decisions=self.max_decisions, kept=len(self.decisions))
            record_counter("memory_decisions_trimmed_total")

        desc_preview = description[:50]
        logger.info("decision_recorded", description_preview=desc_preview, accepted=accepted, decision_id=decision_id)
        record_counter("memory_decisions_total", labels={"accepted": str(accepted)})
        return decision_id

    # ============================================================
    # File & Symbol Tracking
    # ============================================================

    def track_file(self, file_path: str, modified: bool = False) -> None:
        """
        Track file access with memory limits.

        Args:
            file_path: Path to file
            modified: Whether file was modified
        """
        if file_path in self.active_files:
            state = self.active_files[file_path]
            state.access_count += 1
            state.last_accessed = datetime.now()
            if modified:
                state.modified = True
        else:
            # Check limit
            if len(self.active_files) >= self.max_files:
                # Remove least recently accessed, unmodified file
                candidates = [(path, state) for path, state in self.active_files.items() if not state.modified]
                if candidates:
                    candidates.sort(key=lambda x: x[1].last_accessed)
                    removed_path = candidates[0][0]
                    del self.active_files[removed_path]
                    logger.debug("file_removed_from_tracking", removed_path=removed_path)
                    record_counter("memory_files_trimmed_total")

            self.active_files[file_path] = FileState(path=file_path, modified=modified, access_count=1)

        logger.debug(
            "file_tracked",
            file_path=file_path,
            modified=modified,
            access_count=self.active_files[file_path].access_count,
        )
        record_counter("memory_files_tracked_total", labels={"modified": str(modified)})

    def track_symbol(self, name: str, kind: str, file_path: str, line_number: int) -> None:
        """
        Track symbol reference.

        Args:
            name: Symbol name
            kind: Symbol kind (function, class, etc.)
            file_path: File containing symbol
            line_number: Line number
        """
        self.active_symbols[name] = SymbolInfo(name=name, kind=kind, file_path=file_path, line_number=line_number)
        logger.debug("symbol_tracked", symbol_name=name, kind=kind, file_path=file_path, line_number=line_number)
        record_counter("memory_symbols_tracked_total", labels={"kind": kind})

    def add_discovery(self, description: str, importance: str = "medium") -> None:
        """
        Add a discovery with type safety.

        Args:
            description: What was discovered
            importance: Importance level (low/medium/high)
        """
        # Validate importance level
        valid_importance = importance if importance in ("low", "medium", "high") else "medium"
        if valid_importance != importance:
            logger.warning("invalid_discovery_importance", provided=importance, using="medium")
            record_counter("memory_discovery_errors_total", labels={"error": "invalid_importance"})

        discovery = Discovery(description=description, importance=valid_importance)
        self.recent_discoveries.push(discovery)
        desc_preview = description[:50]
        logger.info("discovery_added", description_preview=desc_preview, importance=valid_importance)
        record_counter("memory_discoveries_total", labels={"importance": valid_importance})

    # ============================================================
    # Context Snapshot
    # ============================================================

    def _capture_context_snapshot(self) -> dict[str, Any]:
        """Capture current context snapshot."""
        return {
            "timestamp": datetime.now().isoformat(),
            "active_files": list(self.active_files.keys()),
            "active_symbols": list(self.active_symbols.keys()),
            "hypothesis_count": len(self.hypotheses),
            "decision_count": len(self.decisions),
            "current_step": self.current_step,
        }

    # ============================================================
    # Session Consolidation
    # ============================================================

    def consolidate(self) -> Episode:
        """
        Consolidate working memory into episodic record.

        Called at end of session to create an episode for long-term storage.

        Returns:
            Episode record
        """
        if not self.current_task:
            raise ValueError("Cannot consolidate without active task")

        # Calculate duration
        duration_ms = (datetime.now() - self.started_at).total_seconds() * 1000

        # Aggregate tool usage
        tool_usage = self._aggregate_tool_usage()

        # Extract applied patches
        patches = self._extract_applied_patches()

        # Extract plan summary
        plan_summary = self._extract_plan_summary()

        # Extract pivots
        pivots = self._extract_pivots()

        # Get project_id from context or infer from files
        project_id = self._get_project_id()

        episode = Episode(
            id=str(uuid4()),
            project_id=project_id,
            session_id=self.session_id,
            task_type=self.current_task["type"],
            task_description=self.current_task["description"],
            files_involved=list(self.active_files.keys()),
            symbols_involved=list(self.active_symbols.keys()),
            error_types=[e.error.__class__.__name__ for e in self.recent_errors.to_list()],
            plan_summary=plan_summary,
            steps_count=len(self.steps_completed),
            tools_used=tool_usage,
            key_decisions=self.decisions.copy(),
            pivots=pivots,
            outcome_status=self.current_task["status"],
            patches=patches,
            tests_passed=False,  # TODO: Check test results
            created_at=self.started_at,
            duration_ms=duration_ms,
            tokens_used=self.stats["tokens_used"],
        )

        logger.info(
            "session_consolidated",
            session_id=self.session_id,
            steps_count=len(self.steps_completed),
            files_count=len(self.active_files),
            symbols_count=len(self.active_symbols),
            duration_ms=duration_ms,
            task_type=self.current_task["type"].value,
        )
        record_counter("memory_sessions_consolidated_total", labels={"task_type": self.current_task["type"].value})
        record_histogram("memory_session_duration_ms", duration_ms)
        record_histogram("memory_session_steps", len(self.steps_completed))
        record_histogram("memory_session_files", len(self.active_files))

        return episode

    def _aggregate_tool_usage(self) -> list[ToolUsageSummary]:
        """Aggregate tool usage statistics."""
        tool_stats: dict[str, dict] = {}

        for step in self.steps_completed:
            if step.tool_name not in tool_stats:
                tool_stats[step.tool_name] = {"count": 0, "success": 0, "total_duration": 0.0}

            tool_stats[step.tool_name]["count"] += 1
            if step.success:
                tool_stats[step.tool_name]["success"] += 1
            tool_stats[step.tool_name]["total_duration"] += step.duration_ms

        return [
            ToolUsageSummary(
                tool_name=tool,
                call_count=stats["count"],
                success_count=stats["success"],
                avg_duration_ms=stats["total_duration"] / stats["count"] if stats["count"] > 0 else 0.0,
            )
            for tool, stats in tool_stats.items()
        ]

    def _extract_applied_patches(self) -> list[PatchSummary]:
        """Extract applied patches from file modifications."""
        patches = []
        for file_path, state in self.active_files.items():
            if state.modified:
                # Calculate line changes from step records
                lines_added, lines_removed = self._calculate_line_changes(file_path)
                description = self._generate_patch_description(file_path, lines_added, lines_removed)
                patches.append(
                    PatchSummary(
                        file_path=file_path,
                        lines_added=lines_added,
                        lines_removed=lines_removed,
                        description=description,
                    )
                )
        return patches

    def _calculate_line_changes(self, file_path: str) -> tuple[int, int]:
        """
        Calculate line changes for a file from step records.

        Args:
            file_path: Path to file

        Returns:
            Tuple of (lines_added, lines_removed)
        """
        lines_added = 0
        lines_removed = 0

        # Scan through step records for edits to this file
        for step in self.steps_completed:
            if step.tool_name in ("edit", "write", "search_replace"):
                tool_input = step.tool_input
                if isinstance(tool_input, dict):
                    step_file = tool_input.get("file_path") or tool_input.get("target_file")
                    if step_file == file_path and step.success:
                        # Estimate changes from tool input
                        old_str = tool_input.get("old_string", "")
                        new_str = tool_input.get("new_string", "")
                        contents = tool_input.get("contents", "")

                        if old_str and new_str:
                            # search_replace
                            old_lines = old_str.count("\n") + 1
                            new_lines = new_str.count("\n") + 1
                            if new_lines > old_lines:
                                lines_added += new_lines - old_lines
                            else:
                                lines_removed += old_lines - new_lines
                        elif contents:
                            # write - count as all added (simplified)
                            lines_added += contents.count("\n") + 1

        return lines_added, lines_removed

    def _generate_patch_description(self, file_path: str, lines_added: int, lines_removed: int) -> str:
        """
        Generate a description for a patch.

        Args:
            file_path: Path to file
            lines_added: Number of lines added
            lines_removed: Number of lines removed

        Returns:
            Description string
        """
        if lines_added > 0 and lines_removed > 0:
            return f"Modified: +{lines_added}/-{lines_removed} lines"
        elif lines_added > 0:
            return f"Added: +{lines_added} lines"
        elif lines_removed > 0:
            return f"Removed: -{lines_removed} lines"
        else:
            return "Modified (no line count available)"

    def _extract_plan_summary(self) -> str:
        """
        Extract plan summary from current plan.

        Returns:
            Plan summary string
        """
        if not self.current_plan:
            return ""

        # Extract key information from plan
        if isinstance(self.current_plan, dict):
            # Try to get summary or description
            summary = self.current_plan.get("summary", "")
            if summary:
                return summary

            # Fallback: extract from steps or goals
            steps = self.current_plan.get("steps", [])
            if steps:
                step_summary = ", ".join(str(s)[:50] for s in steps[:3])
                return f"Plan: {step_summary}" + ("..." if len(steps) > 3 else "")

            goals = self.current_plan.get("goals", [])
            if goals:
                goal_summary = ", ".join(str(g)[:50] for g in goals[:3])
                return f"Goals: {goal_summary}" + ("..." if len(goals) > 3 else "")

        return str(self.current_plan)[:200] if self.current_plan else ""

    def _extract_pivots(self) -> list:
        """
        Extract pivots (strategic changes) from execution history.

        A pivot is detected when:
        - Error rate suddenly changes
        - Tool usage pattern changes
        - Active files/symbols significantly change
        - New hypothesis or decision

        Returns:
            List of Pivot objects
        """
        from .models import Pivot

        pivots = []

        # Check for error-driven pivots
        error_steps = [i for i, step in enumerate(self.steps_completed) if not step.success]
        if error_steps:
            # Find clusters of errors
            for i in range(len(error_steps) - 1):
                if error_steps[i + 1] - error_steps[i] > 5:  # Gap of 5+ steps
                    step_num = error_steps[i + 1]
                    if step_num < len(self.steps_completed):
                        pivots.append(
                            Pivot(
                                step_number=step_num,
                                description="Strategy change after errors",
                                reason="Recovered from error sequence",
                            )
                        )

        # Check for decision-driven pivots
        for decision in self.decisions:
            if hasattr(decision, "context_snapshot"):
                step = decision.context_snapshot.get("current_step", 0)
                if step > 0:
                    pivots.append(
                        Pivot(
                            step_number=step,
                            description=f"Decision: {decision.description[:50]}",
                            reason=decision.rationale[:100] if hasattr(decision, "rationale") else "",
                        )
                    )

        # Sort by step number
        pivots.sort(key=lambda p: p.step_number)

        # Limit to most significant pivots
        return pivots[:5]

    def _get_project_id(self) -> str:
        """
        Get project ID from context or infer from active files.

        Returns:
            Project ID string
        """
        # Try to extract from active files (common path prefix)
        if self.active_files:
            files = list(self.active_files.keys())
            # Find common prefix
            if len(files) == 1:
                # Use first directory component
                parts = files[0].split("/")
                return parts[0] if parts else "default"
            else:
                # Find common prefix among all files
                common_prefix = files[0]
                for f in files[1:]:
                    while not f.startswith(common_prefix):
                        common_prefix = common_prefix[:-1]
                        if not common_prefix:
                            return "default"

                # Extract project name from prefix
                parts = common_prefix.rstrip("/").split("/")
                return parts[-1] if parts else "default"

        return "default"

    # ============================================================
    # Query Methods
    # ============================================================

    def get_recent_errors(self) -> list[ErrorRecord]:
        """Get recent errors."""
        return self.recent_errors.to_list()

    def get_recent_discoveries(self) -> list[Discovery]:
        """Get recent discoveries."""
        return self.recent_discoveries.to_list()

    def get_active_hypotheses(self) -> list[Hypothesis]:
        """Get active hypotheses."""
        return [h for h in self.hypotheses if h.status == "active"]

    def get_summary(self) -> dict[str, Any]:
        """Get session summary."""
        return {
            "session_id": self.session_id,
            "duration_sec": (datetime.now() - self.started_at).total_seconds(),
            "steps_completed": len(self.steps_completed),
            "files_accessed": len(self.active_files),
            "files_modified": sum(1 for f in self.active_files.values() if f.modified),
            "symbols_referenced": len(self.active_symbols),
            "hypotheses": len(self.hypotheses),
            "decisions": len(self.decisions),
            "errors": len(self.recent_errors),
            "stats": self.stats.copy(),
        }
