"""
Git Service

Git history, branch, and PR analysis.
Provides temporal context for code.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..domain.context import GitContext
from ..domain.nodes import CommitNode
from ..ports.git_provider import GitProviderPort
from ..ports.relational_store import RelationalStorePort


class GitService:
    """
    Git operations and history analysis service.

    Provides:
    - Commit history
    - Branch management
    - Change analysis
    - Temporal context
    """

    def __init__(
        self,
        git_provider: GitProviderPort,
        relational_store: RelationalStorePort,
    ):
        """Initialize git service."""
        self.git_provider = git_provider
        self.relational_store = relational_store

    async def get_commit_history(
        self,
        repo_path: Path,
        branch: str,
        max_count: Optional[int] = 100,
    ) -> list[CommitNode]:
        """
        Get commit history for a branch.

        Args:
            repo_path: Repository path
            branch: Branch name
            max_count: Maximum commits to retrieve

        Returns:
            List of commit nodes
        """
        commits = await self.git_provider.get_commit_history(
            repo_path,
            branch,
            max_count,
        )

        # Convert to domain models
        commit_nodes = []
        for commit in commits:
            node = CommitNode(
                node_id=f"commit:{commit.hash}",
                node_type="commit",
                repo_id="",  # TODO: Get repo_id
                hash=commit.hash,
                author=commit.author,
                author_email=commit.author_email,
                authored_at=commit.authored_at,
                message=commit.message,
                parents=commit.parents,
            )
            commit_nodes.append(node)

        return commit_nodes

    async def analyze_file_changes(
        self,
        repo_path: Path,
        file_path: str,
        since: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """
        Analyze change history for a file.

        Args:
            repo_path: Repository path
            file_path: Path to file
            since: Optional start date

        Returns:
            Change analysis (frequency, authors, etc.)
        """
        # TODO: Implement file change analysis
        raise NotImplementedError

    async def get_file_blame(
        self,
        repo_path: Path,
        file_path: str,
        ref: str = "HEAD",
    ) -> list[dict[str, Any]]:
        """
        Get blame information for a file.

        Args:
            repo_path: Repository path
            file_path: Path to file
            ref: Git reference

        Returns:
            Line-by-line blame information
        """
        return await self.git_provider.get_file_blame(repo_path, file_path, ref)

    async def compute_git_context(
        self,
        repo_path: Path,
        file_path: str,
    ) -> GitContext:
        """
        Compute git context for a file.

        Extracts:
        - Last modified timestamp
        - Last author
        - Change frequency
        - All contributors

        Args:
            repo_path: Repository path
            file_path: Path to file

        Returns:
            Git context
        """
        # TODO: Implement git context computation
        raise NotImplementedError

    async def get_pr_changes(
        self,
        repo_path: Path,
        pr_number: int,
    ) -> list[str]:
        """
        Get files changed in a pull request.

        Args:
            repo_path: Repository path
            pr_number: PR number

        Returns:
            List of changed file paths
        """
        # TODO: Implement PR change detection
        raise NotImplementedError

    async def list_branches(self, repo_path: Path) -> list[str]:
        """
        List all branches in repository.

        Args:
            repo_path: Repository path

        Returns:
            List of branch names
        """
        return await self.git_provider.list_branches(repo_path)
