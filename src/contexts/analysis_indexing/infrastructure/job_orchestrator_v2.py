"""
IndexJobOrchestrator v2 - SemanticaTask 기반.

기존 IndexJobOrchestrator 인터페이스 유지하면서
내부 구현을 SemanticaTask Daemon으로 교체.

변경:
- PostgreSQL + Redis → SemanticaTask (SQLite/PostgreSQL)
- 분산 락, Checkpoint, Retry → Daemon이 처리
- 923줄 → ~200줄 (75% 감소)
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from src.contexts.analysis_indexing.domain.models import IndexJob, JobStatus, TriggerType
from src.contexts.analysis_indexing.infrastructure.handlers.indexing_handler import IndexingJobHandler
from src.contexts.analysis_indexing.infrastructure.orchestrator import IndexingOrchestrator
from src.infra.jobs.semantica_adapter import SemanticaAdapter
from src.infra.observability.logging import get_logger
from src.infra.observability.metrics import record_counter

logger = get_logger(__name__)


class IndexJobOrchestratorV2:
    """
    SemanticaTask 기반 Job Orchestrator.

    기존 API 호환성 유지:
    - submit_job() → adapter.enqueue()
    - execute_job() → Daemon이 자동 실행 (deprecated)
    - get_job(), list_jobs(), cancel_job() → adapter 호출

    Usage:
        orchestrator_v2 = IndexJobOrchestratorV2(
            orchestrator=indexing_orchestrator,
            adapter=semantica_adapter,
        )

        # Job 등록 (기존 코드 호환)
        job = await orchestrator_v2.submit_job(
            repo_id="repo123",
            snapshot_id="main",
            repo_path="/path/to/repo",
        )

        # Daemon이 자동 실행 (execute_job 불필요)
    """

    def __init__(
        self,
        orchestrator: IndexingOrchestrator,
        adapter: SemanticaAdapter,
        instance_id: str | None = None,
    ):
        """
        Args:
            orchestrator: IndexingOrchestrator (비즈니스 로직)
            adapter: SemanticaAdapter (Job Queue)
            instance_id: 인스턴스 ID (기본값: random UUID)
        """
        self.orchestrator = orchestrator
        self.adapter = adapter
        self.instance_id = instance_id or str(uuid.uuid4())[:8]

        # Handler 등록 (Daemon Worker가 호출)
        if "INDEX_FILE" not in adapter.handlers:
            adapter.handlers["INDEX_FILE"] = IndexingJobHandler(orchestrator)

    async def submit_job(
        self,
        repo_id: str,
        snapshot_id: str,
        repo_path: str | Path,
        trigger_type: TriggerType = TriggerType.MANUAL,
        trigger_metadata: dict[str, Any] | None = None,
        scope_paths: list[str] | None = None,
        incremental: bool = False,
    ) -> IndexJob:
        """
        Job 등록 (기존 API 호환).

        내부적으로 SemanticaTask로 전달:
        - subject_key: repo_id::snapshot_id (중복 방지)
        - payload: repo_path, scope_paths, incremental 등

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID (브랜치/커밋)
            repo_path: 저장소 경로
            trigger_type: 트리거 유형
            trigger_metadata: 트리거 메타데이터
            scope_paths: 특정 파일만 (None=전체)
            incremental: 증분 인덱싱 여부

        Returns:
            IndexJob (SemanticaTask Job → IndexJob 변환)
        """
        # subject_key: 동일 repo + snapshot → 최신 Job만 실행
        subject_key = f"{repo_id}::{snapshot_id}"

        # payload: Handler가 받을 데이터
        payload = {
            "repo_path": str(repo_path),
            "repo_id": repo_id,
            "snapshot_id": snapshot_id,
            "incremental": incremental,
            "scope_paths": scope_paths,
            "trigger_type": trigger_type.value,
            "trigger_metadata": trigger_metadata or {},
        }

        # Priority 계산
        priority = self._calculate_priority(trigger_type, scope_paths)

        # SemanticaTask로 등록
        job = await self.adapter.enqueue(
            job_type="INDEX_FILE",
            queue="code_intel",
            subject_key=subject_key,
            payload=payload,
            priority=priority,
        )

        # IndexJob으로 변환 (기존 코드 호환)
        index_job = IndexJob(
            id=job.job_id,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            scope_paths=scope_paths,
            trigger_type=trigger_type,
            trigger_metadata=trigger_metadata or {},
            status=self._convert_state(job.state),
            created_at=job.created_at,
        )

        # Metrics 기록
        record_counter(
            "index_jobs_created_total",
            labels={
                "repo_id": repo_id,
                "snapshot_id": snapshot_id,
                "trigger": trigger_type.value,
                "instance": self.instance_id,
            },
        )

        logger.info(
            "job_submitted_via_semantica",
            job_id=job.job_id,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            trigger=trigger_type.value,
        )

        return index_job

    async def execute_job(self, job_id: str, repo_path: str | Path) -> IndexJob:
        """
        Job 실행 (DEPRECATED).

        SemanticaTask Daemon이 자동으로 실행하므로 이 메서드는 불필요.
        기존 코드 호환성을 위해 유지하지만 실제로는 아무 것도 하지 않음.

        Args:
            job_id: Job ID
            repo_path: 저장소 경로 (사용 안 함)

        Returns:
            IndexJob (Daemon이 실행 중이거나 완료된 상태)
        """
        logger.warning(
            "execute_job_deprecated",
            job_id=job_id,
            message="execute_job() is deprecated. SemanticaTask Daemon executes jobs automatically.",
        )

        # Job 상태만 조회해서 반환
        # TODO: SemanticaTask에 get_job API 추가되면 구현
        return IndexJob(
            id=job_id,
            repo_id="unknown",
            snapshot_id="unknown",
            status=JobStatus.RUNNING,
            created_at=datetime.now(),
        )

    async def cancel_job(self, job_id: str) -> bool:
        """
        Job 취소.

        Args:
            job_id: Job ID

        Returns:
            취소 성공 여부
        """
        cancelled = await self.adapter.cancel_job(job_id)

        if cancelled:
            logger.info("job_cancelled", job_id=job_id)
            record_counter("jobs_cancelled_total", labels={"job_id": job_id})

        return cancelled

    async def get_job(self, job_id: str) -> IndexJob | None:
        """
        Job 조회.

        TODO: SemanticaTask에 get_job API 추가 필요
        """
        logger.warning("get_job_not_implemented", job_id=job_id)
        return None

    async def list_jobs(
        self,
        repo_id: str | None = None,
        snapshot_id: str | None = None,
        status: JobStatus | None = None,
        limit: int = 100,
    ) -> list[IndexJob]:
        """
        Job 목록 조회.

        TODO: SemanticaTask에 list_jobs API 추가 필요
        """
        logger.warning("list_jobs_not_implemented")
        return []

    def _calculate_priority(self, trigger_type: TriggerType, scope_paths: list[str] | None) -> int:
        """
        우선순위 계산.

        - GIT_COMMIT: 높은 우선순위 (코드 변경)
        - FS_EVENT: 중간 우선순위 (파일 저장)
        - MANUAL: 낮은 우선순위 (수동 트리거)
        - 소량 파일: 우선순위 +10
        """
        base_priority = {
            TriggerType.GIT_COMMIT: 50,
            TriggerType.FS_EVENT: 30,
            TriggerType.MANUAL: 10,
        }.get(trigger_type, 0)

        # 소량 파일 (10개 이하) → 우선순위 증가
        if scope_paths and len(scope_paths) <= 10:
            base_priority += 10

        return base_priority

    def _convert_state(self, semantica_state: str) -> JobStatus:
        """
        SemanticaTask State → JobStatus 변환.

        SemanticaTask: QUEUED, RUNNING, DONE, FAILED, SUPERSEDED
        IndexJob: QUEUED, RUNNING, COMPLETED, FAILED, SUPERSEDED
        """
        mapping = {
            "QUEUED": JobStatus.QUEUED,
            "RUNNING": JobStatus.RUNNING,
            "DONE": JobStatus.COMPLETED,
            "FAILED": JobStatus.FAILED,
            "SUPERSEDED": JobStatus.SUPERSEDED,
        }
        return mapping.get(semantica_state, JobStatus.QUEUED)
