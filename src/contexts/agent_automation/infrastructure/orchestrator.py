"""
Agent Orchestrator

High-level orchestration of the agent system:
- Task management and execution
- Mode coordination via FSM
- Change application to files
- Human approval integration
- End-to-end workflow management
"""

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.contexts.agent_automation.infrastructure.fsm import AgentFSM
from src.contexts.agent_automation.infrastructure.types import (
    AgentMode,
    ApprovalLevel,
    Change,
    ModeContext,
    Result,
    Task,
)
from src.infra.observability import get_logger, record_counter, record_histogram

logger = get_logger(__name__)


class ChangeApplicator:
    """
    Applies code changes to files with atomic operations.

    Supports:
    - Add new files
    - Modify existing files
    - Delete files
    - Rollback capability
    """

    def __init__(self, base_path: str | Path = "."):
        """
        Initialize change applicator.

        Args:
            base_path: Base directory for file operations
        """
        self.base_path = Path(base_path)
        self.applied_changes: list[dict] = []  # For rollback

    async def apply_changes(self, changes: list[Change]) -> dict[str, Any]:
        """
        Apply a list of changes atomically.

        If any change fails, all changes are rolled back.

        Args:
            changes: List of Change objects to apply

        Returns:
            Result dictionary with success status and details
        """
        if not changes:
            return {"success": True, "message": "No changes to apply"}

        self.applied_changes.clear()
        applied_count = 0

        try:
            for change in changes:
                self._apply_single_change(change)
                applied_count += 1

            return {
                "success": True,
                "message": f"Applied {applied_count} changes",
                "changes": applied_count,
            }

        except Exception as e:
            # Rollback all applied changes
            logger.error("change_application_failed", error=str(e), applied_count=applied_count, exc_info=True)
            record_counter("agent_change_application_errors_total", labels={"stage": "apply"})
            self._rollback()
            return {
                "success": False,
                "message": f"Failed to apply changes: {e}",
                "applied": applied_count,
                "rolled_back": True,
            }

    def _apply_single_change(self, change: Change) -> None:
        """
        Apply a single change to a file.

        Args:
            change: Change to apply

        Raises:
            Exception: If change application fails
        """
        file_path = self.base_path / change.file_path
        change_type = change.change_type

        # Backup existing file content (for rollback)
        if file_path.exists():
            backup_content = file_path.read_text()
            self.applied_changes.append({"file_path": file_path, "backup_content": backup_content, "existed": True})
        else:
            self.applied_changes.append({"file_path": file_path, "existed": False})

        # Apply change
        if change_type == "add":
            self._add_file(file_path, change.content)
        elif change_type == "modify":
            self._modify_file(file_path, change)
        elif change_type == "delete":
            self._delete_file(file_path)
        else:
            raise ValueError(f"Unknown change type: {change_type}")

        logger.debug("change_applied", change_type=change_type, file_path=str(change.file_path))
        record_counter("agent_changes_applied_total", labels={"change_type": change_type})

    def _add_file(self, file_path: Path, content: str) -> None:
        """Add a new file."""
        if file_path.exists():
            raise FileExistsError(f"File already exists: {file_path}")

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

    def _modify_file(self, file_path: Path, change: Change) -> None:
        """Modify an existing file."""
        if not file_path.exists():
            # Create new file if it doesn't exist
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(change.content)
            return

        # If line range specified, replace those lines
        if change.line_start is not None and change.line_end is not None:
            lines = file_path.read_text().splitlines(keepends=True)
            new_lines = lines[: change.line_start - 1] + [change.content + "\n"] + lines[change.line_end :]
            file_path.write_text("".join(new_lines))
        else:
            # Replace entire file
            file_path.write_text(change.content)

    def _delete_file(self, file_path: Path) -> None:
        """Delete a file."""
        if not file_path.exists():
            logger.warning("delete_nonexistent_file", file_path=str(file_path))
            return

        file_path.unlink()

    def _rollback(self) -> None:
        """Rollback all applied changes."""
        rollback_count = len(self.applied_changes)
        rollback_errors = 0

        for change_record in reversed(self.applied_changes):
            file_path = change_record["file_path"]
            try:
                if change_record["existed"]:
                    # Restore original content
                    file_path.write_text(change_record["backup_content"])
                else:
                    # Remove newly created file
                    if file_path.exists():
                        file_path.unlink()
            except Exception as e:
                rollback_errors += 1
                logger.error("rollback_failed", file_path=str(file_path), error=str(e), exc_info=True)
                record_counter("agent_rollback_errors_total", labels={"file": str(file_path)})

        self.applied_changes.clear()
        logger.info("rollback_completed", changes_count=rollback_count, errors=rollback_errors)
        record_counter("agent_rollbacks_total", value=1)
        record_histogram("agent_rollback_changes_count", rollback_count)


