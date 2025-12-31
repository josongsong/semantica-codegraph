"""
Multi Index Domain Ports

다중 인덱스 관리 포트
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .models import DeleteResult, UpsertResult

if TYPE_CHECKING:
    from codegraph_engine.multi_index.infrastructure.common.documents import IndexDocument, SearchHit


# ============================================================
# Lexical Index Port (RFC-020 Phase 4: SOTA Batch Indexing)
# ============================================================


class IndexingMode(Enum):
    """Indexing performance mode"""

    CONSERVATIVE = "conservative"  # 512MB heap, 4 threads - 안정적
    BALANCED = "balanced"  # 1024MB heap, 8 threads - 기본값
    AGGRESSIVE = "aggressive"  # 2048MB heap, 16 threads - 최고 성능


@dataclass(frozen=True)
class FileToIndex:
    """File indexing input (immutable)"""

    repo_id: str
    file_path: str
    content: str

    def __post_init__(self):
        """Validate inputs"""
        if not self.repo_id:
            raise ValueError("repo_id cannot be empty")
        if not self.file_path:
            raise ValueError("file_path cannot be empty")
        if not isinstance(self.content, str):
            raise TypeError(f"content must be str, got {type(self.content)}")


@dataclass
class IndexingResult:
    """Batch indexing result"""

    total_files: int
    success_count: int
    failed_files: list[tuple[str, str]]  # (file_path, error_message)
    duration_seconds: float

    @property
    def is_partial_success(self) -> bool:
        """Check if some files failed"""
        return 0 < self.success_count < self.total_files

    @property
    def is_complete_success(self) -> bool:
        """Check if all files succeeded"""
        return self.success_count == self.total_files

    @property
    def is_complete_failure(self) -> bool:
        """Check if all files failed"""
        return self.success_count == 0


@runtime_checkable
class LexicalIndexPort(Protocol):
    """
    Lexical Index Port (Code Search)

    Domain-level abstraction for lexical code indexing.
    Implementations should provide:
    - File-based code indexing
    - Batch operations for performance
    - Full-text search capabilities

    Current Implementation:
        - TantivyCodeIndex (RFC-020)
    """

    async def index_file(self, repo_id: str, file_path: str, content: str) -> bool:
        """
        Index a single file (backward compatibility)

        Args:
            repo_id: Repository ID
            file_path: File path
            content: File content

        Returns:
            Success boolean
        """
        ...

    async def index_files_batch(self, files: list[FileToIndex], fail_fast: bool = False) -> IndexingResult:
        """
        Index multiple files in batch (SOTA performance)

        Args:
            files: List of files to index
            fail_fast: If True, stop on first error

        Returns:
            IndexingResult with success/failure details

        Raises:
            ValueError: If files list is empty
        """
        ...

    async def delete_file(self, repo_id: str, file_path: str) -> bool:
        """
        Delete a file from index

        Args:
            repo_id: Repository ID
            file_path: File path

        Returns:
            Success boolean
        """
        ...

    async def close(self) -> None:
        """
        Close index and release resources

        Should be called on application shutdown
        """
        ...


class IndexPort(Protocol):
    """인덱스 포트 (Legacy)"""

    async def upsert(self, data: list[dict], repo_id: str) -> UpsertResult:
        """데이터 업서트"""
        ...

    async def delete(self, ids: list[str], repo_id: str) -> DeleteResult:
        """데이터 삭제"""
        ...

    async def search(self, query: str, repo_id: str, limit: int) -> list[dict]:
        """검색"""
        ...


@runtime_checkable
class SearchableIndex(Protocol):
    """
    검색 가능한 인덱스 Protocol.

    모든 인덱스 어댑터가 구현해야 하는 검색 인터페이스.
    IndexRegistry에서 등록된 인덱스의 타입 안전성을 보장.

    Implementations:
        - TantivyCodeIndex (lexical) ← RFC-020
        - QdrantVectorIndex (vector)
        - MemgraphSymbolIndex (symbol)
        - DomainMetaIndex (domain)

    """

    async def search(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        limit: int = 50,
    ) -> list["SearchHit"]:
        """
        검색 수행.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            query: 검색 쿼리
            limit: 최대 결과 수

        Returns:
            SearchHit 리스트
        """
        ...


@runtime_checkable
class IndexableIndex(Protocol):
    """
    인덱싱 가능한 인덱스 Protocol.

    전체 인덱싱(full index)을 지원하는 인덱스 어댑터용.

    Implementations:
        - QdrantVectorIndex
        - PostgresFuzzyIndex
        - DomainMetaIndex
    """

    async def index(
        self,
        repo_id: str,
        snapshot_id: str,
        docs: list["IndexDocument"],
    ) -> None:
        """
        전체 인덱싱.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            docs: 인덱싱할 문서 리스트
        """
        ...


@runtime_checkable
class UpsertableIndex(Protocol):
    """
    Upsert 가능한 인덱스 Protocol.

    증분 업데이트를 지원하는 인덱스 어댑터용.

    Implementations:
        - QdrantVectorIndex
        - PostgresFuzzyIndex
        - DomainMetaIndex
        - MemgraphSymbolIndex
    """

    async def upsert(
        self,
        repo_id: str,
        snapshot_id: str,
        docs: list["IndexDocument"],
    ) -> None:
        """
        문서 Upsert.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            docs: Upsert할 문서 리스트
        """
        ...


@runtime_checkable
class DeletableIndex(Protocol):
    """
    삭제 가능한 인덱스 Protocol.

    chunk_id 기반 삭제를 지원하는 인덱스 어댑터용.
    """

    async def delete(
        self,
        repo_id: str,
        snapshot_id: str,
        chunk_ids: list[str],
    ) -> None:
        """
        문서 삭제.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            chunk_ids: 삭제할 chunk ID 리스트
        """
        ...


# ============================================================
# Infrastructure Store Protocols
# ============================================================


@runtime_checkable
class PostgresStoreProtocol(Protocol):
    """
    PostgreSQL 스토어 Protocol.

    PostgresFuzzyIndex가 의존하는 인터페이스.
    실제 구현: src.infra.storage.postgres.PostgresStore
    """

    async def execute(self, query: str, *args) -> list[dict]:
        """SQL 쿼리 실행"""
        ...

    async def execute_many(self, query: str, args_list: list[tuple]) -> None:
        """배치 SQL 실행"""
        ...


@runtime_checkable
class GraphStoreProtocol(Protocol):
    """
    그래프 스토어 Protocol.

    MemgraphSymbolIndex가 의존하는 인터페이스.
    실제 구현: src.contexts.code_foundation.infrastructure.graph.store.MemgraphGraphStore
    """

    async def save_graph(self, graph_doc, mode: str = "upsert") -> dict:
        """그래프 저장"""
        ...

    async def delete_snapshot(self, repo_id: str, snapshot_id: str) -> None:
        """스냅샷 삭제"""
        ...

    async def query_called_by(self, symbol_id: str) -> list[str]:
        """호출자 조회"""
        ...

    async def query_nodes_by_ids(self, node_ids: list[str]) -> list[dict]:
        """노드 조회"""
        ...

    async def query_neighbors_bulk(
        self,
        node_ids: list[str],
        rel_types: list[str] | None = None,
        direction: str = "both",
    ) -> dict[str, list[str]]:
        """이웃 노드 조회"""
        ...

    async def query_node_by_id(self, node_id: str) -> dict | None:
        """단일 노드 조회"""
        ...
