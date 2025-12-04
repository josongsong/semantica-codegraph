"""
Git Workflow Mode

Handles Git automation including commits, branches, and PRs.

Features:
- Commit message generation (conventional format)
- File staging and commit preparation
- Branch name suggestions
- Conflict detection
- LLM-powered intelligent messages
"""

from typing import Any

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

logger = get_logger(__name__)


@mode_registry.register(AgentMode.GIT_WORKFLOW)
class GitWorkflowMode(BaseModeHandler):
    """
    Git Workflow mode for Git automation.

    Flow:
    1. Analyze pending changes
    2. Generate commit message (LLM or template)
    3. Stage files
    4. Create branch name suggestion (optional)
    5. Prepare for commit or PR

    Transitions:
    - committed → Done (changes committed)
    - staged → Ready to commit
    - conflicts_detected → Resolve conflicts
    - no_changes → Stay (nothing to commit)
    """

    def __init__(self, llm_client=None, git_client=None):
        """
        Initialize Git Workflow mode.

        Args:
            llm_client: Optional LLM client for intelligent commit messages
            git_client: Optional Git client for actual Git operations
        """
        super().__init__(AgentMode.GIT_WORKFLOW)
        self.llm = llm_client
        self.git = git_client

    async def enter(self, context: ModeContext) -> None:
        """Enter git workflow mode."""
        await super().enter(context)
        self.logger.info(f"🔀 Git Workflow mode: Processing {len(context.pending_changes)} changes")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute git workflow.

        Args:
            task: Git workflow task
            context: Shared mode context with pending changes

        Returns:
            Result with commit message, staged files, and branch suggestion
        """
        self.logger.info(f"Processing git workflow: {task.query}")

        # 1. Check for pending changes
        if not context.pending_changes:
            return self._create_result(
                data={
                    "no_changes": True,
                    "files_staged": 0,
                },
                trigger="no_changes",
                explanation="No changes to commit",
            )

        # 2. Analyze changes
        change_summary = self._analyze_changes(context.pending_changes)

        # 3. Generate commit message
        commit_message = await self._generate_commit_message(context.pending_changes, change_summary, task)

        # 4. Stage files
        files_staged = await self._stage_files(context.pending_changes)

        # 5. Generate branch name suggestion
        branch_name = self._generate_branch_name(change_summary)

        # 6. Detect conflicts (if git client available)
        conflicts = await self._detect_conflicts()

        # 7. Determine trigger
        trigger = self._determine_trigger(files_staged, conflicts)

        return self._create_result(
            data={
                "commit_message": commit_message,
                "files_staged": files_staged,
                "branch_name": branch_name,
                "change_summary": change_summary,
                "conflicts": conflicts,
            },
            trigger=trigger,
            explanation=f"Staged {files_staged} files, generated commit message",
        )

    def _analyze_changes(self, pending_changes: list[dict]) -> dict[str, Any]:
        """
        Analyze pending changes to understand what's being committed.

        Args:
            pending_changes: List of pending changes

        Returns:
            Change summary dictionary
        """
        summary = {
            "total_files": len(pending_changes),
            "added": 0,
            "modified": 0,
            "deleted": 0,
            "files_by_type": {},
        }

        for change in pending_changes:
            change_type = change.get("change_type", "modify")
            file_path = change.get("file_path", "")

            # Count by change type
            if change_type == "add":
                summary["added"] += 1
            elif change_type == "delete":
                summary["deleted"] += 1
            else:
                summary["modified"] += 1

            # Count by file type
            if "." in file_path:
                ext = file_path.split(".")[-1]
                summary["files_by_type"][ext] = summary["files_by_type"].get(ext, 0) + 1

        return summary

    async def _generate_commit_message(self, pending_changes: list[dict], change_summary: dict, task: Task) -> str:
        """
        Generate commit message using LLM or template.

        Args:
            pending_changes: List of pending changes
            change_summary: Change summary
            task: Git workflow task

        Returns:
            Commit message string
        """
        # Try LLM first
        if self.llm:
            try:
                return await self._generate_llm_commit_message(pending_changes, change_summary, task)
            except Exception as e:
                self.logger.warning(f"LLM commit message failed: {e}, using template")

        # Fallback: Template-based commit message
        return self._generate_template_commit_message(pending_changes, change_summary)

    async def _generate_llm_commit_message(self, pending_changes: list[dict], change_summary: dict, task: Task) -> str:
        """Generate commit message using LLM."""
        # Prepare change context
        changes_context = "\n".join([f"- {change['change_type']}: {change['file_path']}" for change in pending_changes])

        prompt = f"""Generate a conventional commit message for these changes:

