"""
JobHandler Protocol - 비즈니스 로직 실행 인터페이스.

강결합 제거:
- Job Queue (인프라) ↔ Handler (도메인) 분리
- SemanticaTask와 호환 가능한 추상화
"""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class JobResult:
    """
    Handler 실행 결과.

    성공/실패 여부 + 결과 데이터 + 에러 정보.
    """

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None

    @classmethod
    def ok(cls, data: dict[str, Any] | None = None) -> "JobResult":
        """성공 결과."""
        return cls(success=True, data=data or {})

    @classmethod
    def fail(cls, error: str, data: dict[str, Any] | None = None) -> "JobResult":
        """실패 결과."""
        return cls(success=False, data=data, error=error)


class JobHandler(Protocol):
    """
    Job Handler 인터페이스.

    각 job_type별로 Handler 구현체를 만들어 등록:
    - INDEX_FILE → IndexingJobHandler
    - EMBED_CHUNK → EmbeddingJobHandler
    - ANALYZE_CODE → AnalysisJobHandler

    Example:
        class IndexingJobHandler:
            def __init__(self, orchestrator: IndexingOrchestrator):
                self.orchestrator = orchestrator

            async def execute(self, payload: dict) -> JobResult:
                result = await self.orchestrator.index_repository(
                    repo_path=payload["repo_path"],
                    repo_id=payload["repo_id"],
                )
                return JobResult.ok({"files_processed": result.files_processed})
    """

    async def execute(self, payload: dict[str, Any]) -> JobResult:
        """
        Job 실행.

        Args:
            payload: Job의 payload 데이터 (dict)

        Returns:
            JobResult (성공/실패 + 데이터)

        Raises:
            Exception은 상위에서 처리 (자동 FAILED 전환)
        """
        ...
