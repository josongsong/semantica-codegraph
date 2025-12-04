"""
Build RepoMap UseCase
"""

from pathlib import Path

from ..domain.models import RepoMap
from ..domain.ports import RepoMapBuilderPort


class BuildRepoMapUseCase:
    """RepoMap 빌드 UseCase"""

    def __init__(self, builder: RepoMapBuilderPort):
        self.builder = builder

    async def execute(self, repo_path: Path, repo_id: str) -> RepoMap:
        """RepoMap 빌드"""
        return await self.builder.build(repo_path, repo_id)
