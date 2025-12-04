"""
Index Repository Full UseCase

전체 리포지토리 인덱싱
"""

from pathlib import Path

from ..domain.models import IndexingResult


class IndexRepositoryFullUseCase:
    """전체 리포지토리 인덱싱 UseCase"""

    def __init__(self, orchestrator):
        """
        초기화

        Args:
            orchestrator: IndexingOrchestrator (실제 구현체)
        """
        self.orchestrator = orchestrator

    async def execute(
        self,
        repo_id: str,
        repo_path: str | Path,
        snapshot_id: str = "main",
        force: bool = False,
    ) -> IndexingResult:
        """
        전체 인덱싱 실행

        Args:
            repo_id: 리포지토리 ID
            repo_path: 리포지토리 경로
            snapshot_id: 스냅샷 ID
            force: 강제 재인덱싱 여부

        Returns:
            인덱싱 결과
        """
        # 실제 오케스트레이터 호출
        result = await self.orchestrator.index_repository_full(
            repo_path=repo_path,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            force=force,
        )

        # 기존 결과를 도메인 모델로 변환
        from ..domain.models import IndexingStatus

        return IndexingResult(
            repo_id=result.repo_id,
            snapshot_id=result.snapshot_id,
            status=IndexingStatus(result.status.value),
            files_processed=result.files_processed,
            files_failed=result.files_failed,
            graph_nodes_created=result.graph_nodes_created,
            graph_edges_created=result.graph_edges_created,
            chunks_created=result.chunks_created,
            total_duration_seconds=result.total_duration_seconds,
            errors=result.errors or [],
        )
