"""
ChunkStore - Chunk 저장소 인터페이스 및 구현

Chunk CRUD 및 Zoekt 매핑용 file+line 조회 기능 제공.
"""

from abc import abstractmethod
from typing import Protocol

from src.foundation.chunk.models import Chunk


class ChunkStore(Protocol):
    """
    Chunk 저장소 포트.

    주요 기능:
    - Chunk CRUD
    - file_path + line → Chunk 매핑 (Zoekt 통합용)
    - Incremental update 지원 (get_chunks_by_file, save_chunks)
    """

    @abstractmethod
    def save_chunk(self, chunk: Chunk) -> None:
        """Chunk 저장"""
        ...

    @abstractmethod
    def save_chunks(self, chunks: list[Chunk]) -> None:
        """
        여러 Chunk를 일괄 저장 (incremental update용).

        Args:
            chunks: 저장할 Chunk 리스트
        """
        ...

    @abstractmethod
    def get_chunk(self, chunk_id: str) -> Chunk | None:
        """Chunk ID로 조회"""
        ...

    @abstractmethod
    def get_chunks_batch(self, chunk_ids: list[str]) -> dict[str, Chunk]:
        """
        여러 Chunk를 일괄 조회 (N+1 쿼리 방지용).

        Args:
            chunk_ids: 조회할 Chunk ID 리스트

        Returns:
            chunk_id → Chunk 매핑 딕셔너리 (존재하지 않는 ID는 제외)
        """
        ...

    @abstractmethod
    def find_chunks_by_repo(self, repo_id: str, snapshot_id: str | None = None) -> list[Chunk]:
        """Repository의 모든 Chunk 조회"""
        ...

    @abstractmethod
    def get_chunks_by_file(self, repo_id: str, file_path: str, commit: str | None = None) -> list[Chunk]:
        """
        파일의 모든 Chunk 조회 (incremental update용).

        Args:
            repo_id: Repository ID
            file_path: 파일 경로
            commit: 커밋 해시 (snapshot_id로 사용, None이면 최신)

        Returns:
            파일에 속한 모든 Chunk 리스트
        """
        ...

    @abstractmethod
    def find_chunk_by_file_and_line(
        self,
        repo_id: str,
        file_path: str,
        line: int,
    ) -> Chunk | None:
        """
        Zoekt 결과(file+line)를 Chunk로 매핑.

        우선순위:
        1. function/method chunk (line이 포함된 가장 작은 chunk)
        2. class chunk
        3. file chunk

        Args:
            repo_id: Repository ID
            file_path: 파일 경로
            line: 줄 번호

        Returns:
            매핑된 Chunk (없으면 None)
        """
        ...

    @abstractmethod
    def find_file_chunk(self, repo_id: str, file_path: str) -> Chunk | None:
        """
        파일 레벨 Chunk 조회 (fallback용).

        Args:
            repo_id: Repository ID
            file_path: 파일 경로

        Returns:
            File chunk (없으면 None)
        """
        ...

    @abstractmethod
    def delete_chunks_by_repo(self, repo_id: str, snapshot_id: str) -> None:
        """Repository의 모든 Chunk 삭제"""
        ...


