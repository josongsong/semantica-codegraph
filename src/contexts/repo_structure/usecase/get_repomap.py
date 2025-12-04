"""
Get RepoMap UseCase

RepoMap 조회
"""

from ..domain.models import RepoMap
from ..domain.ports import RepoMapStorePort


class GetRepoMapUseCase:
    """RepoMap 조회 UseCase"""

    def __init__(self, repomap_store: RepoMapStorePort):
        """
        초기화

        Args:
            repomap_store: RepoMap 저장소
        """
        self.repomap_store = repomap_store

    async def execute(self, repo_id: str) -> RepoMap | None:
        """
        RepoMap 조회

        Args:
            repo_id: 리포지토리 ID

        Returns:
            RepoMap (없으면 None)
        """
        repomap = await self.repomap_store.load(repo_id)
        return repomap
