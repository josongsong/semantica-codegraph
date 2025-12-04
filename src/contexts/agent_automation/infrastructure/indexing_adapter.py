"""
Incremental Indexing Adapter

Agent → Indexing 시스템 연결을 위한 Adapter.
IncrementalIndexingPort를 구현하여 IndexJobOrchestrator를 래핑합니다.

L10 Engineering Standards:
- Observability: 모든 백그라운드 태스크 메트릭 수집
- Resource Management: 백그라운드 태스크 제한 및 타임아웃
- Error Handling: 일관된 Job 상태 관리 (Orchestrator 통한 업데이트)
- Performance: 효율적인 대기 메커니즘 (exponential backoff)
- Thread Safety: 동시 접근 보호
"""

import asyncio
from pathlib import Path
from typing import Any

from src.common.observability import get_logger
from src.contexts.agent_automation.domain.ports import IncrementalIndexingPort, IncrementalIndexingResult
from src.contexts.agent_automation.infrastructure.repo_registry import RepoRegistry
from src.contexts.analysis_indexing.infrastructure.job_orchestrator import IndexJobOrchestrator
from src.contexts.analysis_indexing.infrastructure.models.job import IndexJob, JobStatus, TriggerType
from src.infra.observability import record_counter, record_gauge

logger = get_logger(__name__)


