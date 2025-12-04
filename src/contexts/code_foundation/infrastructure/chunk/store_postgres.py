"""
PostgresChunkStore - PostgreSQL 기반 ChunkStore 구현

프로덕션용 구현, asyncpg 사용.
"""

from src.contexts.code_foundation.infrastructure.chunk.models import Chunk, ChunkHistory, ChunkToGraph, ChunkToIR


class PostgresChunkStore:
    """
    PostgreSQL 기반 ChunkStore 구현.

    Uses asyncpg for async PostgreSQL operations.

    필요한 인덱스:
    - idx_chunks_file_span: (repo_id, file_path, start_line, end_line)
    - idx_chunks_repo_snapshot: (repo_id, snapshot_id)
    - idx_chunks_symbol: (symbol_id)
    - idx_chunks_content_hash: (repo_id, file_path, content_hash)
    """

    def __init__(self, postgres_store):
        """
        Initialize PostgresChunkStore.

        Args:
            postgres_store: Shared PostgresStore instance (required)
        """
        if postgres_store is None:
            raise ValueError("postgres_store is required. Pass a PostgresStore instance.")
        self._postgres_store = postgres_store

    async def _get_pool(self):
        """
        Get connection pool from PostgresStore.

        The pool will be auto-initialized on first use via PostgresStore._ensure_pool().
        """
        return await self._postgres_store._ensure_pool()

    async def close(self):
        """
        Close is handled by PostgresStore lifecycle.

        Do not close the pool here as it's shared across the application.
        """
        pass  # No-op: PostgresStore manages its own lifecycle

    def _chunk_from_row(self, row) -> Chunk:
        """Convert DB row to Chunk model"""
        import json

        return Chunk(
            chunk_id=row["chunk_id"],
            repo_id=row["repo_id"],
            snapshot_id=row["snapshot_id"],
            project_id=row["project_id"],
            module_path=row["module_path"],
            file_path=row["file_path"],
            kind=row["kind"],
            fqn=row["fqn"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            original_start_line=row["original_start_line"],
            original_end_line=row["original_end_line"],
            content_hash=row["content_hash"],
            parent_id=row["parent_id"],
            children=json.loads(row.get("attrs", "{}")).get("children", []),
            language=row["language"],
            symbol_visibility=row["symbol_visibility"],
            symbol_id=row["symbol_id"],
            symbol_owner_id=row["symbol_owner_id"],
            summary=row["summary"],
            importance=row["importance"],
            attrs=json.loads(row.get("attrs", "{}")),
            version=row["version"],
            last_indexed_commit=row["last_indexed_commit"],
            is_deleted=row["is_deleted"],
            is_test=row.get("is_test"),  # P1: Test detection
            is_overlay=row.get("is_overlay", False),  # P2: Overlay support
            overlay_session_id=row.get("overlay_session_id"),  # P2
            base_chunk_id=row.get("base_chunk_id"),  # P2
        )

    async def save_chunk(self, chunk: Chunk) -> None:
        """Chunk 저장 (UPSERT)"""
        import json

        pool = await self._get_pool()
        # No need to copy - we're only reading for JSON serialization
        attrs_json = json.dumps({**chunk.attrs, "children": chunk.children})

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chunks (
                    chunk_id, repo_id, snapshot_id, project_id, module_path, file_path,
                    parent_id, kind, fqn, language, symbol_visibility,
                    symbol_id, symbol_owner_id, start_line, end_line,
                    original_start_line, original_end_line, content_hash,
                    version, is_deleted, last_indexed_commit,
                    summary, importance, attrs,
                    is_test, is_overlay, overlay_session_id, base_chunk_id
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                    $16, $17, $18, $19, $20, $21, $22, $23, $24,
                    $25, $26, $27, $28
                )
                ON CONFLICT (chunk_id) DO UPDATE SET
                    snapshot_id = EXCLUDED.snapshot_id,
                    project_id = EXCLUDED.project_id,
                    module_path = EXCLUDED.module_path,
                    file_path = EXCLUDED.file_path,
                    parent_id = EXCLUDED.parent_id,
                    kind = EXCLUDED.kind,
                    fqn = EXCLUDED.fqn,
                    language = EXCLUDED.language,
                    symbol_visibility = EXCLUDED.symbol_visibility,
                    symbol_id = EXCLUDED.symbol_id,
                    symbol_owner_id = EXCLUDED.symbol_owner_id,
                    start_line = EXCLUDED.start_line,
                    end_line = EXCLUDED.end_line,
                    original_start_line = EXCLUDED.original_start_line,
                    original_end_line = EXCLUDED.original_end_line,
                    content_hash = EXCLUDED.content_hash,
                    version = EXCLUDED.version,
                    is_deleted = EXCLUDED.is_deleted,
                    last_indexed_commit = EXCLUDED.last_indexed_commit,
                    summary = EXCLUDED.summary,
                    importance = EXCLUDED.importance,
                    attrs = EXCLUDED.attrs,
                    is_test = EXCLUDED.is_test,
                    is_overlay = EXCLUDED.is_overlay,
                    overlay_session_id = EXCLUDED.overlay_session_id,
                    base_chunk_id = EXCLUDED.base_chunk_id
                """,
                chunk.chunk_id,
                chunk.repo_id,
                chunk.snapshot_id,
                chunk.project_id,
                chunk.module_path,
                chunk.file_path,
                chunk.parent_id,
                chunk.kind,
                chunk.fqn,
                chunk.language,
                chunk.symbol_visibility,
                chunk.symbol_id,
                chunk.symbol_owner_id,
                chunk.start_line,
                chunk.end_line,
                chunk.original_start_line,
                chunk.original_end_line,
                chunk.content_hash,
                chunk.version,
                chunk.is_deleted,
                chunk.last_indexed_commit,
                chunk.summary,
                chunk.importance,
                attrs_json,
                chunk.is_test,
                chunk.is_overlay,
                chunk.overlay_session_id,
                chunk.base_chunk_id,
            )

    async def save_chunks(self, chunks: list[Chunk]) -> None:
        """
        여러 Chunk를 일괄 저장 (배치 UPSERT).

        성능 최적화를 위해:
        - 배치 크기를 500개로 제한 (PostgreSQL 파라미터 제한 고려)
        - 트랜잭션으로 원자성 보장
        """
        if not chunks:
            return

        BATCH_SIZE = 500
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            async with conn.transaction():
                # Process in batches
                for i in range(0, len(chunks), BATCH_SIZE):
                    batch = chunks[i : i + BATCH_SIZE]
                    await self._upsert_batch(conn, batch)

    async def _upsert_batch(self, conn, chunks: list[Chunk]) -> None:
        """
        배치 단위로 chunk를 UPSERT.

        Args:
            conn: Database connection
            chunks: Chunks to upsert (max 500)
        """
        if not chunks:
            return

        import json

        from src.common.utils import build_batch_values_clause, deduplicate_by_key

        # Deduplicate chunks by chunk_id (keep last occurrence)
        chunks = deduplicate_by_key(chunks, lambda c: c.chunk_id)

        # Prepare batch data using utility
        def extract_chunk_fields(chunk: Chunk) -> list:
            attrs_json = json.dumps({**chunk.attrs, "children": chunk.children})
            return [
                chunk.chunk_id,
                chunk.repo_id,
                chunk.snapshot_id,
                chunk.project_id,
                chunk.module_path,
                chunk.file_path,
                chunk.parent_id,
                chunk.kind,
                chunk.fqn,
                chunk.language,
                chunk.symbol_visibility,
                chunk.symbol_id,
                chunk.symbol_owner_id,
                chunk.start_line,
                chunk.end_line,
                chunk.original_start_line,
                chunk.original_end_line,
                chunk.content_hash,
                chunk.version,
                chunk.is_deleted,
                chunk.last_indexed_commit,
                chunk.summary,
                chunk.importance,
                attrs_json,
                chunk.is_test,  # P1
                chunk.is_overlay,  # P2
                chunk.overlay_session_id,  # P2
                chunk.base_chunk_id,  # P2
            ]

        values = []
        for chunk in chunks:
            values.extend(extract_chunk_fields(chunk))

        # Build VALUES clause using utility
        num_fields = 28  # 24 + 4 (P1+P2 fields)
        values_clause = build_batch_values_clause(num_fields, len(chunks))

        await conn.execute(
            f"""
            INSERT INTO chunks (
                chunk_id, repo_id, snapshot_id, project_id, module_path, file_path,
                parent_id, kind, fqn, language, symbol_visibility,
                symbol_id, symbol_owner_id, start_line, end_line,
                original_start_line, original_end_line, content_hash,
                version, is_deleted, last_indexed_commit,
                summary, importance, attrs,
                is_test, is_overlay, overlay_session_id, base_chunk_id
            ) VALUES {values_clause}
            ON CONFLICT (chunk_id) DO UPDATE SET
                snapshot_id = EXCLUDED.snapshot_id,
                project_id = EXCLUDED.project_id,
                module_path = EXCLUDED.module_path,
                file_path = EXCLUDED.file_path,
                parent_id = EXCLUDED.parent_id,
                kind = EXCLUDED.kind,
                fqn = EXCLUDED.fqn,
                language = EXCLUDED.language,
                symbol_visibility = EXCLUDED.symbol_visibility,
                symbol_id = EXCLUDED.symbol_id,
                symbol_owner_id = EXCLUDED.symbol_owner_id,
                start_line = EXCLUDED.start_line,
                end_line = EXCLUDED.end_line,
                original_start_line = EXCLUDED.original_start_line,
                original_end_line = EXCLUDED.original_end_line,
                content_hash = EXCLUDED.content_hash,
                version = EXCLUDED.version,
                is_deleted = EXCLUDED.is_deleted,
                last_indexed_commit = EXCLUDED.last_indexed_commit,
                summary = EXCLUDED.summary,
                importance = EXCLUDED.importance,
                attrs = EXCLUDED.attrs,
                is_test = EXCLUDED.is_test,
                is_overlay = EXCLUDED.is_overlay,
                overlay_session_id = EXCLUDED.overlay_session_id,
                base_chunk_id = EXCLUDED.base_chunk_id,
                updated_at = NOW()
            """,
            *values,
        )

    async def get_chunk(self, chunk_id: str) -> Chunk | None:
        """Chunk ID로 조회"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM chunks WHERE chunk_id = $1", chunk_id)
            return self._chunk_from_row(row) if row else None

    async def get_chunks_batch(self, chunk_ids: list[str]) -> dict[str, Chunk]:
        """
        여러 Chunk를 일괄 조회 (단일 쿼리, N+1 방지).

        PostgreSQL의 = ANY() 연산자 사용하여 효율적인 배치 조회.
        """
        if not chunk_ids:
            return {}

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM chunks WHERE chunk_id = ANY($1)", chunk_ids)
            return {row["chunk_id"]: self._chunk_from_row(row) for row in rows}

    async def find_chunks_by_repo(
        self,
        repo_id: str,
        snapshot_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Chunk]:
        """
        Repository의 Chunk 조회 (페이지네이션 지원).

        OOM 방지를 위해 대규모 레포에서는 limit 사용 권장 (예: limit=1000).
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if snapshot_id:
                query = """
                    SELECT * FROM chunks
                    WHERE repo_id = $1 AND snapshot_id = $2 AND is_deleted = FALSE
                    ORDER BY chunk_id
                """
                params = [repo_id, snapshot_id]
            else:
                query = """
                    SELECT * FROM chunks
                    WHERE repo_id = $1 AND is_deleted = FALSE
                    ORDER BY chunk_id
                """
                params = [repo_id]

            # Add pagination
            if limit is not None:
                query += f" LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
                params.extend([limit, offset])
            elif offset > 0:
                query += f" OFFSET ${len(params) + 1}"
                params.append(offset)

            rows = await conn.fetch(query, *params)
            return [self._chunk_from_row(row) for row in rows]

    async def count_chunks_by_repo(self, repo_id: str, snapshot_id: str | None = None) -> int:
        """
        Repository의 Chunk 개수 조회 (효율적인 COUNT 쿼리).

        페이지네이션 시 전체 페이지 수 계산에 사용.
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if snapshot_id:
                row = await conn.fetchrow(
                    """
                    SELECT COUNT(*) as count FROM chunks
                    WHERE repo_id = $1 AND snapshot_id = $2 AND is_deleted = FALSE
                    """,
                    repo_id,
                    snapshot_id,
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT COUNT(*) as count FROM chunks
                    WHERE repo_id = $1 AND is_deleted = FALSE
                    """,
                    repo_id,
                )
            return row["count"] if row else 0

    async def get_chunks_by_file(self, repo_id: str, file_path: str, commit: str | None = None) -> list[Chunk]:
        """파일의 모든 Chunk 조회 (incremental update용)"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if commit:
                rows = await conn.fetch(
                    """
                    SELECT * FROM chunks
                    WHERE repo_id = $1 AND file_path = $2 AND snapshot_id = $3
                    """,
                    repo_id,
                    file_path,
                    commit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM chunks
                    WHERE repo_id = $1 AND file_path = $2
                    ORDER BY snapshot_id DESC
                    """,
                    repo_id,
                    file_path,
                )
            return [self._chunk_from_row(row) for row in rows]

    async def get_chunks_by_files_batch(
        self, repo_id: str, file_paths: list[str], commit: str | None = None
    ) -> dict[str, list[Chunk]]:
        """
        여러 파일의 Chunk를 일괄 조회 (N+1 쿼리 방지용).

        SQL IN 절을 사용하여 한 번의 쿼리로 모든 파일의 chunk를 가져옵니다.
        """
        if not file_paths:
            return {}

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if commit:
                rows = await conn.fetch(
                    """
                    SELECT * FROM chunks
                    WHERE repo_id = $1 AND file_path = ANY($2) AND snapshot_id = $3
                    ORDER BY file_path, start_line
                    """,
                    repo_id,
                    file_paths,
                    commit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM chunks
                    WHERE repo_id = $1 AND file_path = ANY($2)
                    ORDER BY file_path, snapshot_id DESC, start_line
                    """,
                    repo_id,
                    file_paths,
                )

            # Group chunks by file_path
            result: dict[str, list[Chunk]] = {fp: [] for fp in file_paths}
            for row in rows:
                chunk = self._chunk_from_row(row)
                if chunk.file_path in result:
                    result[chunk.file_path].append(chunk)

            return result

    async def find_chunk_by_file_and_line(
        self,
        repo_id: str,
        file_path: str,
        line: int,
    ) -> Chunk | None:
        """
        file+line → Chunk 매핑.

        우선순위: function > class > file
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT *
                FROM chunks
                WHERE repo_id = $1
                  AND file_path = $2
                  AND start_line <= $3
                  AND end_line >= $3
                  AND is_deleted = FALSE
                ORDER BY
                  CASE kind
                    WHEN 'function' THEN 1
                    WHEN 'method' THEN 1
                    WHEN 'class' THEN 2
                    WHEN 'file' THEN 3
                    ELSE 4
                  END,
                  (end_line - start_line) ASC
                LIMIT 1
                """,
                repo_id,
                file_path,
                line,
            )
            return self._chunk_from_row(row) if row else None

    async def find_file_chunk(self, repo_id: str, file_path: str) -> Chunk | None:
        """파일 레벨 Chunk 조회"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM chunks
                WHERE repo_id = $1 AND file_path = $2 AND kind = 'file' AND is_deleted = FALSE
                ORDER BY snapshot_id DESC
                LIMIT 1
                """,
                repo_id,
                file_path,
            )
            return self._chunk_from_row(row) if row else None

    async def find_chunks_by_file_and_lines_batch(
        self,
        repo_id: str,
        locations: list[tuple[str, int]],
    ) -> dict[tuple[str, int], Chunk]:
        """
        여러 (file_path, line) 쌍을 일괄 조회 (N+1 방지).

        단일 쿼리로 모든 위치에 대한 청크를 조회하고,
        각 위치에 대해 가장 적합한 청크를 선택합니다.
        """
        if not locations:
            return {}

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # 고유 파일 경로 추출
            file_paths = list({fp for fp, _ in locations})
            max_line = max(line for _, line in locations)

            # 모든 관련 청크를 한 번에 조회
            rows = await conn.fetch(
                """
                SELECT *
                FROM chunks
                WHERE repo_id = $1
                  AND file_path = ANY($2)
                  AND start_line <= $3
                  AND is_deleted = FALSE
                ORDER BY file_path, start_line
                """,
                repo_id,
                file_paths,
                max_line,
            )

            # 파일별로 청크 그룹화
            chunks_by_file: dict[str, list[Chunk]] = {}
            for row in rows:
                chunk = self._chunk_from_row(row)
                if chunk.file_path not in chunks_by_file:
                    chunks_by_file[chunk.file_path] = []
                chunks_by_file[chunk.file_path].append(chunk)

            # 각 위치에 대해 최적의 청크 선택
            result: dict[tuple[str, int], Chunk] = {}
            for file_path, line in locations:
                candidates = chunks_by_file.get(file_path, [])
                matching = [
                    c
                    for c in candidates
                    if c.start_line is not None and c.end_line is not None and c.start_line <= line <= c.end_line
                ]

                if matching:
                    # 우선순위: function/method > class > file, 그리고 더 작은 span
                    kind_priority = {
                        "function": 1,
                        "method": 1,
                        "class": 2,
                        "file": 3,
                    }
                    matching.sort(key=lambda c: (kind_priority.get(c.kind, 4), (c.end_line or 0) - (c.start_line or 0)))
                    result[(file_path, line)] = matching[0]

            return result

    async def delete_chunks_by_repo(self, repo_id: str, snapshot_id: str) -> None:
        """Repository의 모든 Chunk 삭제 (soft delete)"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE chunks
                SET is_deleted = TRUE, version = version + 1
                WHERE repo_id = $1 AND snapshot_id = $2
                """,
                repo_id,
                snapshot_id,
            )

    # ============================================================
    # Git History Methods (P0-1: Layer 19)
    # ============================================================

    async def save_chunk_history(self, chunk_id: str, history: ChunkHistory) -> None:
        """Save or update chunk history (UPSERT)"""
        import json

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chunk_history (
                    chunk_id, author, last_modified_by, last_modified_at, commit_sha,
                    churn_score, stability_index, contributor_count,
                    co_changed_files, co_change_strength,
                    first_commit_at, days_since_last_change,
                    last_analyzed_at, analysis_version
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW(), 1
                )
                ON CONFLICT (chunk_id) DO UPDATE SET
                    author = EXCLUDED.author,
                    last_modified_by = EXCLUDED.last_modified_by,
                    last_modified_at = EXCLUDED.last_modified_at,
                    commit_sha = EXCLUDED.commit_sha,
                    churn_score = EXCLUDED.churn_score,
                    stability_index = EXCLUDED.stability_index,
                    contributor_count = EXCLUDED.contributor_count,
                    co_changed_files = EXCLUDED.co_changed_files,
                    co_change_strength = EXCLUDED.co_change_strength,
                    first_commit_at = EXCLUDED.first_commit_at,
                    days_since_last_change = EXCLUDED.days_since_last_change,
                    last_analyzed_at = NOW()
                """,
                chunk_id,
                history.author,
                history.last_modified_by,
                history.last_modified_at,
                history.commit_sha,
                history.churn_score,
                history.stability_index,
                history.contributor_count,
                json.dumps(history.co_changed_files),
                json.dumps(history.co_change_strength),
                history.first_commit_at,
                history.days_since_last_change,
            )

    async def save_chunk_histories(self, histories: dict[str, ChunkHistory]) -> None:
        """Batch save chunk histories (for incremental updates)"""
        if not histories:
            return

        BATCH_SIZE = 500
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            async with conn.transaction():
                # Process in batches
                items = list(histories.items())
                for i in range(0, len(items), BATCH_SIZE):
                    batch = items[i : i + BATCH_SIZE]
                    await self._upsert_history_batch(conn, batch)

    async def _upsert_history_batch(self, conn, histories: list[tuple[str, ChunkHistory]]) -> None:
        """Batch UPSERT chunk histories"""
        if not histories:
            return

        import json

        # Prepare batch data
        values = []
        for chunk_id, history in histories:
            values.extend(
                [
                    chunk_id,
                    history.author,
                    history.last_modified_by,
                    history.last_modified_at,
                    history.commit_sha,
                    history.churn_score,
                    history.stability_index,
                    history.contributor_count,
                    json.dumps(history.co_changed_files),
                    json.dumps(history.co_change_strength),
                    history.first_commit_at,
                    history.days_since_last_change,
                ]
            )

        # Build VALUES clause with placeholders
        num_fields = 12
        placeholders = []
        for i in range(len(histories)):
            offset = i * num_fields
            field_placeholders = ", ".join(f"${j}" for j in range(offset + 1, offset + num_fields + 1))
            placeholders.append(f"({field_placeholders}, NOW(), 1)")

        values_clause = ", ".join(placeholders)

        await conn.execute(
            f"""
            INSERT INTO chunk_history (
                chunk_id, author, last_modified_by, last_modified_at, commit_sha,
                churn_score, stability_index, contributor_count,
                co_changed_files, co_change_strength,
                first_commit_at, days_since_last_change,
                last_analyzed_at, analysis_version
            ) VALUES {values_clause}
            ON CONFLICT (chunk_id) DO UPDATE SET
                author = EXCLUDED.author,
                last_modified_by = EXCLUDED.last_modified_by,
                last_modified_at = EXCLUDED.last_modified_at,
                commit_sha = EXCLUDED.commit_sha,
                churn_score = EXCLUDED.churn_score,
                stability_index = EXCLUDED.stability_index,
                contributor_count = EXCLUDED.contributor_count,
                co_changed_files = EXCLUDED.co_changed_files,
                co_change_strength = EXCLUDED.co_change_strength,
                first_commit_at = EXCLUDED.first_commit_at,
                days_since_last_change = EXCLUDED.days_since_last_change,
                last_analyzed_at = NOW()
            """,
            *values,
        )

    def _history_from_row(self, row) -> ChunkHistory:
        """Convert DB row to ChunkHistory model"""
        import json

        return ChunkHistory(
            author=row["author"],
            last_modified_by=row["last_modified_by"],
            last_modified_at=row["last_modified_at"],
            commit_sha=row["commit_sha"],
            churn_score=row["churn_score"],
            stability_index=row["stability_index"],
            contributor_count=row["contributor_count"],
            co_changed_files=json.loads(row.get("co_changed_files", "[]")),
            co_change_strength=json.loads(row.get("co_change_strength", "{}")),
            first_commit_at=row["first_commit_at"],
            days_since_last_change=row["days_since_last_change"],
        )

    async def get_chunk_history(self, chunk_id: str) -> ChunkHistory | None:
        """Get chunk history"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM chunk_history WHERE chunk_id = $1", chunk_id)
            return self._history_from_row(row) if row else None

    async def get_chunk_histories_batch(self, chunk_ids: list[str]) -> dict[str, ChunkHistory]:
        """Batch get chunk histories (N+1 prevention)"""
        if not chunk_ids:
            return {}

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM chunk_history WHERE chunk_id = ANY($1)", chunk_ids)
            return {row["chunk_id"]: self._history_from_row(row) for row in rows}

    # ============================================================
    # GAP #9: Chunk-Graph/IR Mapping Persistence
    # ============================================================

    async def save_chunk_to_graph_mapping(self, repo_id: str, snapshot_id: str, mapping: ChunkToGraph) -> None:
        """
        Save chunk-to-graph mapping (GAP #9).

        Uses batch UPSERT for efficient storage.
        """
        if not mapping:
            return

        import json

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Prepare batch data
                values = []
                for chunk_id, graph_node_ids in mapping.items():
                    values.extend(
                        [
                            repo_id,
                            snapshot_id,
                            chunk_id,
                            json.dumps(list(graph_node_ids)),
                        ]
                    )

                if not values:
                    return

                # Build VALUES clause
                num_fields = 4
                placeholders = []
                for i in range(len(mapping)):
                    offset = i * num_fields
                    field_placeholders = ", ".join(f"${j}" for j in range(offset + 1, offset + num_fields + 1))
                    placeholders.append(f"({field_placeholders})")

                values_clause = ", ".join(placeholders)

                await conn.execute(
                    f"""
                    INSERT INTO chunk_to_graph_mapping (
                        repo_id, snapshot_id, chunk_id, graph_node_ids
                    ) VALUES {values_clause}
                    ON CONFLICT (repo_id, snapshot_id, chunk_id) DO UPDATE SET
                        graph_node_ids = EXCLUDED.graph_node_ids,
                        updated_at = NOW()
                    """,
                    *values,
                )

    async def get_chunk_to_graph_mapping(
        self, repo_id: str, snapshot_id: str, chunk_ids: list[str] | None = None
    ) -> ChunkToGraph:
        """
        Get chunk-to-graph mapping (GAP #9).

        GAP #10: Optimized with proper indexing.
        """
        import json

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if chunk_ids:
                rows = await conn.fetch(
                    """
                    SELECT chunk_id, graph_node_ids
                    FROM chunk_to_graph_mapping
                    WHERE repo_id = $1 AND snapshot_id = $2 AND chunk_id = ANY($3)
                    """,
                    repo_id,
                    snapshot_id,
                    chunk_ids,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT chunk_id, graph_node_ids
                    FROM chunk_to_graph_mapping
                    WHERE repo_id = $1 AND snapshot_id = $2
                    """,
                    repo_id,
                    snapshot_id,
                )

            return {row["chunk_id"]: set(json.loads(row["graph_node_ids"])) for row in rows}

    async def save_chunk_to_ir_mapping(self, repo_id: str, snapshot_id: str, mapping: ChunkToIR) -> None:
        """
        Save chunk-to-IR mapping (GAP #9).

        Uses batch UPSERT for efficient storage.
        """
        if not mapping:
            return

        import json

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Prepare batch data
                values = []
                for chunk_id, ir_node_ids in mapping.items():
                    values.extend(
                        [
                            repo_id,
                            snapshot_id,
                            chunk_id,
                            json.dumps(list(ir_node_ids)),
                        ]
                    )

                if not values:
                    return

                # Build VALUES clause
                num_fields = 4
                placeholders = []
                for i in range(len(mapping)):
                    offset = i * num_fields
                    field_placeholders = ", ".join(f"${j}" for j in range(offset + 1, offset + num_fields + 1))
                    placeholders.append(f"({field_placeholders})")

                values_clause = ", ".join(placeholders)

                await conn.execute(
                    f"""
                    INSERT INTO chunk_to_ir_mapping (
                        repo_id, snapshot_id, chunk_id, ir_node_ids
                    ) VALUES {values_clause}
                    ON CONFLICT (repo_id, snapshot_id, chunk_id) DO UPDATE SET
                        ir_node_ids = EXCLUDED.ir_node_ids,
                        updated_at = NOW()
                    """,
                    *values,
                )

    async def get_chunk_to_ir_mapping(
        self, repo_id: str, snapshot_id: str, chunk_ids: list[str] | None = None
    ) -> ChunkToIR:
        """
        Get chunk-to-IR mapping (GAP #9).

        GAP #10: Optimized with proper indexing.
        """
        import json

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if chunk_ids:
                rows = await conn.fetch(
                    """
                    SELECT chunk_id, ir_node_ids
                    FROM chunk_to_ir_mapping
                    WHERE repo_id = $1 AND snapshot_id = $2 AND chunk_id = ANY($3)
                    """,
                    repo_id,
                    snapshot_id,
                    chunk_ids,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT chunk_id, ir_node_ids
                    FROM chunk_to_ir_mapping
                    WHERE repo_id = $1 AND snapshot_id = $2
                    """,
                    repo_id,
                    snapshot_id,
                )

            return {row["chunk_id"]: set(json.loads(row["ir_node_ids"])) for row in rows}
