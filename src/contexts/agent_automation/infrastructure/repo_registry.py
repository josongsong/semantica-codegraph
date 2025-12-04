"""
Repository Registry

repo_id → repo_path 매핑을 관리하는 레지스트리.
Multi-repo 환경 지원.
"""

from pathlib import Path

from src.common.observability import get_logger

logger = get_logger(__name__)


class RepoRegistry:
    """
    Repository ID to Path 매핑 레지스트리.

    Multi-repo 환경에서 repo_id만으로 실제 경로를 찾을 수 있게 합니다.

    Usage:
        registry = RepoRegistry()
        registry.register("project-a", "/path/to/project-a")
        registry.register("project-b", "/path/to/project-b")

        path = registry.get_path("project-a")  # /path/to/project-a
    """

    def __init__(self, default_workspace_path: str | Path | None = None):
        """
        Initialize registry.

        Args:
            default_workspace_path: Default workspace path (backward compatibility)
        """
        self._repos: dict[str, Path] = {}
        self._default_path = Path(default_workspace_path) if default_workspace_path else None

    def register(self, repo_id: str, repo_path: str | Path) -> None:
        """
        Register a repository.

        Args:
            repo_id: Repository identifier
            repo_path: Path to repository
        """
        path = Path(repo_path).resolve()
        self._repos[repo_id] = path
        logger.debug("repo_registered", repo_id=repo_id, repo_path=str(path))

    def get_path(self, repo_id: str) -> Path:
        """
        Get repository path by ID.

        Args:
            repo_id: Repository identifier

        Returns:
            Path to repository

        Raises:
            KeyError: If repo_id not registered and no default path
        """
        if repo_id in self._repos:
            return self._repos[repo_id]

        # Fallback: default workspace path (단일 repo 환경)
        if self._default_path:
            logger.debug(
                "using_default_workspace_path",
                repo_id=repo_id,
                default_path=str(self._default_path),
            )
            return self._default_path

        raise KeyError(
            f"Repository '{repo_id}' not registered and no default workspace path. "
            f"Call registry.register('{repo_id}', '/path/to/repo')"
        )

    def get_path_safe(self, repo_id: str) -> Path | None:
        """
        Get repository path safely (returns None if not found).

        Args:
            repo_id: Repository identifier

        Returns:
            Path to repository or None
        """
        try:
            return self.get_path(repo_id)
        except KeyError:
            return None

    def is_registered(self, repo_id: str) -> bool:
        """Check if repository is registered."""
        return repo_id in self._repos or self._default_path is not None

    def list_repos(self) -> dict[str, Path]:
        """Get all registered repositories."""
        return self._repos.copy()

    def unregister(self, repo_id: str) -> bool:
        """
        Unregister a repository.

        Args:
            repo_id: Repository identifier

        Returns:
            True if removed, False if not found
        """
        if repo_id in self._repos:
            del self._repos[repo_id]
            logger.debug("repo_unregistered", repo_id=repo_id)
            return True
        return False