class IncrementalIndexingAdapter(IncrementalIndexingPort):
    """
    증분 인덱싱 Adapter.

    Agent에서 파일 변경 후 자동 재인덱싱을 위한 Adapter.
    IndexJobOrchestrator를 래핑하여 파일 단위 증분 인덱싱을 수행합니다.

    Architecture:
        AgentOrchestrator → IncrementalIndexingAdapter → IndexJobOrchestrator
                                                        → IndexingOrchestrator._index_single_file()
    """

    def __init__(
        self,
        job_orchestrator: IndexJobOrchestrator,
        repo_registry: RepoRegistry,
        max_background_tasks: int = 50,  # L10: Resource limit
        background_task_timeout: float = 1800.0,  # L10: 30분 타임아웃
    ):
        """
        Initialize adapter.

        Args:
            job_orchestrator: IndexJobOrchestrator 인스턴스
            repo_registry: RepoRegistry for repo_id → path 매핑
            max_background_tasks: 최대 동시 백그라운드 태스크 수 (L10: Resource limit)
            background_task_timeout: 백그라운드 태스크 타임아웃 (초) (L10: Deadlock 방지)
        """
        self.job_orchestrator = job_orchestrator
        self.repo_registry = repo_registry
        self.max_background_tasks = max_background_tasks
        self.background_task_timeout = background_task_timeout

        # Background task tracking (for proper lifecycle management)
        # L10: Thread-safe set (asyncio tasks are thread-safe for add/discard)
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._background_tasks_lock = asyncio.Lock()  # L10: 동시 접근 보호

    async def index_files(
        self,
        repo_id: str,
        snapshot_id: str,
        file_paths: list[str],
        reason: str | None = None,
        priority: int = 0,
        head_sha: str | None = None,
        execute_immediately: bool = True,  # NEW: 즉시 실행 여부
    ) -> IncrementalIndexingResult:
        """
        파일 목록 증분 인덱싱.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID (branch/worktree)
            file_paths: 인덱싱할 파일 경로 리스트
            reason: 인덱싱 트리거 사유 (e.g., "agent_apply")
            priority: Job 우선순위 (0=normal, 1=high)
            head_sha: Git HEAD SHA (optional)
            execute_immediately: True면 백그라운드에서 즉시 실행 (default: True)

        Returns:
            IncrementalIndexingResult with status and metrics
        """
        if not file_paths:
            logger.debug("no_files_to_index")
            return IncrementalIndexingResult(
                status="not_triggered",
                indexed_count=0,
                total_files=0,
                errors=[],
            )

        logger.info(
            "indexing_files_requested",
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            file_count=len(file_paths),
            reason=reason,
        )

        try:
            # Resolve repo_path from repo_id
            repo_path = self.repo_registry.get_path(repo_id)

            # Map reason to TriggerType
            if reason == "agent_apply":
                trigger_type = TriggerType.FS_EVENT  # Agent changes are file system events
            else:
                trigger_type = TriggerType.MANUAL

            # Submit job to queue (저장용, repo_path는 DB에 저장 안 됨)
            job = await self.job_orchestrator.submit_job(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
                repo_path=repo_path,  # RepoRegistry에서 조회한 경로
                trigger_type=trigger_type,
                trigger_metadata={
                    "reason": reason or "agent_apply",
                    "priority": priority,
                    "head_sha": head_sha,
                    "file_count": len(file_paths),
                },
                scope_paths=file_paths,
                incremental=True,
            )

            logger.info("indexing_job_submitted", job_id=job.id[:8], status=job.status.value)

            # L10: Status 초기화 (명확한 변수 스코프)
            status = "success"  # 기본값: 정상 제출

            # 즉시 실행 모드: 백그라운드 태스크로 Job 실행
            if execute_immediately and job.status == JobStatus.QUEUED:
                # L10: Resource limit 체크
                async with self._background_tasks_lock:
                    active_count = self.get_active_task_count()
                    if active_count >= self.max_background_tasks:
                        logger.warning(
                            "background_tasks_limit_reached",
                            active=active_count,
                            max=self.max_background_tasks,
                            job_id=job.id[:8],
                        )
                        record_counter(
                            "incremental_indexing_background_tasks_limit_reached_total",
                            labels={"repo_id": repo_id},
                        )
                        # Job은 QUEUED 상태로 남겨두고, 나중에 worker가 처리
                        status = "queued"  # 리소스 부족으로 대기 중
                    else:
                        # 백그라운드에서 비동기로 실행 (non-blocking)
                        task = asyncio.create_task(self._execute_job_background_with_timeout(job.id, repo_path))

                        # CRITICAL: Task 추적 및 메모리 누수 방지
                        self._background_tasks.add(task)
                        task.add_done_callback(self._background_tasks.discard)

                        # L10: Observability - 메트릭 수집
                        record_gauge(
                            "incremental_indexing_background_tasks_active",
                            value=active_count + 1,
                            labels={"repo_id": repo_id},
                        )
                        record_counter(
                            "incremental_indexing_background_tasks_started_total",
                            labels={"repo_id": repo_id},
                        )

                        logger.debug("job_execution_scheduled", job_id=job.id[:8])
                        status = "success"  # 정상 스케줄링

            # Job 상태에 따라 결과 반환
            if job.status == JobStatus.DEDUPED:
                # 중복 제거됨 = 다른 job이 처리 중
                status = "partial_success"
                logger.debug("job_deduped", job_id=job.id[:8])
            elif job.status == JobStatus.SUPERSEDED:
                # 대체됨 = 더 최신 job이 처리
                status = "partial_success"
                logger.debug("job_superseded", job_id=job.id[:8])

            # Job이 큐에 들어감 (실제 인덱싱은 비동기 처리)
            return IncrementalIndexingResult(
                status=status,
                indexed_count=0,  # 아직 인덱싱 시작 안 함
                total_files=len(file_paths),
                errors=[],
            )

        except Exception as e:
            logger.error(
                "indexing_failed",
                repo_id=repo_id,
                error=str(e),
                exc_info=True,
            )
            return IncrementalIndexingResult(
                status="failed",
                indexed_count=0,
                total_files=len(file_paths),
                errors=[{"error": str(e)}],
            )

    async def _execute_job_background_with_timeout(self, job_id: str, repo_path: Path) -> None:
        """
        백그라운드에서 Job 실행 (타임아웃 포함).

        L10 Engineering:
        - 타임아웃으로 무한 대기 방지
        - 에러 처리 및 메트릭 수집
        - Job 상태 일관성 보장 (Orchestrator 통한 업데이트)

        Args:
            job_id: Job ID
            repo_path: Repository path
        """
        start_time = asyncio.get_event_loop().time()
        try:
            logger.info("executing_job_background", job_id=job_id[:8])
            # L10: 타임아웃으로 무한 대기 방지
            # wait_for는 타임아웃 시 자동으로 태스크를 취소함
            await asyncio.wait_for(
                self.job_orchestrator.execute_job(job_id, repo_path),
                timeout=self.background_task_timeout,
            )
            duration = asyncio.get_event_loop().time() - start_time
            logger.info("job_completed", job_id=job_id[:8], duration_seconds=f"{duration:.2f}")
            record_counter(
                "incremental_indexing_background_tasks_completed_total",
                labels={"status": "success"},
            )
            record_gauge(
                "incremental_indexing_background_tasks_duration_seconds",
                value=duration,
            )
        except asyncio.TimeoutError:
            duration = asyncio.get_event_loop().time() - start_time
            error_msg = f"Job execution timeout after {duration:.2f}s"
            logger.error(
                "job_execution_timeout",
                job_id=job_id[:8],
                timeout=self.background_task_timeout,
                duration=duration,
            )
            record_counter(
                "incremental_indexing_background_tasks_completed_total",
                labels={"status": "timeout"},
            )
            await self._handle_job_failure(job_id, error_msg)
        except Exception as e:
            duration = asyncio.get_event_loop().time() - start_time
            logger.error(
                "job_execution_failed",
                job_id=job_id[:8],
                error=str(e),
                duration=duration,
                exc_info=True,
            )
            record_counter(
                "incremental_indexing_background_tasks_completed_total",
                labels={"status": "error"},
            )
            await self._handle_job_failure(job_id, str(e))
        finally:
            # L10: Observability - 활성 태스크 수 업데이트
            async with self._background_tasks_lock:
                active_count = self.get_active_task_count()
                record_gauge(
                    "incremental_indexing_background_tasks_active",
                    value=active_count,
                )

    async def _handle_job_failure(self, job_id: str, error_message: str) -> None:
        """
        Job 실패 처리.

        L10 Engineering:
        - Orchestrator를 통한 일관된 상태 업데이트 시도
        - 실패 시 직접 DB 업데이트 (fallback)
        - 모든 실패 케이스 로깅 및 메트릭 수집

        Args:
            job_id: Job ID
            error_message: Error message
        """
        # L10: Orchestrator를 통한 일관된 상태 업데이트 시도
        # Note: _update_job은 private이지만, 같은 패키지에서 접근 가능
        # 더 나은 방법: 직접 DB 업데이트 (fallback으로만 사용)
        orchestrator_error: Exception | None = None
        try:
            # Job을 로드하여 상태 확인
            job = await self.job_orchestrator.get_job(job_id)
            if job:
                # L10: Orchestrator의 내부 메서드 사용 (같은 패키지이므로 접근 가능)
                # 하지만 더 안전한 방법은 직접 DB 업데이트
                job.status = JobStatus.FAILED
                job.status_reason = error_message
                # Private 메서드이지만 같은 패키지에서 접근 가능
                # type: ignore[attr-defined] - private 메서드 접근
                await self.job_orchestrator._update_job(job)  # noqa: SLF001
                logger.info("job_status_updated_via_orchestrator", job_id=job_id[:8])
                return
        except Exception as e:
            orchestrator_error = e
            logger.warning(
                "failed_to_update_via_orchestrator",
                job_id=job_id[:8],
                error=str(e),
            )

        # Fallback: 직접 DB 업데이트
        try:
            await self._mark_job_failed_direct(job_id, error_message)
        except Exception as update_error:
            # L10: Critical - 모든 수단 실패 시에도 로깅
            logger.error(
                "failed_to_update_job_status_all_methods",
                job_id=job_id[:8],
                orchestrator_error=str(orchestrator_error) if orchestrator_error else None,
                direct_error=str(update_error),
                exc_info=True,
            )
            record_counter(
                "incremental_indexing_job_status_update_failed_total",
            )

    async def _mark_job_failed_direct(self, job_id: str, error_message: str) -> None:
        """
        Job을 failed 상태로 직접 마킹 (fallback 메서드).

        L10 Engineering:
        - Orchestrator를 통한 업데이트가 실패한 경우에만 사용
        - 직접 DB 업데이트는 최후의 수단

        Args:
            job_id: Job ID
            error_message: Error message
        """
        query = """
        UPDATE index_jobs
        SET status = 'failed',
            status_reason = $2,
            finished_at = NOW()
        WHERE id = $1
        """

        await self.job_orchestrator.postgres.execute(query, job_id, error_message)

    async def wait_until_idle(
        self,
        repo_id: str,
        snapshot_id: str,
        timeout: float = 5.0,
    ) -> bool:
        """
        인덱싱 완료 대기 (L10: Exponential Backoff).

        현재 진행 중인 인덱싱 작업이 완료될 때까지 대기합니다.

        L10 Engineering:
        - Exponential backoff로 DB 부하 감소
        - 초기 빠른 응답, 이후 점진적 간격 증가
        - 타임아웃 정확도 향상

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            timeout: Timeout in seconds

        Returns:
            True if idle, False if timeout
        """
        start_time = asyncio.get_event_loop().time()
        poll_interval = 0.05  # 초기 50ms
        max_poll_interval = 0.5  # 최대 500ms
        poll_count = 0

        while True:
            # Check if there are running jobs for this repo+snapshot
            jobs = await self.job_orchestrator.list_jobs(
                repo_id=repo_id,
                snapshot_id=snapshot_id,
            )

            # Filter running jobs
            running_jobs = [j for j in jobs if j.status in (JobStatus.RUNNING, JobStatus.QUEUED)]

            if not running_jobs:
                logger.debug("indexing_idle", repo_id=repo_id, snapshot_id=snapshot_id)
                record_gauge(
                    "incremental_indexing_wait_polls_total",
                    value=poll_count,
                    labels={"repo_id": repo_id, "result": "success"},
                )
                return True

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                logger.warning(
                    "wait_timeout",
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    running=len(running_jobs),
                    polls=poll_count,
                )
                record_gauge(
                    "incremental_indexing_wait_polls_total",
                    value=poll_count,
                    labels={"repo_id": repo_id, "result": "timeout"},
                )
                return False

            # L10: Exponential backoff (최대 간격 제한)
            await asyncio.sleep(poll_interval)
            poll_count += 1
            poll_interval = min(poll_interval * 1.5, max_poll_interval)  # 1.5배씩 증가, 최대 500ms

    async def cancel_all_tasks(self) -> int:
        """
        모든 백그라운드 태스크 취소.

        L10 Engineering:
        - Thread-safe 취소
        - 모든 태스크 완료 대기
        - 메트릭 업데이트

        Returns:
            취소된 태스크 개수
        """
        async with self._background_tasks_lock:
            if not self._background_tasks:
                return 0

            cancelled_count = 0
            tasks_to_cancel = []
            for task in self._background_tasks:
                if not task.done():
                    task.cancel()
                    tasks_to_cancel.append(task)
                    cancelled_count += 1

            # 모든 취소된 태스크 완료 대기
            if tasks_to_cancel:
                await asyncio.gather(*tasks_to_cancel, return_exceptions=True)

            logger.info("background_tasks_cancelled", count=cancelled_count)
            record_counter(
                "incremental_indexing_background_tasks_cancelled_total",
                value=cancelled_count,
            )
            record_gauge("incremental_indexing_background_tasks_active", value=0)
            return cancelled_count

    def get_active_task_count(self) -> int:
        """
        실행 중인 백그라운드 태스크 개수.

        L10 Engineering:
        - Lock 없이 호출 가능 (읽기 전용)
        - 정확도보다 성능 우선 (메트릭용)
        - 주의: 동시 수정 시 약간의 부정확 가능 (허용 가능)

        Returns:
            활성 태스크 개수
        """
        # Lock 없이 읽기 (성능 우선)
        # 동시 수정 시 약간의 부정확 가능하지만 메트릭용이므로 허용
        return len([t for t in self._background_tasks if not t.done()])
