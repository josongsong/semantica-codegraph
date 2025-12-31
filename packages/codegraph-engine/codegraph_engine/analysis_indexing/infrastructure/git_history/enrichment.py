"""
Git History Enrichment Hook

Integrates git history analysis with chunk update pipeline.
Automatically enriches chunks with git blame and churn metrics.

Phase: P0-1 Git History Analysis (Layer 19)
"""

from pathlib import Path

from codegraph_shared.common.observability import get_logger
from codegraph_engine.analysis_indexing.infrastructure.git_history.git_service import GitService, create_git_service
from codegraph_engine.analysis_indexing.infrastructure.git_history.models import ChunkChurnMetrics, GitBlame
from codegraph_engine.code_foundation.infrastructure.chunk.models import Chunk
from codegraph_shared.infra.storage.postgres import PostgresStore

logger = get_logger(__name__)


class GitHistoryEnrichmentHook:
    """
    Enriches chunks with git history data during chunk updates.

    Implements ChunkUpdateHook protocol to react to chunk lifecycle events:
    - on_chunk_modified: Recalculate churn metrics
    - on_chunk_drifted: Update line ranges in blame data
    - on_chunk_renamed: Update chunk_id references

    Usage:
        git_service = create_git_service("/path/to/repo")
        hook = GitHistoryEnrichmentHook(git_service, postgres_store)

        refresher = ChunkIncrementalRefresher(
            ...,
            update_hook=hook
        )
    """

    def __init__(
        self,
        git_service: GitService | None,
        postgres_store: PostgresStore,
        snapshot_id: str = "HEAD",
    ):
        """
        Initialize git history enrichment hook.

        Args:
            git_service: GitService instance (None disables enrichment)
            postgres_store: PostgreSQL store for persisting data
            snapshot_id: Git snapshot identifier (commit hash or "HEAD")
        """
        self.git_service = git_service
        self.postgres_store = postgres_store
        self.snapshot_id = snapshot_id
        self.enabled = git_service is not None

        if not self.enabled:
            logger.warning("Git history enrichment disabled (no git service)")
        else:
            logger.info(f"Git history enrichment enabled for snapshot: {snapshot_id}")

    def on_chunk_modified(self, chunk: Chunk) -> None:
        """
        Called when a chunk's content is modified.

        Recalculates git blame and churn metrics for the modified chunk.

        Args:
            chunk: The modified chunk
        """
        if not self.enabled:
            return

        try:
            logger.debug(f"Enriching modified chunk: {chunk.chunk_id}")
            self._enrich_chunk(chunk)
        except Exception as e:
            logger.error(f"Failed to enrich modified chunk {chunk.chunk_id}: {e}", exc_info=True)

    def on_chunk_drifted(self, chunk: Chunk) -> None:
        """
        Called when a chunk has drifted beyond threshold.

        Updates git blame line ranges for the drifted chunk.

        Args:
            chunk: The drifted chunk (with updated position)
        """
        if not self.enabled:
            return

        try:
            logger.debug(f"Enriching drifted chunk: {chunk.chunk_id}")
            # Drifted chunks need updated blame data (line ranges changed)
            self._enrich_chunk(chunk)
        except Exception as e:
            logger.error(f"Failed to enrich drifted chunk {chunk.chunk_id}: {e}", exc_info=True)

    def on_chunk_renamed(self, old_id: str, new_id: str, chunk: Chunk) -> None:
        """
        Called when a chunk was renamed (same content, different FQN).

        Updates chunk_id references in git_blame and chunk_churn_metrics tables.

        Args:
            old_id: Old chunk ID
            new_id: New chunk ID
            chunk: The renamed chunk (with new FQN)
        """
        if not self.enabled:
            return

        try:
            logger.debug(f"Updating git history for renamed chunk: {old_id} → {new_id}")
            self._update_chunk_id_references(old_id, new_id)
        except Exception as e:
            logger.error(f"Failed to update renamed chunk references {old_id} → {new_id}: {e}", exc_info=True)

    def _enrich_chunk(self, chunk: Chunk) -> None:
        """
        Enrich a chunk with git blame and churn metrics.

        Args:
            chunk: Chunk to enrich
        """
        if not self.git_service:
            return

        # Extract git blame for chunk's line range
        blame_data = self._get_blame_for_chunk(chunk)
        if blame_data:
            self._store_blame_data(blame_data)

        # Calculate churn metrics
        churn_metrics = self._calculate_churn_metrics(chunk)
        if churn_metrics:
            self._store_churn_metrics(churn_metrics)

    def _get_blame_for_chunk(self, chunk: Chunk) -> list[GitBlame]:
        """
        Get git blame data for a chunk's line range.

        Args:
            chunk: Chunk to get blame for

        Returns:
            List of GitBlame entries
        """
        if not self.git_service:
            return []

        try:
            # Get full file blame
            all_blame = self.git_service.get_blame_for_file(chunk.file_path, rev=self.snapshot_id)

            # Filter to chunk's line range and associate with chunk_id
            chunk_blame = []
            chunk_start = chunk.start_line or 0
            chunk_end = chunk.end_line or 0
            for blame in all_blame:
                # Check if blame overlaps with chunk's line range
                if blame.start_line <= chunk_end and blame.end_line >= chunk_start:
                    # Clip blame to chunk boundaries
                    clipped_start = max(blame.start_line, chunk_start)
                    clipped_end = min(blame.end_line, chunk_end)

                    # Create new blame entry for chunk
                    chunk_blame.append(
                        GitBlame(
                            id=None,
                            repo_id=blame.repo_id,
                            snapshot_id=self.snapshot_id,
                            file_path=chunk.file_path,
                            start_line=clipped_start,
                            end_line=clipped_end,
                            commit_hash=blame.commit_hash,
                            author_name=blame.author_name,
                            author_email=blame.author_email,
                            commit_date=blame.commit_date,
                            chunk_id=chunk.chunk_id,
                        )
                    )

            logger.debug(f"Extracted {len(chunk_blame)} blame entries for chunk {chunk.chunk_id}")
            return chunk_blame

        except Exception as e:
            logger.error(f"Failed to get blame for chunk {chunk.chunk_id}: {e}")
            return []

    def _calculate_churn_metrics(self, chunk: Chunk) -> ChunkChurnMetrics | None:
        """
        Calculate churn metrics for a chunk.

        Args:
            chunk: Chunk to calculate metrics for

        Returns:
            ChunkChurnMetrics or None if calculation failed
        """
        if not self.git_service:
            return None

        try:
            metrics = self.git_service.calculate_churn_metrics(
                chunk_id=chunk.chunk_id,
                file_path=chunk.file_path,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
            )
            logger.debug(
                f"Calculated churn metrics for {chunk.chunk_id}: "
                f"score={metrics.churn_score:.3f}, commits={metrics.total_commits}"
            )
            return metrics

        except Exception as e:
            logger.error(f"Failed to calculate churn metrics for chunk {chunk.chunk_id}: {e}")
            return None

    def _store_blame_data(self, blame_data: list[GitBlame]) -> None:
        """
        Store git blame data in database.

        Args:
            blame_data: List of GitBlame entries
        """
        if not blame_data:
            return

        try:
            # Delete existing blame data for this chunk (if any)
            chunk_id = blame_data[0].chunk_id
            if chunk_id:
                self.postgres_store.execute(
                    """
                    DELETE FROM git_blame
                    WHERE chunk_id = %s AND snapshot_id = %s
                    """,
                    (chunk_id, self.snapshot_id),
                )

            # Insert new blame data
            for blame in blame_data:
                self.postgres_store.execute(
                    """
                    INSERT INTO git_blame (
                        repo_id, snapshot_id, file_path,
                        start_line, end_line,
                        commit_hash, author_name, author_email, commit_date,
                        chunk_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (repo_id, snapshot_id, file_path, start_line, end_line)
                    DO UPDATE SET
                        commit_hash = EXCLUDED.commit_hash,
                        author_name = EXCLUDED.author_name,
                        author_email = EXCLUDED.author_email,
                        commit_date = EXCLUDED.commit_date,
                        chunk_id = EXCLUDED.chunk_id
                    """,
                    (
                        blame.repo_id,
                        blame.snapshot_id,
                        blame.file_path,
                        blame.start_line,
                        blame.end_line,
                        blame.commit_hash,
                        blame.author_name,
                        blame.author_email,
                        blame.commit_date,
                        blame.chunk_id,
                    ),
                )

            logger.debug(f"Stored {len(blame_data)} blame entries")

        except Exception as e:
            logger.error(f"Failed to store blame data: {e}", exc_info=True)

    def _store_churn_metrics(self, metrics: ChunkChurnMetrics) -> None:
        """
        Store churn metrics in database.

        Args:
            metrics: ChunkChurnMetrics to store
        """
        try:
            # Convert authors to JSONB
            import json

            authors_json = json.dumps(
                [
                    {"name": author.name, "email": author.email, "commit_count": author.commit_count}
                    for author in metrics.authors
                ]
            )

            # Upsert churn metrics
            self.postgres_store.execute(
                """
                INSERT INTO chunk_churn_metrics (
                    chunk_id, repo_id,
                    total_commits, total_lines_added, total_lines_deleted, total_lines_modified,
                    churn_score,
                    primary_author, author_count, authors,
                    first_commit_hash, first_commit_date,
                    last_commit_hash, last_commit_date,
                    age_days, days_since_last_change,
                    is_hotspot, hotspot_reason
                ) VALUES (
                    %s, %s,
                    %s, %s, %s, %s,
                    %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s
                )
                ON CONFLICT (chunk_id)
                DO UPDATE SET
                    total_commits = EXCLUDED.total_commits,
                    total_lines_added = EXCLUDED.total_lines_added,
                    total_lines_deleted = EXCLUDED.total_lines_deleted,
                    total_lines_modified = EXCLUDED.total_lines_modified,
                    churn_score = EXCLUDED.churn_score,
                    primary_author = EXCLUDED.primary_author,
                    author_count = EXCLUDED.author_count,
                    authors = EXCLUDED.authors,
                    first_commit_hash = EXCLUDED.first_commit_hash,
                    first_commit_date = EXCLUDED.first_commit_date,
                    last_commit_hash = EXCLUDED.last_commit_hash,
                    last_commit_date = EXCLUDED.last_commit_date,
                    age_days = EXCLUDED.age_days,
                    days_since_last_change = EXCLUDED.days_since_last_change,
                    is_hotspot = EXCLUDED.is_hotspot,
                    hotspot_reason = EXCLUDED.hotspot_reason
                """,
                (
                    metrics.chunk_id,
                    metrics.repo_id,
                    metrics.total_commits,
                    metrics.total_lines_added,
                    metrics.total_lines_deleted,
                    metrics.total_lines_modified,
                    metrics.churn_score,
                    metrics.primary_author,
                    metrics.author_count,
                    authors_json,
                    metrics.first_commit_hash,
                    metrics.first_commit_date,
                    metrics.last_commit_hash,
                    metrics.last_commit_date,
                    metrics.age_days,
                    metrics.days_since_last_change,
                    metrics.is_hotspot,
                    metrics.hotspot_reason.value if metrics.hotspot_reason else None,
                ),
            )

            logger.debug(
                f"Stored churn metrics for {metrics.chunk_id} "
                f"(score={metrics.churn_score:.3f}, hotspot={metrics.is_hotspot})"
            )

        except Exception as e:
            logger.error(f"Failed to store churn metrics: {e}", exc_info=True)

    def _update_chunk_id_references(self, old_id: str, new_id: str) -> None:
        """
        Update chunk_id references after rename.

        Args:
            old_id: Old chunk ID
            new_id: New chunk ID
        """
        try:
            # Update git_blame references
            self.postgres_store.execute(
                """
                UPDATE git_blame
                SET chunk_id = %s
                WHERE chunk_id = %s
                """,
                (new_id, old_id),
            )

            # Update chunk_churn_metrics (primary key, so delete + insert)
            # First, get existing metrics
            result = self.postgres_store.fetchone("SELECT * FROM chunk_churn_metrics WHERE chunk_id = %s", (old_id,))

            if result:
                # Delete old entry
                self.postgres_store.execute("DELETE FROM chunk_churn_metrics WHERE chunk_id = %s", (old_id,))

                # Insert with new ID
                columns = list(result.keys())
                values = [result[col] for col in columns]
                # Update chunk_id in values
                chunk_id_idx = columns.index("chunk_id")
                values[chunk_id_idx] = new_id

                placeholders = ", ".join(["%s"] * len(columns))
                self.postgres_store.execute(
                    f"""
                    INSERT INTO chunk_churn_metrics ({", ".join(columns)})
                    VALUES ({placeholders})
                    """,
                    tuple(values),
                )

            logger.debug(f"Updated git history references: {old_id} → {new_id}")

        except Exception as e:
            logger.error(f"Failed to update chunk ID references: {e}", exc_info=True)


def create_enrichment_hook(
    repo_path: str | Path,
    postgres_store: PostgresStore,
    snapshot_id: str = "HEAD",
) -> GitHistoryEnrichmentHook:
    """
    Create git history enrichment hook with error handling.

    Args:
        repo_path: Path to git repository
        postgres_store: PostgreSQL store
        snapshot_id: Git snapshot identifier

    Returns:
        GitHistoryEnrichmentHook (may be disabled if git is unavailable)
    """
    git_service = create_git_service(repo_path)
    return GitHistoryEnrichmentHook(git_service, postgres_store, snapshot_id)
