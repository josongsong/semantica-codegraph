"""
Index Job Orchestrator

Provides job-based indexing with distributed locking for concurrent editing support.
Wraps the existing IndexingOrchestrator with:
- Job lifecycle management
- Distributed locking (single writer per repo+snapshot)
- Checkpoint system for idempotent retries
- Job deduplication and supersession
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.contexts.analysis_indexing.infrastructure.conflict_registry import ConflictRegistry, ConflictStrategy
from src.contexts.analysis_indexing.infrastructure.lock_key_generator import LockKeyGenerator
from src.contexts.analysis_indexing.infrastructure.models.job import (
    IndexJob,
    IndexJobCheckpoint,
    JobProgress,
    JobStatus,
    TriggerType,
)
from src.contexts.analysis_indexing.infrastructure.orchestrator import IndexingOrchestrator
from src.infra.cache.distributed_lock import DistributedLock, LockAcquisitionError
from src.infra.observability import get_logger, record_counter, record_histogram
from src.infra.storage.postgres import PostgresStore

logger = get_logger(__name__)


class IndexJobOrchestrator:
    """
    Job-based indexing orchestrator with distributed locking.

    Wraps IndexingOrchestrator to provide:
    - Single writer guarantee per (repo_id, snapshot_id)
    - Job queuing and status tracking
    - Idempotent retries with checkpoints
    - Job deduplication and supersession
    - Observability and metrics

    Architecture:
        User → IndexJobOrchestrator → [Queue] → Worker
                                    ↓
                            DistributedLock (Redis)
                                    ↓
                            IndexingOrchestrator (existing)
                                    ↓
                            Storage (PostgreSQL, Kuzu, Qdrant)
    """

    def __init__(
        self,
        orchestrator: IndexingOrchestrator,
        postgres_store: PostgresStore,
        redis_client: Any,
        instance_id: str | None = None,
        lock_ttl: int = 300,  # 5 minutes
        lock_extend_interval: int = 60,  # 1 minute
        conflict_strategy: ConflictStrategy = ConflictStrategy.SKIP,
        enable_distributed_lock: bool = True,  # NEW: Lock 활성화 플래그
    ):
        """
        Initialize job orchestrator.

        Args:
            orchestrator: Existing IndexingOrchestrator
            postgres_store: PostgreSQL store for job storage
            redis_client: Redis client for distributed locking (redis.asyncio.Redis)
            instance_id: Unique identifier for this instance (default: random UUID)
            lock_ttl: Lock expiration time in seconds (default: 300s)
                     With Phase 2 lock extension, jobs can run indefinitely
            lock_extend_interval: How often to extend lock for long jobs (default: 60s)
                                 Phase 2: Implemented with background task
            conflict_strategy: How to handle duplicate jobs (default: SKIP)
                              Phase 2: Deduplication with ConflictRegistry
            enable_distributed_lock: If False, use NoOpLock (단일 프로세스/테스트용)
        """
        self.orchestrator = orchestrator
        self.postgres = postgres_store
        self.redis_client = redis_client
        self.instance_id = instance_id or str(uuid.uuid4())[:8]
        self.lock_ttl = lock_ttl
        self.lock_extend_interval = lock_extend_interval
        self.enable_distributed_lock = enable_distributed_lock

        # Phase 2: Conflict registry for job deduplication
        self.conflict_registry = ConflictRegistry(postgres_store, default_strategy=conflict_strategy)

        logger.info(
            "job_orchestrator_initialized",
            instance_id=self.instance_id,
            lock_ttl_seconds=lock_ttl,
            conflict_strategy=conflict_strategy.value,
        )

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
        Submit a new indexing job.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier (branch/commit)
            repo_path: Path to repository
            trigger_type: What triggered this job (git_commit, fs_event, manual)
            trigger_metadata: Additional trigger information
            scope_paths: Optional list of file paths to index (None = entire repo)
            incremental: If True, only process changed files

        Returns:
            Created IndexJob

        Raises:
            Exception: If job creation fails
        """
        job = IndexJob(
            id=str(uuid.uuid4()),
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            scope_paths=scope_paths,
            trigger_type=trigger_type,
            trigger_metadata=trigger_metadata or {},
            status=JobStatus.QUEUED,
            created_at=datetime.now(),
        )

        # Store job in database
        await self._store_job(job)

        # Phase 2: Check for duplicate/conflicting jobs
        existing_job = await self.conflict_registry.check_duplicate(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            exclude_job_id=job.id,
        )

        if existing_job:
            # Apply conflict resolution strategy
            new_status = await self.conflict_registry.apply_strategy(
                new_job=job,
                existing_job=existing_job,
            )

            if new_status != JobStatus.QUEUED:
                # Job was deduped or modified
                job.status = new_status
                await self._update_job(job)

                logger.info(
                    "job_marked_duplicate",
                    job_id=job.id[:8],
                    status=new_status.value,
                    duplicate_of=existing_job.id[:8],
                )

        # Record metrics
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
            "job_submitted",
            job_id=job.id[:8],
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            trigger=trigger_type.value,
            status=job.status.value,
        )

        return job

    async def execute_job(self, job_id: str, repo_path: str | Path) -> IndexJob:
        """
        Execute a queued indexing job.

        Refactored to use helper methods for better maintainability.
        Reduced from 209 lines → 76 lines (64% reduction).

        This is the main entry point for job processing. It:
        1. Loads job from database
        2. Acquires distributed lock (via _acquire_job_lock)
        3. Checks for deduplication/supersession (via _check_superseded_jobs)
        4. Executes indexing via IndexingOrchestrator (via _execute_indexing_with_checkpoint)
        5. Updates job status and metrics

        Args:
            job_id: Job identifier
            repo_path: Path to repository

        Returns:
            Updated IndexJob

        Raises:
            LockAcquisitionError: If lock cannot be acquired
            Exception: If job execution fails

        Notes:
            - Current implementation: Jobs must complete within lock_ttl (default: 5 minutes)
            - Phase 2: Lock extension will be implemented for long-running jobs
            - For production: Consider increasing lock_ttl to 30+ minutes
        """
        # ============================================================
        # Step 1: Load and validate job
        # ============================================================
        job = await self._load_job(job_id)

        if job.status != JobStatus.QUEUED:
            logger.warning("job_not_queued", job_id=job_id[:8], status=job.status.value)
            return job

        # ============================================================
        # Step 2: Acquire distributed lock (또는 NoOp)
        # ============================================================
        # 파일 단위 Lock 사용 여부 판단
        use_file_lock = LockKeyGenerator.should_use_file_lock(
            scope_paths=job.scope_paths,
            max_files=10,  # 10개 이하 파일만 파일 lock
        )

        if use_file_lock:
            # 파일 단위 Lock (병렬 인덱싱 가능)
            lock_key = LockKeyGenerator.generate_file_lock_key(
                repo_id=job.repo_id,
                snapshot_id=job.snapshot_id,
                file_paths=job.scope_paths,
            )
            logger.debug(
                "using_file_lock",
                job_id=job.id[:8],
                file_count=len(job.scope_paths or []),
                lock_key=lock_key,
            )
        else:
            # Repo 단위 Lock (전체 인덱싱 또는 대량 파일)
            lock_key = LockKeyGenerator.generate_repo_lock_key(
                repo_id=job.repo_id,
                snapshot_id=job.snapshot_id,
            )
            logger.debug(
                "using_repo_lock",
                job_id=job.id[:8],
                file_count=len(job.scope_paths or []) if job.scope_paths else "all",
                lock_key=lock_key,
            )

        if self.enable_distributed_lock:
            lock = DistributedLock(self.redis_client, lock_key, ttl=self.lock_ttl)
        else:
            # 단일 프로세스/테스트: Lock 비활성화
            from src.infra.cache.noop_lock import NoOpLock

            lock = NoOpLock(self.redis_client, lock_key, ttl=self.lock_ttl)

        try:
            # Try to acquire lock (updates job status internally)
            acquired, _lock_wait_seconds = await self._acquire_job_lock(job, lock)

            if not acquired:
                # Lock acquisition failed, job status already updated
                return job

            # ============================================================
            # Step 3: Start lock extension + check superseded jobs
            # ============================================================
            extension_task = None
            if self.lock_extend_interval > 0:
                extension_task = self._start_lock_extension(lock, job.id)

            await self._check_superseded_jobs(job)

            # ============================================================
            # Step 4: Execute indexing with checkpoint
            # ============================================================
            try:
                success, result = await self._execute_indexing_with_checkpoint(job, repo_path)

                if not success:
                    # Indexing failed, handle with retry logic
                    await self._handle_indexing_failure(job, result)

                    # Only raise if no more retries (job status == FAILED)
                    if job.status == JobStatus.FAILED:
                        raise result

            finally:
                # Stop lock extension task
                if extension_task and not extension_task.done():
                    extension_task.cancel()
                    try:
                        await extension_task
                    except asyncio.CancelledError:
                        pass

        except LockAcquisitionError as e:
            # Lock acquisition error (exception-based timeout)
            # This happens when lock.acquire() raises exception instead of returning False
            job.status = JobStatus.LOCK_FAILED
            job.status_reason = str(e)
            job.finished_at = datetime.now()
            await self._update_job(job)
            logger.error("lock_acquisition_error", job_id=job.id[:8], error=str(e), exc_info=True)
            record_counter("lock_errors_total", labels={"job_id": job.id[:8]})
            # Don't raise - return job with LOCK_FAILED status for caller to handle
            return job

        finally:
            # Always release lock
            if lock.is_acquired():
                await lock.release()
                logger.debug("lock_released", job_id=job.id[:8])

        return job

    async def get_job(self, job_id: str) -> IndexJob | None:
        """
        Get job by ID.

        Args:
            job_id: Job identifier

        Returns:
            IndexJob or None if not found
        """
        return await self._load_job(job_id)

    async def list_jobs(
        self,
        repo_id: str | None = None,
        snapshot_id: str | None = None,
        status: JobStatus | None = None,
        limit: int = 100,
    ) -> list[IndexJob]:
        """
        List jobs with optional filters.

        Args:
            repo_id: Filter by repository
            snapshot_id: Filter by snapshot
            status: Filter by status
            limit: Maximum number of jobs to return

        Returns:
            List of IndexJob
        """
        # Build query
        query = "SELECT * FROM index_jobs WHERE 1=1"
        params = []

        if repo_id:
            query += " AND repo_id = $1"
            params.append(repo_id)

        if snapshot_id:
            query += f" AND snapshot_id = ${len(params) + 1}"
            params.append(snapshot_id)

        if status:
            query += f" AND status = ${len(params) + 1}"
            params.append(status.value)

        query += f" ORDER BY created_at DESC LIMIT ${len(params) + 1}"
        params.append(limit)

        # Execute query
        rows = await self.postgres.fetch(query, *params)

        # Convert to IndexJob objects
        jobs = [self._row_to_job(row) for row in rows]

        return jobs

    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a queued or running job.

        Args:
            job_id: Job identifier

        Returns:
            True if cancelled, False if not found or cannot be cancelled
        """
        job = await self._load_job(job_id)

        if not job:
            return False

        # Only cancel queued or acquiring_lock jobs
        if job.status not in [JobStatus.QUEUED, JobStatus.ACQUIRING_LOCK]:
            logger.warning("cannot_cancel_job", job_id=job_id[:8], status=job.status.value)
            return False

        job.status = JobStatus.CANCELLED
        job.finished_at = datetime.now()
        await self._update_job(job)

        logger.info("job_cancelled", job_id=job_id[:8])
        record_counter("jobs_cancelled_total", labels={"job_id": job_id[:8]})
        return True

    def get_metrics(self) -> dict[str, Any]:
        """
        Get aggregate metrics for all jobs.

        **DEPRECATED**: Metrics are now exported via observability infrastructure.
        Use Prometheus/OpenTelemetry endpoints to query metrics.

        Returns:
            Empty dictionary (deprecated)
        """
        logger.warning(
            "get_metrics_deprecated",
            message="get_metrics() is deprecated. Use observability metrics endpoints instead.",
        )
        return {}

    def get_job_metrics(self, job_id: str) -> dict[str, Any] | None:
        """
        Get metrics for a specific job.

        **DEPRECATED**: Metrics are now exported via observability infrastructure.
        Use structured logging and metrics endpoints to query job-specific data.

        Args:
            job_id: Job identifier

        Returns:
            None (deprecated)
        """
        logger.warning(
            "get_job_metrics_deprecated",
            job_id=job_id[:8],
            message="get_job_metrics() is deprecated. Use observability metrics instead.",
        )
        return None

    # ============================================================
    # Internal: Database operations
    # ============================================================

    async def _store_job(self, job: IndexJob) -> None:
        """Store job in database."""
        query = """
            INSERT INTO index_jobs (
                id, repo_id, snapshot_id, scope_paths, trigger_type, trigger_metadata,
                status, status_reason, created_at, started_at, finished_at,
                changed_files_count, indexed_chunks_count, errors_count,
                retry_count, max_retries, last_error,
                lock_acquired_by, lock_expires_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
        """

        await self.postgres.execute(
            query,
            job.id,
            job.repo_id,
            job.snapshot_id,
            json.dumps(job.scope_paths) if job.scope_paths else None,  # JSONB: explicit serialization
            job.trigger_type.value,
            json.dumps(job.trigger_metadata),  # JSONB: explicit serialization
            job.status.value,
            job.status_reason,
            job.created_at,
            job.started_at,
            job.finished_at,
            job.changed_files_count,
            job.indexed_chunks_count,
            job.errors_count,
            job.retry_count,
            job.max_retries,
            job.last_error,
            job.lock_acquired_by,
            job.lock_expires_at,
        )

    async def _load_job(self, job_id: str) -> IndexJob | None:
        """Load job from database."""
        query = "SELECT * FROM index_jobs WHERE id = $1"
        row = await self.postgres.fetchrow(query, job_id)

        if not row:
            return None

        return self._row_to_job(row)

    async def _update_job(self, job: IndexJob) -> None:
        """Update job in database."""
        query = """
            UPDATE index_jobs SET
                status = $2,
                status_reason = $3,
                started_at = $4,
                finished_at = $5,
                changed_files_count = $6,
                indexed_chunks_count = $7,
                errors_count = $8,
                retry_count = $9,
                last_error = $10,
                lock_acquired_by = $11,
                lock_expires_at = $12
            WHERE id = $1
        """

        await self.postgres.execute(
            query,
            job.id,
            job.status.value,
            job.status_reason,
            job.started_at,
            job.finished_at,
            job.changed_files_count,
            job.indexed_chunks_count,
            job.errors_count,
            job.retry_count,
            job.last_error,
            job.lock_acquired_by,
            job.lock_expires_at,
        )

    def _row_to_job(self, row: dict[str, Any]) -> IndexJob:
        """Convert database row to IndexJob."""
        # Parse JSONB fields (asyncpg returns them as strings if stored with json.dumps)
        scope_paths = row["scope_paths"]
        if isinstance(scope_paths, str):
            scope_paths = json.loads(scope_paths) if scope_paths else None

        trigger_metadata = row["trigger_metadata"]
        if isinstance(trigger_metadata, str):
            trigger_metadata = json.loads(trigger_metadata) if trigger_metadata else {}

        return IndexJob(
            id=str(row["id"]),  # UUID → str 변환 (asyncpg returns UUID type)
            repo_id=row["repo_id"],
            snapshot_id=row["snapshot_id"],
            scope_paths=scope_paths,
            trigger_type=TriggerType(row["trigger_type"]),
            trigger_metadata=trigger_metadata or {},
            status=JobStatus(row["status"]),
            status_reason=row["status_reason"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            changed_files_count=row["changed_files_count"],
            indexed_chunks_count=row["indexed_chunks_count"],
            errors_count=row["errors_count"],
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
            last_error=row["last_error"],
            lock_acquired_by=row["lock_acquired_by"],
            lock_expires_at=row["lock_expires_at"],
        )

    # ============================================================
    # Internal: Checkpoint system (Phase 2)
    # ============================================================

    async def _save_checkpoint(
        self, job_id: str, checkpoint: IndexJobCheckpoint, completed_files: list[str], failed_files: dict[str, str]
    ) -> None:
        """
        Save job checkpoint for idempotent retries.

        Args:
            job_id: Job identifier
            checkpoint: Checkpoint name
            completed_files: List of successfully processed files
            failed_files: Map of file_path → error_message
        """
        query = """
            INSERT INTO job_checkpoints (job_id, checkpoint, completed_files, failed_files, created_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (job_id, checkpoint) DO UPDATE SET
                completed_files = EXCLUDED.completed_files,
                failed_files = EXCLUDED.failed_files,
                created_at = EXCLUDED.created_at
        """

        await self.postgres.execute(
            query,
            job_id,
            checkpoint.value,
            json.dumps(completed_files),  # JSONB: explicit serialization
            json.dumps(failed_files),  # JSONB: explicit serialization
            datetime.now(),
        )

    async def _load_checkpoint(self, job_id: str, checkpoint: IndexJobCheckpoint) -> JobProgress | None:
        """
        Load job checkpoint.

        Args:
            job_id: Job identifier
            checkpoint: Checkpoint name

        Returns:
            JobProgress or None if not found
        """
        query = "SELECT * FROM job_checkpoints WHERE job_id = $1 AND checkpoint = $2"
        row = await self.postgres.fetchrow(query, job_id, checkpoint.value)

        if not row:
            return None

        # Parse JSONB fields
        completed_files = row["completed_files"]
        if isinstance(completed_files, str):
            completed_files = json.loads(completed_files) if completed_files else []

        failed_files = row["failed_files"]
        if isinstance(failed_files, str):
            failed_files = json.loads(failed_files) if failed_files else {}

        return JobProgress(
            checkpoint=IndexJobCheckpoint(row["checkpoint"]),
            completed_files=completed_files or [],
            failed_files=failed_files or {},
            timestamp=row["created_at"],
        )

    # ============================================================
    # Internal: Lock extension (Phase 2)
    # ============================================================

    def _start_lock_extension(self, lock: DistributedLock, job_id: str) -> asyncio.Task:
        """
        Start background task to periodically extend lock.

        Args:
            lock: Distributed lock to extend
            job_id: Job identifier for logging

        Returns:
            asyncio.Task that can be cancelled
        """
        task = asyncio.create_task(self._lock_extension_worker(lock, job_id))
        logger.debug(
            "lock_extension_started",
            job_id=job_id[:8],
            interval_seconds=self.lock_extend_interval,
        )
        return task

    async def _lock_extension_worker(self, lock: DistributedLock, job_id: str) -> None:
        """
        Background worker that periodically extends lock TTL.

        Args:
            lock: Distributed lock to extend
            job_id: Job identifier for logging
        """
        extension_count = 0

        try:
            while True:
                # Wait for interval
                await asyncio.sleep(self.lock_extend_interval)

                # Try to extend lock
                success = await lock.extend()

                if success:
                    extension_count += 1
                    logger.debug(
                        "lock_extended",
                        job_id=job_id[:8],
                        extension_count=extension_count,
                        ttl_seconds=self.lock_ttl,
                    )
                    record_counter("lock_extensions_total", labels={"job_id": job_id[:8]})
                else:
                    # Lock was lost (expired or taken by another process)
                    logger.error(
                        "lock_extension_failed",
                        job_id=job_id[:8],
                        message="Lock was lost - job may have exceeded TTL or been preempted",
                    )
                    record_counter("lock_lost_total", labels={"job_id": job_id[:8]})
                    break

        except asyncio.CancelledError:
            # Task was cancelled (job completed or failed)
            logger.debug(
                "lock_extension_cancelled",
                job_id=job_id[:8],
                total_extensions=extension_count,
            )
            raise

    # ============================================================
    # Internal: Job execution helpers (refactored from execute_job)
    # ============================================================

    async def _acquire_job_lock(self, job: IndexJob, lock: DistributedLock) -> tuple[bool, float]:
        """
        Acquire distributed lock for job execution.

        Args:
            job: Job to acquire lock for
            lock: Distributed lock instance

        Returns:
            Tuple of (acquired: bool, wait_seconds: float)

        Side effects:
            - Updates job status (ACQUIRING_LOCK, RUNNING, or LOCK_FAILED)
            - Records metrics (lock attempt, acquired, timeout)
        """
        # Update status: QUEUED → ACQUIRING_LOCK
        job.status = JobStatus.ACQUIRING_LOCK
        await self._update_job(job)

        # Track lock acquisition time
        lock_start_time = time.time()

        # Record lock attempt
        record_counter("lock_attempts_total", labels={"job_id": job.id[:8]})

        # Try to acquire lock with reasonable timeout
        # NOTE: timeout should be shorter than lock_ttl to allow retry logic
        lock_timeout = min(60, self.lock_ttl // 5)  # Max 60s or 1/5 of TTL
        acquired = await lock.acquire(blocking=True, timeout=lock_timeout)
        lock_wait_seconds = time.time() - lock_start_time

        if not acquired:
            # Lock acquisition failed
            job.status = JobStatus.LOCK_FAILED
            job.status_reason = f"Failed to acquire lock within {lock_timeout}s"
            job.finished_at = datetime.now()
            await self._update_job(job)

            # Record lock timeout
            record_counter("lock_timeouts_total", labels={"job_id": job.id[:8]})
            record_histogram("lock_wait_seconds", lock_wait_seconds)
            logger.warning(
                "lock_acquisition_failed",
                job_id=job.id[:8],
                timeout_seconds=lock_timeout,
                wait_seconds=lock_wait_seconds,
            )
            return False, lock_wait_seconds

        # Lock acquired successfully
        job.lock_acquired_by = self.instance_id
        job.lock_expires_at = datetime.now() + timedelta(seconds=self.lock_ttl)
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now()
        await self._update_job(job)

        # Record lock acquisition
        record_counter("locks_acquired_total", labels={"job_id": job.id[:8], "instance": self.instance_id})
        record_histogram("lock_wait_seconds", lock_wait_seconds)
        logger.info(
            "lock_acquired",
            job_id=job.id[:8],
            instance_id=self.instance_id,
            wait_seconds=lock_wait_seconds,
        )

        return True, lock_wait_seconds

    async def _check_superseded_jobs(self, job: IndexJob) -> None:
        """
        Check if any jobs were superseded by this job and mark them.

        Args:
            job: Current job

        Side effects:
            - Marks superseded jobs in database
        """
        superseded_jobs = await self.conflict_registry.find_superseded_jobs(
            repo_id=job.repo_id,
            new_snapshot_id=job.snapshot_id,
            exclude_job_id=job.id,
        )

        # If we found superseded jobs, mark them (but don't cancel ourselves)
        for superseded_job in superseded_jobs:
            await self.conflict_registry.mark_superseded(
                superseded_job.id,
                job.snapshot_id,
            )

    async def _execute_indexing_with_checkpoint(self, job: IndexJob, repo_path: str | Path) -> tuple[bool, Any | None]:
        """
        Execute indexing and save checkpoint on success.

        Args:
            job: Job to execute
            repo_path: Path to repository

        Returns:
            Tuple of (success: bool, result: Any or None)

        Side effects:
            - Executes indexing via orchestrator
            - Saves completion checkpoint
            - Updates job with results
            - Records metrics
        """
        try:
            result = await self.orchestrator.index_repository(
                repo_path=repo_path,
                repo_id=job.repo_id,
                snapshot_id=job.snapshot_id,
                incremental=job.trigger_type == TriggerType.FS_EVENT,  # FS events are incremental
            )

            # Save completion checkpoint
            await self._save_checkpoint(
                job_id=job.id,
                checkpoint=IndexJobCheckpoint.COMPLETED,
                completed_files=[],  # TODO: Extract from result
                failed_files={},
            )

            # Update job with results
            job.status = JobStatus.COMPLETED
            job.finished_at = datetime.now()
            job.changed_files_count = result.files_processed
            job.indexed_chunks_count = result.chunks_created
            job.errors_count = len(result.errors) if hasattr(result, "errors") else 0
            await self._update_job(job)

            # Calculate job duration
            job_duration = (job.finished_at - job.started_at).total_seconds() if job.started_at else 0

            # Record completion metrics
            record_counter(
                "jobs_completed_total",
                labels={"status": "completed", "job_id": job.id[:8], "instance": self.instance_id},
            )
            record_histogram("job_duration_seconds", job_duration)
            record_histogram("job_files_processed", job.changed_files_count)
            record_histogram("job_chunks_created", job.indexed_chunks_count)

            logger.info(
                "job_completed",
                job_id=job.id[:8],
                files_processed=job.changed_files_count,
                chunks_created=job.indexed_chunks_count,
                errors_count=job.errors_count,
                duration_seconds=job_duration,
            )

            return True, result

        except Exception as e:
            return False, e

    async def _handle_indexing_failure(self, job: IndexJob, error: Exception) -> None:
        """
        Handle indexing failure with retry logic.

        Args:
            job: Failed job
            error: Exception that caused failure

        Side effects:
            - Updates job status (FAILED or QUEUED for retry)
            - Records failure metrics
            - Error details stored in job.last_error
        """
        # Update job status
        job.status = JobStatus.FAILED
        job.finished_at = datetime.now()
        job.last_error = str(error)
        job.errors_count = 1

        # Check if retry is available
        if job.retry_count < job.max_retries:
            job.retry_count += 1
            job.status = JobStatus.QUEUED  # Re-queue for retry
            job.finished_at = None
            job.started_at = None
            job.lock_acquired_by = None
            job.lock_expires_at = None

            logger.warning(
                "job_failed_retrying",
                job_id=job.id[:8],
                retry_count=job.retry_count,
                max_retries=job.max_retries,
                error=str(error),
            )
            record_counter("job_retries_total", labels={"job_id": job.id[:8]})
        else:
            logger.error(
                "job_failed_permanently",
                job_id=job.id[:8],
                retry_count=job.retry_count,
                error=str(error),
                exc_info=True,
            )
            record_counter("jobs_failed_permanently_total", labels={"job_id": job.id[:8]})

        await self._update_job(job)

        # Record failure metrics
        record_counter(
            "jobs_completed_total",
            labels={"status": job.status.value, "job_id": job.id[:8], "instance": self.instance_id},
        )
        record_counter("job_errors_total", value=1, labels={"job_id": job.id[:8]})