class AgentOrchestrator:
    """
    High-level agent orchestrator.

    Manages:
    - FSM and mode transitions
    - Task execution
    - Change application
    - Human approval flow
    - End-to-end workflows
    """

    def __init__(
        self,
        fsm: AgentFSM | None = None,
        approval_callback: Callable | None = None,
        base_path: str | Path = ".",
        auto_approve: bool = False,
        indexing_port=None,
        repo_id: str = "default",
        snapshot_id: str | None = None,
    ):
        """
        Initialize orchestrator.

        Args:
            fsm: AgentFSM instance (creates new if None)
            approval_callback: Optional async function for human approval
            base_path: Base directory for file operations
            auto_approve: If True, automatically approve all changes
            indexing_port: IncrementalIndexingPort implementation (optional)
            repo_id: Repository ID
            snapshot_id: Snapshot ID (branch/worktree, None if not set)
        """
        self.fsm = fsm or AgentFSM()
        self.approval_callback = approval_callback
        self.auto_approve = auto_approve
        self.change_applicator = ChangeApplicator(base_path)
        self.indexing_port = indexing_port
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id
        self.execution_history: list[dict] = []

    async def execute_task(self, task: Task, start_mode: AgentMode | None = None) -> Result:
        """
        Execute a single task.

        Args:
            task: Task to execute
            start_mode: Optional starting mode (defaults to suggest_next_mode)

        Returns:
            Final result after execution
        """
        # Determine starting mode
        if start_mode is None:
            start_mode = self.fsm.suggest_next_mode(task.query)

        logger.info("task_execution_started", query_preview=task.query[:100], starting_mode=start_mode.value)
        record_counter("agent_tasks_started_total", labels={"mode": start_mode.value})

        start_time = time.time()

        # Transition to starting mode
        await self.fsm.transition_to(start_mode)

        # Execute task
        result = await self.fsm.execute(task)

        # Record execution
        execution_duration = time.time() - start_time
        self.execution_history.append({"task": task.query, "mode": result.mode.value, "trigger": result.trigger})

        logger.info(
            "task_execution_completed",
            mode=result.mode.value,
            trigger=result.trigger,
            duration_seconds=execution_duration,
        )
        record_counter("agent_tasks_completed_total", labels={"mode": result.mode.value})
        record_histogram("agent_task_duration_seconds", execution_duration)

        return result

    async def execute_workflow(
        self,
        task: Task,
        max_transitions: int = 10,
        apply_changes: bool = True,
        start_mode: AgentMode | None = None,
    ) -> dict[str, Any]:
        """
        Execute a complete workflow with automatic mode transitions.

        Args:
            task: Task to execute
            max_transitions: Maximum number of mode transitions
            apply_changes: If True, apply pending changes at the end
            start_mode: Optional starting mode (defaults to suggest_next_mode)

        Returns:
            Workflow result with all executed steps
        """
        logger.info("workflow_started", query_preview=task.query[:100], max_transitions=max_transitions)
        record_counter("agent_workflows_started_total")

        workflow_start_time = time.time()

        # Determine starting mode
        if start_mode is None:
            start_mode = self.fsm.suggest_next_mode(task.query)

            # Fallback to CONTEXT_NAV if suggested mode has no handler
            if start_mode not in self.fsm.handlers:
                logger.warning("suggested_mode_no_handler", suggested_mode=start_mode.value, fallback="CONTEXT_NAV")
                record_counter(
                    "agent_mode_fallbacks_total", labels={"suggested": start_mode.value, "fallback": "CONTEXT_NAV"}
                )
                start_mode = AgentMode.CONTEXT_NAV

        await self.fsm.transition_to(start_mode)
        record_counter("agent_mode_transitions_total", labels={"to_mode": start_mode.value})

        # Execute workflow
        results = []
        transitions = 0

        while transitions < max_transitions:
            # Execute current mode
            mode_start_time = time.time()
            result = await self.fsm.execute(task)
            mode_duration = time.time() - mode_start_time

            results.append({"mode": result.mode.value, "trigger": result.trigger, "data": result.data})
            record_histogram("agent_mode_execution_duration_seconds", mode_duration)

            # Check if workflow is complete
            if result.trigger is None or self.fsm.current_mode == AgentMode.IDLE:
                break

            transitions += 1
            record_counter("agent_mode_transitions_total", labels={"to_mode": self.fsm.current_mode.value})

        # Apply pending changes if requested
        application_result = None
        if apply_changes and len(self.fsm.context.pending_changes) > 0:
            application_result = await self.apply_pending_changes()

        workflow_duration = time.time() - workflow_start_time
        pending_changes_count = len(self.fsm.context.pending_changes)

        workflow_result = {
            "success": True,
            "task": task.query,
            "transitions": transitions,
            "final_mode": self.fsm.current_mode.value,
            "results": results,
            "pending_changes": pending_changes_count,
            "application_result": application_result,
        }

        logger.info(
            "workflow_completed",
            transitions_count=transitions,
            pending_changes=pending_changes_count,
            final_mode=self.fsm.current_mode.value,
            duration_seconds=workflow_duration,
        )
        record_counter("agent_workflows_completed_total", labels={"final_mode": self.fsm.current_mode.value})
        record_histogram("agent_workflow_duration_seconds", workflow_duration)
        record_histogram("agent_workflow_transitions_count", transitions)
        record_histogram("agent_workflow_pending_changes_count", pending_changes_count)

        return workflow_result

    async def apply_pending_changes(
        self,
        require_approval: bool = True,
        auto_reindex: bool = True,
        snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Apply all pending changes from context.

        Args:
            require_approval: If True, request approval before applying
            auto_reindex: 자동 재인덱싱 활성화
            snapshot_id: Snapshot ID override

        Returns:
            {
                "success": bool,
                "changes": int,
                "message": str,
                "indexing_status": str,
                "indexing_result": IncrementalIndexingResult | None,
            }
        """
        if not self.fsm.context.pending_changes:
            return {
                "success": True,
                "message": "No pending changes",
                "indexing_status": "not_triggered",
            }

        # Convert pending changes to Change objects
        changes = [
            Change(
                file_path=pc["file_path"],
                content=pc["content"],
                change_type=pc.get("change_type", "modify"),
                line_start=pc.get("line_start"),
                line_end=pc.get("line_end"),
            )
            for pc in self.fsm.context.pending_changes
        ]

        # Request approval if needed
        if require_approval and not self.auto_approve:
            approved = await self._request_approval(changes)
            if not approved:
                return {
                    "success": False,
                    "message": "Changes rejected by user",
                    "indexing_status": "not_triggered",
                }

        # Apply changes
        apply_result = await self.change_applicator.apply_changes(changes)

        if not apply_result["success"]:
            logger.error("changes_application_failed", message=apply_result["message"], exc_info=True)
            record_counter("agent_changes_batches_applied_total", value=1, labels={"status": "failed"})
            return {
                "success": False,
                "changes": 0,
                "message": apply_result.get("message"),
                "indexing_status": "not_triggered",
            }

        # Clear pending changes
        self.fsm.context.clear_pending_changes()
        logger.info("changes_applied_successfully", changes_count=apply_result["changes"])
        record_counter("agent_changes_batches_applied_total", value=1, labels={"status": "success"})
        record_histogram("agent_changes_per_batch", apply_result["changes"])

        # 자동 재인덱싱
        indexing_result = None
        if auto_reindex and self.indexing_port:
            file_paths = [c.file_path for c in changes]
            actual_snapshot = snapshot_id or self.snapshot_id

            if not actual_snapshot:
                logger.warning("snapshot_id_not_set_skipping_reindex")
                indexing_status = "not_triggered"
            else:
                # Git HEAD SHA 가져오기 (Idempotency용)
                head_sha = None
                try:
                    import subprocess

                    result = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        head_sha = result.stdout.strip()
                except Exception:
                    pass

                indexing_result = await self.indexing_port.index_files(
                    repo_id=self.repo_id,
                    snapshot_id=actual_snapshot,
                    file_paths=file_paths,
                    reason="agent_apply",
                    priority=1,
                    head_sha=head_sha,
                )
                indexing_status = indexing_result.status

                logger.info(
                    "auto_reindex_completed",
                    status=indexing_status,
                    indexed_count=indexing_result.indexed_count,
                    total_files=indexing_result.total_files,
                )
        else:
            indexing_status = "not_triggered"

        # 메트릭 (repo_id 검증)
        if self.repo_id and self.repo_id != "default":
            record_counter(
                "agent_changes_applied_total",
                labels={
                    "repo_id": self.repo_id,
                    "indexing_status": indexing_status,
                },
            )

        return {
            "success": True,
            "changes": apply_result["changes"],
            "message": apply_result.get("message", "Changes applied successfully"),
            "indexing_status": indexing_status,
            "indexing_result": indexing_result,
        }

    async def _request_approval(self, changes: list[Change]) -> bool:
        """
        Request human approval for changes.

        Args:
            changes: List of changes to approve

        Returns:
            True if approved, False otherwise
        """
        if self.auto_approve:
            logger.info("changes_auto_approved", changes_count=len(changes))
            record_counter("agent_approvals_total", labels={"type": "auto", "result": "approved"})
            return True

        if self.approval_callback:
            try:
                approval_start = time.time()
                approved = await self.approval_callback(changes, self.fsm.context)
                approval_duration = time.time() - approval_start

                logger.info(
                    "approval_callback_completed",
                    approved=approved,
                    changes_count=len(changes),
                    duration_seconds=approval_duration,
                )
                record_counter(
                    "agent_approvals_total",
                    labels={"type": "callback", "result": "approved" if approved else "rejected"},
                )
                record_histogram("agent_approval_duration_seconds", approval_duration)
                return bool(approved)
            except Exception as e:
                logger.error("approval_callback_failed", error=str(e), exc_info=True)
                record_counter("agent_approval_errors_total")
                return False

        # Default: require explicit approval
        logger.warning("no_approval_mechanism", auto_approve=self.auto_approve, has_callback=False)
        record_counter("agent_approvals_total", labels={"type": "none", "result": "rejected"})
        return False

    def get_context(self) -> ModeContext:
        """Get current FSM context."""
        return self.fsm.context

    def get_execution_history(self) -> list[dict]:
        """Get execution history."""
        return self.execution_history

    def set_approval_level(self, level: ApprovalLevel) -> None:
        """
        Set approval level for this orchestrator.

        Args:
            level: Approval level (LOW, MEDIUM, HIGH)
        """
        self.fsm.context.approval_level = level
        logger.debug(f"Approval level set to: {level.value}")

    def reset(self) -> None:
        """Reset orchestrator state."""
        history_count = len(self.execution_history)
        self.fsm.reset()
        self.execution_history.clear()
        logger.info("orchestrator_reset", history_count=history_count)
        record_counter("agent_orchestrator_resets_total")


# CLI Approval Helper
async def cli_approval(changes: list[Change], context: ModeContext) -> bool:
    """
    Simple CLI-based approval function.

    Args:
        changes: List of changes to approve
        context: Current mode context

    Returns:
        True if user approves, False otherwise
    """
    print("\n" + "=" * 60)
    print("PROPOSED CHANGES")
    print("=" * 60)

    for i, change in enumerate(changes, 1):
        print(f"\n[Change {i}/{len(changes)}]")
        print(f"File: {change.file_path}")
        print(f"Type: {change.change_type}")

        if change.line_start and change.line_end:
            print(f"Lines: {change.line_start}-{change.line_end}")

        print("\nContent:")
        print("-" * 40)
        print(change.content)
        print("-" * 40)

    print("\n📊 Context:")
    print(f"   Files: {len(context.current_files)}")
    print(f"   Symbols: {len(context.current_symbols)}")
    print(f"   Approval Level: {context.approval_level.value}")

    print("\n" + "=" * 60)
    response = input("Approve these changes? (y/n): ")
    approved = response.lower() in ["y", "yes"]

    if approved:
        print("✅ Changes approved")
    else:
        print("❌ Changes rejected")

    return approved
