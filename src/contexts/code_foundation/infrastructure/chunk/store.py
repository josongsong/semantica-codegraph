"""
ChunkStore - Chunk 저장소 인터페이스

Chunk CRUD 및 Zoekt 매핑용 file+line 조회 기능 제공.

페이지네이션 사용 예제:
    ```python
    # 전체 개수 조회
    total = await store.count_chunks_by_repo("my_repo", "snapshot_123")

    # 페이지 단위로 조회 (1000개씩)
    page_size = 1000
    for page in range(0, (total + page_size - 1) // page_size):
        chunks = await store.find_chunks_by_repo(
            "my_repo", "snapshot_123",
            limit=page_size, offset=page * page_size
        )
        process_chunks(chunks)
    ```

구현체 (별도 파일로 분리):
- InMemoryChunkStore: 테스트용 (store_memory.py)
- PostgresChunkStore: 프로덕션용 (store_postgres.py)
"""

from abc import abstractmethod
from typing import Protocol

from src.contexts.code_foundation.infrastructure.chunk.models import Chunk, ChunkHistory, ChunkToGraph, ChunkToIR

# Re-export implementations for backward compatibility
from src.contexts.code_foundation.infrastructure.chunk.store_memory import InMemoryChunkStore
from src.contexts.code_foundation.infrastructure.chunk.store_postgres import PostgresChunkStore

__all__ = [
    "ChunkStore",
    "InMemoryChunkStore",
    "PostgresChunkStore",
]


