"""
InMemoryChunkStore - In-memory ChunkStore 구현

테스트 및 개발용 구현.
"""

import asyncio

from src.contexts.code_foundation.infrastructure.chunk.models import Chunk, ChunkHistory, ChunkToGraph, ChunkToIR


class InMemoryChunkStore:
    """
    In-memory ChunkStore 구현 (Async 래퍼).

    테스트 및 개발용.

    최적화:
    - file_index를 Set으로 변경하여 O(1) 중복 체크
    - chunk_id만 저장하여 메모리 효율 개선
    - Async 래퍼로 ChunkStore Protocol 준수

    Thread Safety (GAP G2):
    - asyncio.Lock으로 async 환경에서 동시성 보장
    - 모든 write operation은 lock으로 보호됨
    """

    def __init__(self):
        self.chunks: dict[str, Chunk] = {}
        # (repo_id, file_path) → set[chunk_id] (최적화: List 대신 Set 사용)
        self.file_index: dict[tuple[str, str], set[str]] = {}
        # chunk_id → ChunkHistory (Git history storage)
        self.histories: dict[str, ChunkHistory] = {}
        # GAP #9: Mapping storage
        # (repo_id, snapshot_id) → ChunkToGraph
        self.chunk_to_graph_mappings: dict[tuple[str, str], ChunkToGraph] = {}
        # (repo_id, snapshot_id) → ChunkToIR
        self.chunk_to_ir_mappings: dict[tuple[str, str], ChunkToIR] = {}
        # GAP G2: Async lock for concurrent access safety
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> "asyncio.Lock":
        """Get or create asyncio lock (lazy initialization for non-async contexts)."""
        import asyncio

        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def save_chunk(self, chunk: Chunk) -> None:
        """Chunk 저장 (async 래퍼, thread-safe)"""
        async with self._get_lock():
            self.chunks[chunk.chunk_id] = chunk

            # 파일 인덱스 업데이트 (O(1) 중복 체크)
            if chunk.file_path:
                key = (chunk.repo_id, chunk.file_path)
                if key not in self.file_index:
                    self.file_index[key] = set()
                self.file_index[key].add(chunk.chunk_id)  # O(1) 추가

    async def save_chunks(self, chunks: list[Chunk]) -> None:
        """여러 Chunk를 일괄 저장 (async 래퍼, thread-safe)"""
        async with self._get_lock():
            for chunk in chunks:
                self.chunks[chunk.chunk_id] = chunk
                if chunk.file_path:
                    key = (chunk.repo_id, chunk.file_path)
                    if key not in self.file_index:
                        self.file_index[key] = set()
                    self.file_index[key].add(chunk.chunk_id)

    async def get_chunk(self, chunk_id: str) -> Chunk | None:
        """Chunk ID로 조회 (async 래퍼)"""
        return self.chunks.get(chunk_id)

    async def get_chunks_batch(self, chunk_ids: list[str]) -> dict[str, Chunk]:
        """여러 Chunk를 일괄 조회 (O(n) 성능, async 래퍼)"""
        return {cid: self.chunks[cid] for cid in chunk_ids if cid in self.chunks}

    async def find_chunks_by_repo(
        self,
        repo_id: str,
        snapshot_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Chunk]:
        """Repository의 Chunk 조회 (페이지네이션 지원, async 래퍼)"""
        all_chunks = [
            c
            for c in self.chunks.values()
            if c.repo_id == repo_id and (snapshot_id is None or c.snapshot_id == snapshot_id)
        ]
        # Sort for consistent pagination (by chunk_id)
        all_chunks.sort(key=lambda c: c.chunk_id)

        # Apply pagination
        if limit is None:
            return all_chunks[offset:]
        return all_chunks[offset : offset + limit]

    async def count_chunks_by_repo(self, repo_id: str, snapshot_id: str | None = None) -> int:
        """Repository의 Chunk 개수 조회 (async 래퍼)"""
        return sum(
            1
            for c in self.chunks.values()
            if c.repo_id == repo_id and (snapshot_id is None or c.snapshot_id == snapshot_id)
        )

    async def get_chunks_by_file(self, repo_id: str, file_path: str, commit: str | None = None) -> list[Chunk]:
        """파일의 모든 Chunk 조회 (incremental update용, async 래퍼)"""
        key = (repo_id, file_path)
        chunk_ids = self.file_index.get(key, set())

        # chunk_id로 Chunk 객체 조회
        candidates = [self.chunks[cid] for cid in chunk_ids if cid in self.chunks]

        if commit is None:
            return candidates

        # commit (snapshot_id) 필터링
        return [c for c in candidates if c.snapshot_id == commit]

    async def get_chunks_by_files_batch(
        self, repo_id: str, file_paths: list[str], commit: str | None = None
    ) -> dict[str, list[Chunk]]:
        """여러 파일의 Chunk를 일괄 조회"""
        result = {}
        for file_path in file_paths:
            chunks = await self.get_chunks_by_file(repo_id, file_path, commit)
            result[file_path] = chunks
        return result

    async def find_chunk_by_file_and_line(
        self,
        repo_id: str,
        file_path: str,
        line: int,
    ) -> Chunk | None:
        """
        file+line → Chunk 매핑 (async 래퍼).

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

    async def find_file_chunk(self, repo_id: str, file_path: str) -> Chunk | None:
        """파일 레벨 Chunk 조회 (async 래퍼)"""
        key = (repo_id, file_path)
        chunk_ids = self.file_index.get(key, set())

        # chunk_id로 Chunk 객체 조회
        candidates = [self.chunks[cid] for cid in chunk_ids if cid in self.chunks]
        file_chunks = [c for c in candidates if c.kind == "file"]
        return file_chunks[0] if file_chunks else None

    async def find_chunks_by_file_and_lines_batch(
        self,
        repo_id: str,
        locations: list[tuple[str, int]],
    ) -> dict[tuple[str, int], Chunk]:
        """여러 (file_path, line) 쌍을 일괄 조회 (N+1 방지).

        최적화: 파일별로 그룹핑하여 한 번에 조회 후 메모리에서 매칭.
        """
        if not locations:
            return {}

        result: dict[tuple[str, int], Chunk] = {}

        # 파일별로 locations 그룹핑
        by_file: dict[str, list[int]] = {}
        for file_path, line in locations:
            by_file.setdefault(file_path, []).append(line)

        # 파일별로 한 번에 청크 조회 후 매칭
        for file_path, lines in by_file.items():
            key = (repo_id, file_path)
            chunk_ids = self.file_index.get(key, set())
            candidates = [self.chunks[cid] for cid in chunk_ids if cid in self.chunks]

            # 각 line에 대해 최적의 청크 매칭 (메모리 내 처리)
            for line in lines:
                matching = [
                    c
                    for c in candidates
                    if c.start_line is not None and c.end_line is not None and c.start_line <= line <= c.end_line
                ]
                if matching:
                    # 우선순위: function > class > method > file
                    kind_priority = {"function": 0, "class": 1, "method": 2, "file": 3}
                    matching.sort(
                        key=lambda c: (
                            kind_priority.get(c.kind, 4),
                            (c.end_line or 0) - (c.start_line or 0),
                        )
                    )
                    result[(file_path, line)] = matching[0]

        return result

    async def delete_chunks_by_repo(self, repo_id: str, snapshot_id: str) -> None:
        """Repository의 모든 Chunk 삭제 (async 래퍼, thread-safe)"""
        async with self._get_lock():
            to_delete = [cid for cid, c in self.chunks.items() if c.repo_id == repo_id and c.snapshot_id == snapshot_id]

            for cid in to_delete:
                chunk = self.chunks.pop(cid)
                # file_index에서 제거 (Set 사용)
                if chunk.file_path:
                    key = (chunk.repo_id, chunk.file_path)
                    if key in self.file_index:
                        self.file_index[key].discard(cid)  # O(1) 제거
                # histories에서도 제거
                self.histories.pop(cid, None)

    # ============================================================
    # Git History Methods (P0-1: Layer 19)
    # ============================================================

    async def save_chunk_history(self, chunk_id: str, history: ChunkHistory) -> None:
        """Save chunk history (async 래퍼, thread-safe)"""
        async with self._get_lock():
            self.histories[chunk_id] = history

    async def save_chunk_histories(self, histories: dict[str, ChunkHistory]) -> None:
        """Batch save chunk histories (async 래퍼, thread-safe)"""
        async with self._get_lock():
            self.histories.update(histories)

    async def get_chunk_history(self, chunk_id: str) -> ChunkHistory | None:
        """Get chunk history (async 래퍼)"""
        return self.histories.get(chunk_id)

    async def get_chunk_histories_batch(self, chunk_ids: list[str]) -> dict[str, ChunkHistory]:
        """Batch get chunk histories (async 래퍼)"""
        return {cid: self.histories[cid] for cid in chunk_ids if cid in self.histories}

    # ============================================================
    # GAP #9: Chunk-Graph/IR Mapping Persistence
    # ============================================================

    async def save_chunk_to_graph_mapping(self, repo_id: str, snapshot_id: str, mapping: ChunkToGraph) -> None:
        """Save chunk-to-graph mapping (GAP #9, thread-safe)"""
        async with self._get_lock():
            key = (repo_id, snapshot_id)
            if key not in self.chunk_to_graph_mappings:
                self.chunk_to_graph_mappings[key] = {}
            self.chunk_to_graph_mappings[key].update(mapping)

    async def get_chunk_to_graph_mapping(
        self, repo_id: str, snapshot_id: str, chunk_ids: list[str] | None = None
    ) -> ChunkToGraph:
        """Get chunk-to-graph mapping (GAP #9)"""
        key = (repo_id, snapshot_id)
        all_mappings = self.chunk_to_graph_mappings.get(key, {})

        if chunk_ids is None:
            return all_mappings

        return {cid: all_mappings[cid] for cid in chunk_ids if cid in all_mappings}

    async def save_chunk_to_ir_mapping(self, repo_id: str, snapshot_id: str, mapping: ChunkToIR) -> None:
        """Save chunk-to-IR mapping (GAP #9, thread-safe)"""
        async with self._get_lock():
            key = (repo_id, snapshot_id)
            if key not in self.chunk_to_ir_mappings:
                self.chunk_to_ir_mappings[key] = {}
            self.chunk_to_ir_mappings[key].update(mapping)

    async def get_chunk_to_ir_mapping(
        self, repo_id: str, snapshot_id: str, chunk_ids: list[str] | None = None
    ) -> ChunkToIR:
        """Get chunk-to-IR mapping (GAP #9)"""
        key = (repo_id, snapshot_id)
        all_mappings = self.chunk_to_ir_mappings.get(key, {})

        if chunk_ids is None:
            return all_mappings

        return {cid: all_mappings[cid] for cid in chunk_ids if cid in all_mappings}