class InMemoryChunkStore:
    """
    In-memory ChunkStore 구현 (최적화됨).

    테스트 및 개발용.

    최적화:
    - file_index를 Set으로 변경하여 O(1) 중복 체크
    - chunk_id만 저장하여 메모리 효율 개선
    """

    def __init__(self):
        self.chunks: dict[str, Chunk] = {}
        # (repo_id, file_path) → set[chunk_id] (최적화: List 대신 Set 사용)
        self.file_index: dict[tuple[str, str], set[str]] = {}

    def save_chunk(self, chunk: Chunk) -> None:
        """Chunk 저장"""
        self.chunks[chunk.chunk_id] = chunk

        # 파일 인덱스 업데이트 (O(1) 중복 체크)
        if chunk.file_path:
            key = (chunk.repo_id, chunk.file_path)
            if key not in self.file_index:
                self.file_index[key] = set()
            self.file_index[key].add(chunk.chunk_id)  # O(1) 추가

    def save_chunks(self, chunks: list[Chunk]) -> None:
        """여러 Chunk를 일괄 저장"""
        for chunk in chunks:
            self.save_chunk(chunk)

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        """Chunk ID로 조회"""
        return self.chunks.get(chunk_id)

    def get_chunks_batch(self, chunk_ids: list[str]) -> dict[str, Chunk]:
        """여러 Chunk를 일괄 조회 (O(n) 성능)"""
        return {cid: self.chunks[cid] for cid in chunk_ids if cid in self.chunks}

    def find_chunks_by_repo(self, repo_id: str, snapshot_id: str | None = None) -> list[Chunk]:
        """Repository의 모든 Chunk 조회"""
        return [
            c
            for c in self.chunks.values()
            if c.repo_id == repo_id and (snapshot_id is None or c.snapshot_id == snapshot_id)
        ]

    def get_chunks_by_file(self, repo_id: str, file_path: str, commit: str | None = None) -> list[Chunk]:
        """파일의 모든 Chunk 조회 (incremental update용)"""
        key = (repo_id, file_path)
        chunk_ids = self.file_index.get(key, set())

        # chunk_id로 Chunk 객체 조회
        candidates = [self.chunks[cid] for cid in chunk_ids if cid in self.chunks]

        if commit is None:
            return candidates

        # commit (snapshot_id) 필터링
        return [c for c in candidates if c.snapshot_id == commit]

    def find_chunk_by_file_and_line(
        self,
        repo_id: str,
        file_path: str,
        line: int,
    ) -> Chunk | None:
        """
        file+line → Chunk 매핑.

        우선순위: function > class > file
        """
        key = (repo_id, file_path)
        chunk_ids = self.file_index.get(key, set())

        # chunk_id로 Chunk 객체 조회
        candidates = [self.chunks[cid] for cid in chunk_ids if cid in self.chunks]

        # line이 포함된 chunk 필터링
        matching = [
            c
            for c in candidates
            if c.start_line is not None and c.end_line is not None and c.start_line <= line <= c.end_line
        ]

        if not matching:
            return None

        # 우선순위 정렬
        def priority_key(chunk: Chunk) -> tuple[int, int]:
            # kind 우선순위: function(1) > class(2) > file(3) > other(4)
            kind_priority = {
                "function": 1,
                "method": 1,
                "class": 2,
                "file": 3,
            }
            priority = kind_priority.get(chunk.kind, 4)

            # 같은 우선순위면 더 작은 chunk 선택 (end_line - start_line)
            span = (chunk.end_line or 0) - (chunk.start_line or 0)
            return (priority, span)

        matching.sort(key=priority_key)
        return matching[0]

    def find_file_chunk(self, repo_id: str, file_path: str) -> Chunk | None:
        """파일 레벨 Chunk 조회"""
        key = (repo_id, file_path)
        chunk_ids = self.file_index.get(key, set())

        # chunk_id로 Chunk 객체 조회
        candidates = [self.chunks[cid] for cid in chunk_ids if cid in self.chunks]
        file_chunks = [c for c in candidates if c.kind == "file"]
        return file_chunks[0] if file_chunks else None

    def delete_chunks_by_repo(self, repo_id: str, snapshot_id: str) -> None:
        """Repository의 모든 Chunk 삭제"""
        to_delete = [cid for cid, c in self.chunks.items() if c.repo_id == repo_id and c.snapshot_id == snapshot_id]

        for cid in to_delete:
            chunk = self.chunks.pop(cid)
            # file_index에서 제거 (Set 사용)
            if chunk.file_path:
                key = (chunk.repo_id, chunk.file_path)
                if key in self.file_index:
                    self.file_index[key].discard(cid)  # O(1) 제거


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

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self._pool = None

    async def _get_pool(self):
        """Get or create connection pool"""
        if self._pool is None:
            import asyncpg

            self._pool = await asyncpg.create_pool(self.connection_string)
        return self._pool

    async def close(self):
        """Close connection pool"""
        if self._pool:
            await self._pool.close()
            self._pool = None

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
        )

    async def save_chunk(self, chunk: Chunk) -> None:
        """Chunk 저장 (UPSERT)"""
        import json

        pool = await self._get_pool()
        attrs = chunk.attrs.copy()
        attrs["children"] = chunk.children  # Store children in attrs

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO chunks (
                    chunk_id, repo_id, snapshot_id, project_id, module_path, file_path,
                    parent_id, kind, fqn, language, symbol_visibility,
                    symbol_id, symbol_owner_id, start_line, end_line,
                    original_start_line, original_end_line, content_hash,
                    version, is_deleted, last_indexed_commit,
                    summary, importance, attrs
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                    $16, $17, $18, $19, $20, $21, $22, $23, $24
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
                    attrs = EXCLUDED.attrs
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
                json.dumps(attrs),
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

        # Prepare batch data
        values = []
        for chunk in chunks:
            attrs = chunk.attrs.copy()
            attrs["children"] = chunk.children
            values.extend(
                [
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
                    json.dumps(attrs),
                ]
            )

        # Build VALUES clause with placeholders
        num_fields = 24
        placeholders = []
        for i in range(len(chunks)):
            offset = i * num_fields
            field_placeholders = ", ".join(f"${j}" for j in range(offset + 1, offset + num_fields + 1))
            placeholders.append(f"({field_placeholders})")

        values_clause = ", ".join(placeholders)

        await conn.execute(
            f"""
            INSERT INTO chunks (
                chunk_id, repo_id, snapshot_id, project_id, module_path, file_path,
                parent_id, kind, fqn, language, symbol_visibility,
                symbol_id, symbol_owner_id, start_line, end_line,
                original_start_line, original_end_line, content_hash,
                version, is_deleted, last_indexed_commit,
                summary, importance, attrs
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

    async def find_chunks_by_repo(self, repo_id: str, snapshot_id: str | None = None) -> list[Chunk]:
        """Repository의 모든 Chunk 조회"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if snapshot_id:
                rows = await conn.fetch(
                    """
                    SELECT * FROM chunks
                    WHERE repo_id = $1 AND snapshot_id = $2 AND is_deleted = FALSE
                    """,
                    repo_id,
                    snapshot_id,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM chunks
                    WHERE repo_id = $1 AND is_deleted = FALSE
                    """,
                    repo_id,
                )
            return [self._chunk_from_row(row) for row in rows]

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
