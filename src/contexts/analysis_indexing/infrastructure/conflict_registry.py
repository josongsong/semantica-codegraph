"""
Conflict Registry for Job Deduplication.

Handles conflict detection and resolution for concurrent indexing jobs:
- Duplicate detection: Same (repo_id, snapshot_id) already queued/running
- Supersession: Newer snapshot supersedes older jobs
- Conflict strategies: SKIP, QUEUE, CANCEL_OLD

Phase 2 implementation for SOTA concurrent editing support.
"""

import json
from datetime import datetime
from enum import Enum
from typing import Any

from src.common.observability import get_logger
from src.contexts.analysis_indexing.infrastructure.models.job import IndexJob, JobStatus, TriggerType
from src.infra.storage.postgres import PostgresStore

logger = get_logger(__name__)


def _row_to_job(row: dict[str, Any]) -> IndexJob:
    """
    Convert database row to IndexJob.

    Helper function for ConflictRegistry to avoid circular imports.
    """
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


class ConflictStrategy(str, Enum):
    """Strategy for handling conflicting jobs."""

    SKIP = "skip"  # Skip new job, mark as DEDUPED
    QUEUE = "queue"  # Queue new job, both will run
    CANCEL_OLD = "cancel_old"  # Cancel old job, mark as SUPERSEDED
    LAST_WRITE_WINS = "last_write_wins"  # Most recent job wins (for FS events)


