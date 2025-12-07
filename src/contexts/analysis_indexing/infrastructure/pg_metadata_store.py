"""
PostgreSQL Indexing Metadata Store

PostgreSQL 기반 인덱싱 메타데이터 저장소
"""

from ..domain.models import IndexingMetadata, IndexingMode


class PgIndexingMetadataStore:
    """PostgreSQL 기반 인덱싱 메타데이터 저장소"""

    def __init__(self, postgres_adapter):
        """
        초기화

        Args:
            postgres_adapter: PostgreSQL 어댑터 (src.infra.db.postgres_adapter)
        """
        self.db = postgres_adapter

    async def save_metadata(self, metadata: IndexingMetadata) -> None:
        """메타데이터 저장 (Upsert)"""
        query = """
            INSERT INTO indexing_metadata (
                repo_id, snapshot_id, mode, status,
                files_processed, files_failed,
                graph_nodes_created, graph_edges_created,
                chunks_created, started_at, completed_at, error_message
            ) VALUES (
                $1, $2, $3, $4,
                $5, $6,
                $7, $8,
                $9, $10, $11, $12
            )
            ON CONFLICT (repo_id, snapshot_id)
            DO UPDATE SET
                mode = EXCLUDED.mode,
                status = EXCLUDED.status,
                files_processed = EXCLUDED.files_processed,
                files_failed = EXCLUDED.files_failed,
                graph_nodes_created = EXCLUDED.graph_nodes_created,
                graph_edges_created = EXCLUDED.graph_edges_created,
                chunks_created = EXCLUDED.chunks_created,
                completed_at = EXCLUDED.completed_at,
                error_message = EXCLUDED.error_message,
                updated_at = NOW()
        """

        await self.db.execute(
            query,
            metadata.repo_id,
            metadata.snapshot_id,
            metadata.mode.value,
            metadata.status,  # 이미 str
            metadata.files_processed,
            metadata.files_failed,
            metadata.graph_nodes_created,
            metadata.graph_edges_created,
            metadata.chunks_created,
            metadata.started_at,
            metadata.completed_at,
            metadata.error_message,
        )

    async def get_metadata(self, repo_id: str, snapshot_id: str) -> IndexingMetadata | None:
        """메타데이터 조회"""
        query = """
            SELECT
                repo_id, snapshot_id, mode, status,
                files_processed, files_failed,
                graph_nodes_created, graph_edges_created,
                chunks_created, started_at, completed_at, error_message
            FROM indexing_metadata
            WHERE repo_id = $1 AND snapshot_id = $2
        """

        result = await self.db.fetchrow(query, repo_id, snapshot_id)

        if not result:
            return None

        return IndexingMetadata(
            repo_id=result["repo_id"],
            snapshot_id=result["snapshot_id"],
            mode=IndexingMode(result["mode"]),
            status=result["status"],  # str 타입
            files_processed=result["files_processed"],
            files_failed=result["files_failed"],
            graph_nodes_created=result["graph_nodes_created"],
            graph_edges_created=result["graph_edges_created"],
            chunks_created=result["chunks_created"],
            started_at=result["started_at"],
            completed_at=result["completed_at"],
            error_message=result["error_message"],
        )

    async def list_metadata(self, repo_id: str) -> list[IndexingMetadata]:
        """리포지토리의 모든 메타데이터 조회"""
        query = """
            SELECT
                repo_id, snapshot_id, mode, status,
                files_processed, files_failed,
                graph_nodes_created, graph_edges_created,
                chunks_created, started_at, completed_at, error_message
            FROM indexing_metadata
            WHERE repo_id = $1
            ORDER BY started_at DESC
        """

        results = await self.db.fetch(query, repo_id)

        return [
            IndexingMetadata(
                repo_id=row["repo_id"],
                snapshot_id=row["snapshot_id"],
                mode=IndexingMode(row["mode"]),
                status=row["status"],  # str 타입
                files_processed=row["files_processed"],
                files_failed=row["files_failed"],
                graph_nodes_created=row["graph_nodes_created"],
                graph_edges_created=row["graph_edges_created"],
                chunks_created=row["chunks_created"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                error_message=row["error_message"],
            )
            for row in results
        ]

    async def delete_metadata(self, repo_id: str, snapshot_id: str) -> None:
        """메타데이터 삭제"""
        query = """
            DELETE FROM indexing_metadata
            WHERE repo_id = $1 AND snapshot_id = $2
        """

        await self.db.execute(query, repo_id, snapshot_id)
