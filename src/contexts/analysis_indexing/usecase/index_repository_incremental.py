"""
Index Repository Incremental UseCase

증분 리포지토리 인덱싱
"""

from pathlib import Path

from ..domain.ports import IndexingOrchestratorPort
from ..infrastructure.models import IndexingResult


class IndexRepositoryIncrementalUseCase:
    """증분 리포지토리 인덱싱 UseCase"""

    def __init__(self, orchestrator: IndexingOrchestratorPort):
        """
        초기화

        Args:
            orchestrator: 인덱싱 오케스트레이터 포트
        """
        self.orchestrator = orchestrator

    async def execute(
        self,
        repo_id: str,
        repo_path: str | Path,
        snapshot_id: str = "main",
    ) -> IndexingResult:
        """
        증분 인덱싱 실행

        Args:
            repo_id: 리포지토리 ID
            repo_path: 리포지토리 경로
            snapshot_id: 스냅샷 ID

        Returns:
            Infrastructure IndexingResult (정보 손실 없음)

        Note: 변경된 파일은 Orchestrator가 자동으로 감지합니다.
        """
        # 포트를 통해 오케스트레이터 호출 - Infrastructure 모델 직접 반환
        return await self.orchestrator.index_repository_incremental(
            repo_path=repo_path,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
        )
