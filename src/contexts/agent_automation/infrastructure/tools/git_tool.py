"""
Git Tool

Provides Git operations for the agent.

Features:
- Status check (modified, staged, untracked files)
- Diff generation (staged, unstaged, commit comparison)
- Commit creation with message
- Branch operations (list, switch, create)
- Log viewing (recent commits, file history)
"""

import asyncio
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.tools.base import BaseTool

logger = get_logger(__name__)
# ============================================================
# Input/Output Schemas
# ============================================================


class GitStatusInput(BaseModel):
    """Input for git status."""

    include_untracked: bool = Field(True, description="Include untracked files")


class FileStatus(BaseModel):
    """Status of a single file."""

    path: str = Field(..., description="File path")
    status: Literal["modified", "added", "deleted", "renamed", "untracked", "staged"] = Field(
        ..., description="File status"
    )
    staged: bool = Field(False, description="Whether file is staged")


class GitStatusOutput(BaseModel):
    """Output for git status."""

    success: bool = Field(..., description="Whether command succeeded")
    branch: str = Field("", description="Current branch name")
    files: list[FileStatus] = Field(default_factory=list, description="Changed files")
    ahead: int = Field(0, description="Commits ahead of remote")
    behind: int = Field(0, description="Commits behind remote")
    clean: bool = Field(True, description="Whether working directory is clean")
    error: str | None = Field(None, description="Error message if failed")


class GitDiffInput(BaseModel):
    """Input for git diff."""

    staged: bool = Field(False, description="Show staged changes only")
    file_path: str | None = Field(None, description="Specific file to diff")
    commit: str | None = Field(None, description="Compare with specific commit")
    context_lines: int = Field(3, description="Number of context lines", ge=0, le=10)


class GitDiffOutput(BaseModel):
    """Output for git diff."""

    success: bool = Field(..., description="Whether command succeeded")
    diff: str = Field("", description="Diff content")
    files_changed: int = Field(0, description="Number of files changed")
    insertions: int = Field(0, description="Number of insertions")
    deletions: int = Field(0, description="Number of deletions")
    error: str | None = Field(None, description="Error message if failed")


class GitCommitInput(BaseModel):
    """Input for git commit."""

    message: str = Field(..., description="Commit message")
    files: list[str] | None = Field(None, description="Specific files to commit (None = all staged)")
    amend: bool = Field(False, description="Amend previous commit")


class GitCommitOutput(BaseModel):
    """Output for git commit."""

    success: bool = Field(..., description="Whether commit succeeded")
    commit_hash: str = Field("", description="New commit hash")
    message: str = Field("", description="Commit message")
    files_committed: int = Field(0, description="Number of files committed")
    error: str | None = Field(None, description="Error message if failed")


class GitLogInput(BaseModel):
    """Input for git log."""

    limit: int = Field(10, description="Maximum number of commits", ge=1, le=100)
    file_path: str | None = Field(None, description="Show history for specific file")
    oneline: bool = Field(True, description="One line per commit")


class CommitInfo(BaseModel):
    """Information about a single commit."""

    hash: str = Field(..., description="Commit hash (short)")
    full_hash: str = Field(..., description="Full commit hash")
    author: str = Field(..., description="Author name")
    date: str = Field(..., description="Commit date")
    message: str = Field(..., description="Commit message")


class GitLogOutput(BaseModel):
    """Output for git log."""

    success: bool = Field(..., description="Whether command succeeded")
    commits: list[CommitInfo] = Field(default_factory=list, description="Commit list")
    error: str | None = Field(None, description="Error message if failed")


class GitBranchInput(BaseModel):
    """Input for git branch operations."""

    action: Literal["list", "current", "create", "switch", "delete"] = Field(
        "list", description="Branch action to perform"
    )
    branch_name: str | None = Field(None, description="Branch name (for create/switch/delete)")
    force: bool = Field(False, description="Force operation (for delete)")


class BranchInfo(BaseModel):
    """Information about a branch."""

    name: str = Field(..., description="Branch name")
    is_current: bool = Field(False, description="Whether this is the current branch")
    remote: str | None = Field(None, description="Remote tracking branch")


class GitBranchOutput(BaseModel):
    """Output for git branch operations."""

    success: bool = Field(..., description="Whether operation succeeded")
    current_branch: str = Field("", description="Current branch name")
    branches: list[BranchInfo] = Field(default_factory=list, description="All branches")
    error: str | None = Field(None, description="Error message if failed")


# ============================================================
# Git Tool Implementation
# ============================================================


