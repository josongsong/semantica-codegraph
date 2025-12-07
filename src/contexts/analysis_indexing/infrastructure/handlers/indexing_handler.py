"""
IndexingJobHandler - 인덱싱 비즈니스 로직 실행.

강결합 제거: Job Queue ↔ IndexingOrchestrator 분리
"""

from pathlib import Path
from typing import Any

from src.contexts.analysis_indexing.infrastructure.orchestrator import IndexingOrchestrator
from src.infra.jobs.handler import JobResult
from src.infra.observability.logging import get_logger

logger = get_logger(__name__)


class IndexingJobHandler:
    """
    INDEX_FILE Job 실행 Handler.

    Payload 스펙:
        {
            "repo_path": str,      # 저장소 경로
            "repo_id": str,        # 저장소 ID
            "snapshot_id": str,    # 스냅샷 ID (브랜치/커밋)
            "incremental": bool,   # 증분 인덱싱 여부 (선택, 기본값: False)
            "scope_paths": list[str] | None  # 특정 파일만 (선택)
        }

    Example:
        handler = IndexingJobHandler(orchestrator)
        result = await handler.execute({
            "repo_path": "/path/to/repo",
            "repo_id": "my-repo",
            "snapshot_id": "main",
            "incremental": True
        })
    """

    def __init__(self, orchestrator: IndexingOrchestrator):
        """
        Args:
            orchestrator: IndexingOrchestrator 인스턴스 (DI)
        """
        self.orchestrator = orchestrator

    async def execute(self, payload: dict[str, Any]) -> JobResult:
        """
        인덱싱 Job 실행.

        Args:
            payload: Job payload (위 스펙 참고)

        Returns:
            JobResult (성공/실패 + 결과 데이터)
        """
        try:
            # Payload 검증
            repo_path = payload.get("repo_path")
            repo_id = payload.get("repo_id")
            snapshot_id = payload.get("snapshot_id")

            if not all([repo_path, repo_id, snapshot_id]):
                return JobResult.fail(
                    error="Missing required fields: repo_path, repo_id, snapshot_id",
                    data={"payload": payload},
                )

            # 인덱싱 실행
            incremental = payload.get("incremental", False)

            logger.info(
                "indexing_job_started",
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                incremental=incremental,
            )

            result = await self.orchestrator.index_repository(
                repo_path=Path(repo_path),
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                incremental=incremental,
            )

            # 결과 반환
            return JobResult.ok(
                data={
                    "files_processed": result.files_processed,
                    "chunks_created": result.chunks_created,
                    "errors": [str(e) for e in result.errors] if hasattr(result, "errors") else [],
                }
            )

        except Exception as e:
            logger.error(
                "indexing_job_failed",
                error=str(e),
                payload=payload,
                exc_info=True,
            )
            return JobResult.fail(error=str(e), data={"payload": payload})
