"""
Agent Orchestrator

High-level orchestration of the agent system:
- Task management and execution
- Mode coordination via FSM
- Change application to files
- Human approval integration
- End-to-end workflow management
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.agent.fsm import AgentFSM
from src.agent.types import AgentMode, Change, ModeContext, Result, Task

logger = logging.getLogger(__name__)


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
            logger.error(f"Change application failed: {e}. Rolling back...")
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
            self.applied_changes.append(
                {"file_path": file_path, "backup_content": backup_content, "existed": True}
            )
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

        logger.info(f"Applied change: {change_type} {change.file_path}")

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
            new_lines = (
                lines[: change.line_start - 1]
                + [change.content + "\n"]
                + lines[change.line_end :]
            )
            file_path.write_text("".join(new_lines))
        else:
            # Replace entire file
            file_path.write_text(change.content)

    def _delete_file(self, file_path: Path) -> None:
        """Delete a file."""
        if not file_path.exists():
            logger.warning(f"Cannot delete non-existent file: {file_path}")
            return

        file_path.unlink()

    def _rollback(self) -> None:
        """Rollback all applied changes."""
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
                logger.error(f"Rollback failed for {file_path}: {e}")

        self.applied_changes.clear()
        logger.info("Rollback completed")


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
    ):
        """
        Initialize orchestrator.

        Args:
            fsm: AgentFSM instance (creates new if None)
            approval_callback: Optional async function for human approval
            base_path: Base directory for file operations
            auto_approve: If True, automatically approve all changes
        """
        self.fsm = fsm or AgentFSM()
        self.approval_callback = approval_callback
        self.auto_approve = auto_approve
        self.change_applicator = ChangeApplicator(base_path)
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

        logger.info(f"Executing task: {task.query} (starting mode: {start_mode.value})")

        # Transition to starting mode
        await self.fsm.transition_to(start_mode)

        # Execute task
        result = await self.fsm.execute(task)

        # Record execution
        self.execution_history.append(
            {"task": task.query, "mode": result.mode.value, "trigger": result.trigger}
        )

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
        logger.info(f"Starting workflow for: {task.query}")

        # Determine starting mode
        if start_mode is None:
            start_mode = self.fsm.suggest_next_mode(task.query)

            # Fallback to CONTEXT_NAV if suggested mode has no handler
            if start_mode not in self.fsm.handlers:
                logger.warning(
                    f"Suggested mode {start_mode.value} has no handler, using CONTEXT_NAV"
                )
                start_mode = AgentMode.CONTEXT_NAV

        await self.fsm.transition_to(start_mode)

        # Execute workflow
        results = []
        transitions = 0

        while transitions < max_transitions:
            # Execute current mode
            result = await self.fsm.execute(task)
            results.append(
                {"mode": result.mode.value, "trigger": result.trigger, "data": result.data}
            )

            # Check if workflow is complete
            if result.trigger is None or self.fsm.current_mode == AgentMode.IDLE:
                break

            transitions += 1

        # Apply pending changes if requested
        application_result = None
        if apply_changes and len(self.fsm.context.pending_changes) > 0:
            application_result = await self.apply_pending_changes()

        workflow_result = {
            "success": True,
            "task": task.query,
            "transitions": transitions,
            "final_mode": self.fsm.current_mode.value,
            "results": results,
            "pending_changes": len(self.fsm.context.pending_changes),
            "application_result": application_result,
        }

        logger.info(
            f"Workflow complete: {transitions} transitions, "
            f"{len(self.fsm.context.pending_changes)} pending changes"
        )

        return workflow_result

    async def apply_pending_changes(self, require_approval: bool = True) -> dict[str, Any]:
        """
        Apply all pending changes from context.

        Args:
            require_approval: If True, request approval before applying

        Returns:
            Result of change application
        """
        if not self.fsm.context.pending_changes:
            return {"success": True, "message": "No pending changes"}

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
                return {"success": False, "message": "Changes rejected by user"}

        # Apply changes
        result = await self.change_applicator.apply_changes(changes)

        # Clear pending changes if successful
        if result["success"]:
            self.fsm.context.clear_pending_changes()
            logger.info(f"Applied {result['changes']} changes successfully")
        else:
            logger.error(f"Failed to apply changes: {result['message']}")

        return result

    async def _request_approval(self, changes: list[Change]) -> bool:
        """
        Request human approval for changes.

        Args:
            changes: List of changes to approve

        Returns:
            True if approved, False otherwise
        """
        if self.auto_approve:
            logger.info("Auto-approving changes")
            return True

        if self.approval_callback:
            try:
                approved = await self.approval_callback(changes, self.fsm.context)
                logger.info(f"Approval callback result: {approved}")
                return bool(approved)
            except Exception as e:
                logger.error(f"Approval callback failed: {e}")
                return False

        # Default: require explicit approval
        logger.warning("No approval callback provided and auto_approve=False")
        return False

    def get_context(self) -> ModeContext:
        """Get current FSM context."""
        return self.fsm.context

    def get_execution_history(self) -> list[dict]:
        """Get execution history."""
        return self.execution_history

    def reset(self) -> None:
        """Reset orchestrator state."""
        self.fsm.reset()
        self.execution_history.clear()
        logger.info("Orchestrator reset")


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