Changes:
{changes_context}

Summary:
- Added: {change_summary["added"]} files
- Modified: {change_summary["modified"]} files
- Deleted: {change_summary["deleted"]} files

Task: {task.query}

Follow conventional commit format (feat:, fix:, refactor:, docs:, etc.).
Keep it concise (50 chars for subject, optional body).
"""

        if self.llm is None:
            return ""

        messages = [{"role": "user", "content": prompt}]
        response = await self.llm.complete(messages, temperature=0.3, max_tokens=500)

        return response.get("content", "").strip()

    def _generate_template_commit_message(self, pending_changes: list[dict], change_summary: dict) -> str:
        """
        Generate template-based commit message.

        Args:
            pending_changes: List of pending changes
            change_summary: Change summary

        Returns:
            Commit message string
        """
        # Determine commit type
        added = change_summary["added"]
        modified = change_summary["modified"]
        deleted = change_summary["deleted"]

        if added > 0 and modified == 0 and deleted == 0:
            commit_type = "feat"
            action = "Add"
        elif deleted > 0 and added == 0 and modified == 0:
            commit_type = "remove"
            action = "Remove"
        elif modified > 0:
            commit_type = "refactor"
            action = "Update"
        else:
            commit_type = "chore"
            action = "Change"

        # Get file descriptions
        total_files = change_summary["total_files"]
        if total_files == 1:
            file_path = pending_changes[0]["file_path"]
            file_name = file_path.split("/")[-1]
            description = file_name
        else:
            # Multiple files - describe by type
            file_types = change_summary["files_by_type"]
            if len(file_types) == 1:
                ext = list(file_types.keys())[0]
                description = f"{total_files} {ext} files"
            else:
                description = f"{total_files} files"

        # Generate message
        commit_message = f"{commit_type}: {action} {description}"

        return commit_message

    async def _stage_files(self, pending_changes: list[dict]) -> int:
        """
        Stage files for commit.

        Args:
            pending_changes: List of pending changes

        Returns:
            Number of files staged
        """
        if self.git:
            # Use actual git client
            try:
                files_to_stage = [change["file_path"] for change in pending_changes]
                result = await self.git.stage_files(files_to_stage)
                return len(result.get("staged", []))
            except Exception as e:
                self.logger.warning(f"Git staging failed: {e}, simulating")

        # Simulation mode (no git client)
        return len(pending_changes)

    def _generate_branch_name(self, change_summary: dict) -> str:
        """
        Generate branch name suggestion.

        Args:
            change_summary: Change summary

        Returns:
            Branch name string
        """
        # Simple heuristic for branch naming
        added = change_summary["added"]
        modified = change_summary["modified"]

        if added > 0:
            prefix = "feature"
        elif modified > 0:
            prefix = "refactor"
        else:
            prefix = "update"

        # Generate simple branch name
        total = change_summary["total_files"]
        branch_name = f"{prefix}/update-{total}-files"

        return branch_name

    async def _detect_conflicts(self) -> list[dict]:
        """
        Detect merge conflicts.

        Returns:
            List of detected conflicts
        """
        if self.git:
            # Use actual git client to check for conflicts
            try:
                status = await self.git.get_status()
                # Check for conflict markers
                conflicted_files = status.get("conflicted", [])
                return [{"file": file, "type": "merge_conflict"} for file in conflicted_files]
            except Exception as e:
                self.logger.warning(f"Conflict detection failed: {e}")

        # No conflicts detected (or no git client)
        return []

    def _determine_trigger(self, files_staged: int, conflicts: list[dict]) -> str:
        """
        Determine appropriate trigger based on workflow state.

        Args:
            files_staged: Number of files staged
            conflicts: List of conflicts

        Returns:
            Trigger string for FSM
        """
        if conflicts:
            return "conflicts_detected"
        elif files_staged > 0:
            return "staged"
        else:
            return "no_changes"

    async def exit(self, context: ModeContext) -> None:
        """Exit git workflow mode."""
        self.logger.info("Git workflow complete")
        await super().exit(context)