class ChunkStore(Protocol):
    """
    Chunk 저장소 포트 (Async Protocol).

    주요 기능:
    - Chunk CRUD
    - file_path + line → Chunk 매핑 (Zoekt 통합용)
    - Incremental update 지원 (get_chunks_by_file, save_chunks)

    모든 메서드는 async이며 await로 호출해야 합니다:
        ```python
        # ✅ 올바른 사용
        chunk = await store.get_chunk(chunk_id)
        chunks = await store.find_chunks_by_repo(repo_id, snapshot_id)

        # ❌ 잘못된 사용
        chunk = store.get_chunk(chunk_id)  # TypeError
        ```

    구현체:
    - InMemoryChunkStore: 테스트용 (async 래퍼)
    - PostgresChunkStore: 프로덕션용 (네이티브 async)
    """

    @abstractmethod
    async def save_chunk(self, chunk: Chunk) -> None:
        """Chunk 저장"""
        ...

    @abstractmethod
    async def save_chunks(self, chunks: list[Chunk]) -> None:
        """
        여러 Chunk를 일괄 저장 (incremental update용).

        Args:
            chunks: 저장할 Chunk 리스트
        """
        ...

    @abstractmethod
    async def get_chunk(self, chunk_id: str) -> Chunk | None:
        """Chunk ID로 조회"""
        ...

    @abstractmethod
    async def get_chunks_batch(self, chunk_ids: list[str]) -> dict[str, Chunk]:
        """
        여러 Chunk를 일괄 조회 (N+1 쿼리 방지용).

        Args:
            chunk_ids: 조회할 Chunk ID 리스트

        Returns:
            chunk_id → Chunk 매핑 딕셔너리 (존재하지 않는 ID는 제외)
        """
        ...

    @abstractmethod
    async def find_chunks_by_repo(
        self,
        repo_id: str,
        snapshot_id: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Chunk]:
        """
        Repository의 Chunk 조회 (페이지네이션 지원).

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID (None이면 모든 스냅샷)
            limit: 최대 조회 개수 (None이면 전체, OOM 방지를 위해 기본값 권장)
            offset: 시작 오프셋 (0부터 시작)

        Returns:
            Chunk 리스트 (limit/offset 적용)
        """
        ...

    @abstractmethod
    async def count_chunks_by_repo(self, repo_id: str, snapshot_id: str | None = None) -> int:
        """
        Repository의 Chunk 개수 조회 (페이지네이션용).

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID (None이면 모든 스냅샷)

        Returns:
            총 Chunk 개수
        """
        ...

    @abstractmethod
    async def get_chunks_by_file(self, repo_id: str, file_path: str, commit: str | None = None) -> list[Chunk]:
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
    async def get_chunks_by_files_batch(
        self, repo_id: str, file_paths: list[str], commit: str | None = None
    ) -> dict[str, list[Chunk]]:
        """
        여러 파일의 Chunk를 일괄 조회 (N+1 쿼리 방지용).

        Args:
            repo_id: Repository ID
            file_paths: 파일 경로 리스트
            commit: 커밋 해시 (snapshot_id로 사용, None이면 최신)

        Returns:
            file_path → Chunk 리스트 매핑 딕셔너리
        """
        ...

    @abstractmethod
    async def find_chunk_by_file_and_line(
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
    async def find_file_chunk(self, repo_id: str, file_path: str) -> Chunk | None:
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
    async def find_chunks_by_file_and_lines_batch(
        self,
        repo_id: str,
        locations: list[tuple[str, int]],
    ) -> dict[tuple[str, int], Chunk]:
        """
        여러 (file_path, line) 쌍을 일괄 조회 (N+1 쿼리 방지).

        Zoekt 검색 결과를 Chunk로 배치 매핑할 때 사용.

        Args:
            repo_id: Repository ID
            locations: (file_path, line) 튜플 리스트

        Returns:
            (file_path, line) → Chunk 매핑 딕셔너리
        """
        ...

    @abstractmethod
    async def delete_chunks_by_repo(self, repo_id: str, snapshot_id: str) -> None:
        """Repository의 모든 Chunk 삭제"""
        ...

    # ============================================================
    # Git History Methods (P0-1: Layer 19)
    # ============================================================

    @abstractmethod
    async def save_chunk_history(self, chunk_id: str, history: ChunkHistory) -> None:
        """
        Save or update Git history for a chunk.

        Args:
            chunk_id: Chunk ID
            history: ChunkHistory data
        """
        ...

    @abstractmethod
    async def save_chunk_histories(self, histories: dict[str, ChunkHistory]) -> None:
        """
        Batch save chunk histories (for incremental updates).

        Args:
            histories: Mapping of chunk_id → ChunkHistory
        """
        ...

    @abstractmethod
    async def get_chunk_history(self, chunk_id: str) -> ChunkHistory | None:
        """
        Get Git history for a chunk.

        Args:
            chunk_id: Chunk ID

        Returns:
            ChunkHistory if exists, None otherwise
        """
        ...

    @abstractmethod
    async def get_chunk_histories_batch(self, chunk_ids: list[str]) -> dict[str, ChunkHistory]:
        """
        Batch get chunk histories (N+1 prevention).

        Args:
            chunk_ids: List of chunk IDs

        Returns:
            Mapping of chunk_id → ChunkHistory (missing IDs excluded)
        """
        ...

    # ============================================================
    # GAP #9: Chunk-Graph/IR Mapping Persistence
    # ============================================================

    @abstractmethod
    async def save_chunk_to_graph_mapping(self, repo_id: str, snapshot_id: str, mapping: ChunkToGraph) -> None:
        """
        Save chunk-to-graph mapping (GAP #9).

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            mapping: Chunk ID → set of graph node IDs
        """
        ...

    @abstractmethod
    async def get_chunk_to_graph_mapping(
        self, repo_id: str, snapshot_id: str, chunk_ids: list[str] | None = None
    ) -> ChunkToGraph:
        """
        Get chunk-to-graph mapping (GAP #9).

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            chunk_ids: Optional list of chunk IDs to filter (None = all)

        Returns:
            Mapping of chunk_id → set of graph node IDs
        """
        ...

    @abstractmethod
    async def save_chunk_to_ir_mapping(self, repo_id: str, snapshot_id: str, mapping: ChunkToIR) -> None:
        """
        Save chunk-to-IR mapping (GAP #9).

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            mapping: Chunk ID → set of IR node IDs
        """
        ...

    @abstractmethod
    async def get_chunk_to_ir_mapping(
        self, repo_id: str, snapshot_id: str, chunk_ids: list[str] | None = None
    ) -> ChunkToIR:
        """
        Get chunk-to-IR mapping (GAP #9).

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            chunk_ids: Optional list of chunk IDs to filter (None = all)

        Returns:
            Mapping of chunk_id → set of IR node IDs
        """
        ...