class ConflictRegistry:
    """
    Registry for detecting and resolving job conflicts.

    Provides duplicate detection and supersession logic for concurrent jobs.
    Uses PostgreSQL to track active jobs per (repo_id, snapshot_id).

    Usage:
        registry = ConflictRegistry(postgres_store)

        # Check for duplicate
        duplicate = await registry.check_duplicate(repo_id, snapshot_id)
        if duplicate:
            # Handle duplicate (mark new job as DEDUPED)
            pass

        # Check for supersession
        superseded_jobs = await registry.find_superseded_jobs(repo_id, new_snapshot_id)
        for old_job in superseded_jobs:
            await registry.mark_superseded(old_job.id, new_snapshot_id)
    """

    def __init__(
        self,
        postgres_store: PostgresStore,
        default_strategy: ConflictStrategy = ConflictStrategy.SKIP,
    ):
        """
        Initialize conflict registry.

        Args:
            postgres_store: PostgreSQL store for job queries
            default_strategy: Default conflict resolution strategy
        """
        self.postgres = postgres_store
        self.default_strategy = default_strategy

        logger.info(f"ConflictRegistry initialized with strategy={default_strategy.value}")

    async def check_duplicate(
        self,
        repo_id: str,
        snapshot_id: str,
        exclude_job_id: str | None = None,
    ) -> IndexJob | None:
        """
        Check if there's already an active job for (repo_id, snapshot_id).

        Active means: QUEUED, ACQUIRING_LOCK, or RUNNING status.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier (branch/commit)
            exclude_job_id: Job ID to exclude from search (for self-check)

        Returns:
            Existing IndexJob if found, None otherwise
        """
        query = """
            SELECT * FROM index_jobs
            WHERE repo_id = $1
              AND snapshot_id = $2
              AND status IN ('queued', 'acquiring_lock', 'running')
        """
        params: list[Any] = [repo_id, snapshot_id]

        if exclude_job_id:
            query += " AND id != $3"
            params.append(exclude_job_id)

        query += " ORDER BY created_at DESC LIMIT 1"

        row = await self.postgres.fetchrow(query, *params)

        if not row:
            return None

        # Convert row to IndexJob
        job = _row_to_job(row)
        logger.debug(
            f"Duplicate job found: repo={repo_id}, snapshot={snapshot_id}, "
            f"existing_job={job.id[:8]}, status={job.status.value}"
        )

        return job

    async def find_superseded_jobs(
        self,
        repo_id: str,
        new_snapshot_id: str,
        exclude_job_id: str | None = None,
    ) -> list[IndexJob]:
        """
        Find jobs that should be superseded by a new snapshot.

        This is useful when a newer commit/branch is indexed, making older
        jobs obsolete.

        Args:
            repo_id: Repository identifier
            new_snapshot_id: New snapshot that supersedes others
            exclude_job_id: Job ID to exclude (e.g., the new job itself)

        Returns:
            List of jobs that should be marked as SUPERSEDED
        """
        # For now, we only supersede jobs with different snapshot_id
        # In future, could add Git commit ancestry checks
        query = """
            SELECT * FROM index_jobs
            WHERE repo_id = $1
              AND snapshot_id != $2
              AND status IN ('queued', 'acquiring_lock', 'running')
        """
        params: list[Any] = [repo_id, new_snapshot_id]

        if exclude_job_id:
            query += " AND id != $3"
            params.append(exclude_job_id)

        query += " ORDER BY created_at ASC"  # Oldest first

        rows = await self.postgres.fetch(query, *params)

        jobs = [_row_to_job(row) for row in rows]

        if jobs:
            logger.info(f"Found {len(jobs)} jobs to supersede: repo={repo_id}, new_snapshot={new_snapshot_id}")

        return jobs

    async def mark_superseded(self, job_id: str, superseding_snapshot_id: str) -> bool:
        """
        Mark a job as SUPERSEDED by a newer snapshot.

        Args:
            job_id: Job to mark as superseded
            superseding_snapshot_id: Snapshot ID that supersedes this job

        Returns:
            True if job was updated, False if already finished
        """
        query = """
            UPDATE index_jobs
            SET status = 'superseded',
                status_reason = $2,
                finished_at = $3
            WHERE id = $1
              AND status IN ('queued', 'acquiring_lock')
            RETURNING id
        """

        reason = f"Superseded by newer snapshot: {superseding_snapshot_id}"
        result = await self.postgres.fetchrow(query, job_id, reason, datetime.now())

        if result:
            logger.info(f"Job {job_id[:8]} marked as SUPERSEDED by {superseding_snapshot_id}")
            return True
        else:
            logger.debug(f"Job {job_id[:8]} not superseded (already running or finished)")
            return False

    async def mark_deduped(self, job_id: str, duplicate_job_id: str) -> bool:
        """
        Mark a job as DEDUPED (duplicate of another job).

        Args:
            job_id: Job to mark as deduped
            duplicate_job_id: ID of the duplicate job

        Returns:
            True if job was updated
        """
        query = """
            UPDATE index_jobs
            SET status = 'deduped',
                status_reason = $2,
                finished_at = $3
            WHERE id = $1
            RETURNING id
        """

        reason = f"Duplicate of job {duplicate_job_id[:8]}"
        result = await self.postgres.fetchrow(query, job_id, reason, datetime.now())

        if result:
            logger.info(f"Job {job_id[:8]} marked as DEDUPED (duplicate of {duplicate_job_id[:8]})")
            return True

        return False

    async def apply_strategy(
        self,
        new_job: IndexJob,
        existing_job: IndexJob | None,
        strategy: ConflictStrategy | None = None,
    ) -> JobStatus:
        """
        Apply conflict resolution strategy.

        Args:
            new_job: New job being submitted
            existing_job: Existing conflicting job (if any)
            strategy: Strategy to apply (default: use default_strategy)

        Returns:
            Status to set for new_job (QUEUED, DEDUPED, etc.)
        """
        strategy = strategy or self.default_strategy

        if not existing_job:
            # No conflict, proceed normally
            return JobStatus.QUEUED

        if strategy == ConflictStrategy.SKIP:
            # Skip new job, mark as DEDUPED
            await self.mark_deduped(new_job.id, existing_job.id)
            return JobStatus.DEDUPED

        elif strategy == ConflictStrategy.QUEUE:
            # Queue both jobs (default behavior)
            return JobStatus.QUEUED

        elif strategy == ConflictStrategy.CANCEL_OLD:
            # Cancel old job, run new one
            await self.mark_superseded(existing_job.id, new_job.snapshot_id)
            return JobStatus.QUEUED

        elif strategy == ConflictStrategy.LAST_WRITE_WINS:
            # Most recent job wins (for FS events with debouncing)
            if new_job.created_at > existing_job.created_at:
                await self.mark_superseded(existing_job.id, new_job.snapshot_id)
                return JobStatus.QUEUED
            else:
                await self.mark_deduped(new_job.id, existing_job.id)
                return JobStatus.DEDUPED

        return JobStatus.QUEUED