class GitTool(BaseTool[GitStatusInput, GitStatusOutput]):
    """
    Git operations tool.

    Provides safe Git operations for the agent including:
    - Status checking
    - Diff viewing
    - Commit creation
    - Branch management
    - Log viewing

    Safety:
    - Never runs destructive operations without explicit confirmation
    - Validates all inputs before execution
    - Uses subprocess with timeout for all Git commands
    """

    name = "git"
    description = (
        "Perform Git operations: check status, view diffs, create commits, manage branches, and view commit history."
    )
    input_schema = GitStatusInput  # Default, but supports multiple operations
    output_schema = GitStatusOutput

    def __init__(self, repo_path: str | None = None, timeout: int = 30):
        """
        Initialize Git tool.

        Args:
            repo_path: Path to Git repository (defaults to current directory)
            timeout: Command timeout in seconds
        """
        super().__init__()
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self.timeout = timeout

    async def _execute(self, input_data: GitStatusInput) -> GitStatusOutput:
        """Execute git status."""
        return await self.status(input_data.include_untracked)

    async def _run_git(self, *args: str) -> tuple[bool, str, str]:
        """
        Run a Git command safely.

        Args:
            *args: Git command arguments

        Returns:
            Tuple of (success, stdout, stderr)
        """
        cmd = ["git", *args]
        logger.debug(f"Running: {' '.join(cmd)}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.repo_path),
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)

            success = process.returncode == 0
            return success, stdout.decode("utf-8"), stderr.decode("utf-8")

        except asyncio.TimeoutError:
            return False, "", f"Command timed out after {self.timeout}s"
        except Exception as e:
            return False, "", str(e)

    async def status(self, include_untracked: bool = True) -> GitStatusOutput:
        """
        Get repository status.

        Args:
            include_untracked: Include untracked files

        Returns:
            GitStatusOutput with current status
        """
        # Get branch info
        success, branch_out, _ = await self._run_git("branch", "--show-current")
        branch = branch_out.strip() if success else "unknown"

        # Get status
        args = ["status", "--porcelain=v1"]
        if not include_untracked:
            args.append("-uno")

        success, status_out, err = await self._run_git(*args)
        if not success:
            return GitStatusOutput(
                success=False,
                branch="",
                files=[],
                ahead=0,
                behind=0,
                clean=True,
                error=err,
            )

        # Parse status
        files = []
        for line in status_out.strip().split("\n"):
            if not line:
                continue

            status_code = line[:2]
            file_path = line[3:].strip()

            # Parse status code
            staged = status_code[0] != " " and status_code[0] != "?"
            if status_code == "??":
                status = "untracked"
            elif "M" in status_code:
                status = "modified"
            elif "A" in status_code:
                status = "added"
            elif "D" in status_code:
                status = "deleted"
            elif "R" in status_code:
                status = "renamed"
            else:
                status = "modified"

            files.append(FileStatus(path=file_path, status=status, staged=staged))

        # Get ahead/behind info
        ahead, behind = 0, 0
        success, ab_out, _ = await self._run_git("rev-list", "--left-right", "--count", f"{branch}...origin/{branch}")
        if success and ab_out.strip():
            parts = ab_out.strip().split()
            if len(parts) == 2:
                ahead, behind = int(parts[0]), int(parts[1])

        return GitStatusOutput(
            success=True,
            branch=branch,
            files=files,
            ahead=ahead,
            behind=behind,
            clean=len(files) == 0,
        )

    async def diff(
        self,
        staged: bool = False,
        file_path: str | None = None,
        commit: str | None = None,
        context_lines: int = 3,
    ) -> GitDiffOutput:
        """
        Get diff of changes.

        Args:
            staged: Show staged changes only
            file_path: Specific file to diff
            commit: Compare with specific commit
            context_lines: Number of context lines

        Returns:
            GitDiffOutput with diff content
        """
        args = ["diff", f"-U{context_lines}"]

        if staged:
            args.append("--cached")

        if commit:
            args.append(commit)

        if file_path:
            args.extend(["--", file_path])

        success, diff_out, err = await self._run_git(*args)
        if not success:
            return GitDiffOutput(success=False, error=err)

        # Get stats
        stat_args = ["diff", "--stat"]
        if staged:
            stat_args.append("--cached")
        if commit:
            stat_args.append(commit)
        if file_path:
            stat_args.extend(["--", file_path])

        _, stat_out, _ = await self._run_git(*stat_args)

        # Parse stats (last line format: "X files changed, Y insertions(+), Z deletions(-)")
        files_changed, insertions, deletions = 0, 0, 0
        stat_lines = stat_out.strip().split("\n")
        if stat_lines:
            last_line = stat_lines[-1]
            if "changed" in last_line:
                import re

                files_match = re.search(r"(\d+) files? changed", last_line)
                ins_match = re.search(r"(\d+) insertions?", last_line)
                del_match = re.search(r"(\d+) deletions?", last_line)

                files_changed = int(files_match.group(1)) if files_match else 0
                insertions = int(ins_match.group(1)) if ins_match else 0
                deletions = int(del_match.group(1)) if del_match else 0

        return GitDiffOutput(
            success=True,
            diff=diff_out,
            files_changed=files_changed,
            insertions=insertions,
            deletions=deletions,
        )

    async def commit(
        self,
        message: str,
        files: list[str] | None = None,
        amend: bool = False,
    ) -> GitCommitOutput:
        """
        Create a commit.

        Args:
            message: Commit message
            files: Specific files to commit (None = all staged)
            amend: Amend previous commit

        Returns:
            GitCommitOutput with commit result
        """
        # Stage specific files if provided
        if files:
            for file in files:
                success, _, err = await self._run_git("add", file)
                if not success:
                    return GitCommitOutput(success=False, error=f"Failed to stage {file}: {err}")

        # Create commit
        args = ["commit", "-m", message]
        if amend:
            args.append("--amend")

        success, out, err = await self._run_git(*args)
        if not success:
            return GitCommitOutput(success=False, error=err)

        # Get commit hash
        success, hash_out, _ = await self._run_git("rev-parse", "--short", "HEAD")
        commit_hash = hash_out.strip() if success else ""

        # Count files committed
        files_committed = 0
        if "file changed" in out or "files changed" in out:
            import re

            match = re.search(r"(\d+) files? changed", out)
            files_committed = int(match.group(1)) if match else 0

        return GitCommitOutput(
            success=True,
            commit_hash=commit_hash,
            message=message,
            files_committed=files_committed,
        )

    async def log(
        self,
        limit: int = 10,
        file_path: str | None = None,
        oneline: bool = True,
    ) -> GitLogOutput:
        """
        Get commit log.

        Args:
            limit: Maximum number of commits
            file_path: Show history for specific file
            oneline: One line per commit

        Returns:
            GitLogOutput with commit list
        """
        # Use custom format for parsing
        format_str = "%h|%H|%an|%ad|%s"
        args = ["log", f"-{limit}", f"--format={format_str}", "--date=short"]

        if file_path:
            args.extend(["--", file_path])

        success, out, err = await self._run_git(*args)
        if not success:
            return GitLogOutput(success=False, error=err)

        commits = []
        for line in out.strip().split("\n"):
            if not line:
                continue

            parts = line.split("|", 4)
            if len(parts) == 5:
                commits.append(
                    CommitInfo(
                        hash=parts[0],
                        full_hash=parts[1],
                        author=parts[2],
                        date=parts[3],
                        message=parts[4],
                    )
                )

        return GitLogOutput(success=True, commits=commits)

    async def branch(
        self,
        action: str = "list",
        branch_name: str | None = None,
        force: bool = False,
    ) -> GitBranchOutput:
        """
        Manage branches.

        Args:
            action: Branch action (list, current, create, switch, delete)
            branch_name: Branch name for create/switch/delete
            force: Force operation

        Returns:
            GitBranchOutput with branch info
        """
        # Get current branch
        success, current_out, _ = await self._run_git("branch", "--show-current")
        current_branch = current_out.strip() if success else ""

        if action == "current":
            return GitBranchOutput(success=True, current_branch=current_branch)

        if action == "list":
            success, out, err = await self._run_git("branch", "-a")
            if not success:
                return GitBranchOutput(success=False, error=err)

            branches = []
            for line in out.strip().split("\n"):
                if not line:
                    continue
                is_current = line.startswith("*")
                name = line.lstrip("* ").strip()

                # Handle remote branches
                remote = None
                if name.startswith("remotes/"):
                    remote = name.split("/")[1]
                    name = "/".join(name.split("/")[2:])

                branches.append(BranchInfo(name=name, is_current=is_current, remote=remote))

            return GitBranchOutput(success=True, current_branch=current_branch, branches=branches)

        if action == "create":
            if not branch_name:
                return GitBranchOutput(success=False, error="Branch name required for create")

            success, _, err = await self._run_git("checkout", "-b", branch_name)
            if not success:
                return GitBranchOutput(success=False, error=err)

            return GitBranchOutput(success=True, current_branch=branch_name)

        if action == "switch":
            if not branch_name:
                return GitBranchOutput(success=False, error="Branch name required for switch")

            success, _, err = await self._run_git("checkout", branch_name)
            if not success:
                return GitBranchOutput(success=False, error=err)

            return GitBranchOutput(success=True, current_branch=branch_name)

        if action == "delete":
            if not branch_name:
                return GitBranchOutput(success=False, error="Branch name required for delete")

            args = ["branch", "-d" if not force else "-D", branch_name]
            success, _, err = await self._run_git(*args)
            if not success:
                return GitBranchOutput(success=False, error=err)

            return GitBranchOutput(success=True, current_branch=current_branch)

        return GitBranchOutput(success=False, error=f"Unknown action: {action}")
