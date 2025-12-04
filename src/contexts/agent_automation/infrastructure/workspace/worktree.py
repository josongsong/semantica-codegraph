"""Git Worktree Adapter - Manages git worktree operations."""

import subprocess
from pathlib import Path

from src.infra.observability import get_logger

logger = get_logger(__name__)


class GitWorktreeAdapter:
    """Manages git worktree creation and deletion.

    Git worktree allows multiple working directories for the same repo,
    enabling parallel agent operations without conflicts.
    """

    def __init__(self, repo_path: Path):
        """Initialize adapter.

        Args:
            repo_path: Main repository path
        """
        self.repo_path = Path(repo_path)

    def create_worktree(
        self,
        worktree_path: Path,
        branch: str | None = None,
        detach: bool = False,
    ) -> bool:
        """Create a new git worktree.

        Args:
            worktree_path: Path for the new worktree
            branch: Branch to checkout (creates if doesn't exist)
            detach: Create detached HEAD

        Returns:
            True if successful
        """
        cmd = ["git", "worktree", "add"]

        if detach:
            cmd.append("--detach")

        cmd.append(str(worktree_path))

        if branch:
            cmd.extend(["-b", branch])

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                logger.info(
                    "worktree_created",
                    worktree_path=str(worktree_path),
                    branch=branch,
                )
                return True
            else:
                logger.error(
                    "worktree_creation_failed",
                    worktree_path=str(worktree_path),
                    error=result.stderr,
                )
                return False

        except Exception as e:
            logger.error(
                "worktree_creation_exception",
                worktree_path=str(worktree_path),
                error=str(e),
            )
            return False

    def remove_worktree(self, worktree_path: Path, force: bool = False) -> bool:
        """Remove a git worktree.

        Args:
            worktree_path: Worktree path to remove
            force: Force removal even if dirty

        Returns:
            True if successful
        """
        cmd = ["git", "worktree", "remove", str(worktree_path)]

        if force:
            cmd.append("--force")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                logger.info("worktree_removed", worktree_path=str(worktree_path))
                return True
            else:
                logger.error(
                    "worktree_removal_failed",
                    worktree_path=str(worktree_path),
                    error=result.stderr,
                )
                return False

        except Exception as e:
            logger.error(
                "worktree_removal_exception",
                worktree_path=str(worktree_path),
                error=str(e),
            )
            return False

    def list_worktrees(self) -> list[dict]:
        """List all worktrees.

        Returns:
            List of worktree info dicts with path, branch, commit
        """
        cmd = ["git", "worktree", "list", "--porcelain"]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return []

            # Parse porcelain output
            worktrees = []
            current = {}

            for line in result.stdout.strip().split("\n"):
                if not line:
                    if current:
                        worktrees.append(current)
                        current = {}
                    continue

                if line.startswith("worktree "):
                    current["path"] = line.split(" ", 1)[1]
                elif line.startswith("HEAD "):
                    current["commit"] = line.split(" ", 1)[1]
                elif line.startswith("branch "):
                    current["branch"] = line.split(" ", 1)[1]
                elif line.startswith("detached"):
                    current["detached"] = True

            if current:
                worktrees.append(current)

            return worktrees

        except Exception as e:
            logger.error("list_worktrees_failed", error=str(e))
            return []

    def prune_worktrees(self) -> bool:
        """Prune stale worktree administrative files.

        Returns:
            True if successful
        """
        cmd = ["git", "worktree", "prune"]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                logger.info("worktrees_pruned")
                return True
            else:
                logger.error("worktree_prune_failed", error=result.stderr)
                return False

        except Exception as e:
            logger.error("worktree_prune_exception", error=str(e))
            return False
