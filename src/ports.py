"""
Semantica Code Engine Ports

Defines interfaces for both server layer and foundation layer components.
"""

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from src.index.common.documents import IndexDocument, SearchHit

# ============================================================
# Foundation Layer Ports (Index Layer)
# ============================================================


@runtime_checkable
class LexicalIndexPort(Protocol):
    """
    Lexical Search Port (Zoekt-based).

    Provides file-based text/identifier/regex search.
    """

    @abstractmethod
    async def reindex_repo(self, repo_id: str, snapshot_id: str) -> None:
        """
        Full repository reindex.

        Args:
            repo_id: Repository identifier
            snapshot_id: Git commit hash or snapshot identifier
        """
        ...

    @abstractmethod
    async def reindex_paths(self, repo_id: str, snapshot_id: str, paths: list[str]) -> None:
        """
        Partial reindex for specific files/paths.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            paths: List of file paths to reindex
        """
        ...

    @abstractmethod
    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> "list[SearchHit]":
        """
        Search with lexical query.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Search query (text/regex/identifier)
            limit: Maximum results

        Returns:
            List of SearchHit with source="lexical"
        """
        ...

    @abstractmethod
    async def delete_repo(self, repo_id: str, snapshot_id: str) -> None:
        """Delete repository index"""
        ...


@runtime_checkable
class VectorIndexPort(Protocol):
    """
    Vector Search Port (Qdrant-based).

    Provides semantic/embedding-based search.
    """

    @abstractmethod
    async def index(self, repo_id: str, snapshot_id: str, docs: "list[IndexDocument]") -> None:
        """
        Full index creation.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            docs: List of IndexDocument instances
        """
        ...

    @abstractmethod
    async def upsert(self, repo_id: str, snapshot_id: str, docs: "list[IndexDocument]") -> None:
        """
        Incremental upsert.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            docs: List of IndexDocument instances to upsert
        """
        ...

    @abstractmethod
    async def delete(self, repo_id: str, snapshot_id: str, doc_ids: list[str]) -> None:
        """
        Delete documents by ID.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            doc_ids: List of chunk_ids to delete
        """
        ...

    @abstractmethod
    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> "list[SearchHit]":
        """
        Semantic search.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Natural language query
            limit: Maximum results

        Returns:
            List of SearchHit with source="vector"
        """
        ...


@runtime_checkable
class SymbolIndexPort(Protocol):
    """
    Symbol Search Port (Kuzu Graph-based).

    Provides go-to-definition, find-references, call graph queries.
    """

    @abstractmethod
    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> "list[SearchHit]":
        """
        Symbol search (go-to-def, find-refs).

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Symbol name or pattern
            limit: Maximum results

        Returns:
            List of SearchHit with source="symbol"
        """
        ...

    @abstractmethod
    async def index_graph(self, repo_id: str, snapshot_id: str, graph_doc: Any) -> None:
        """
        Index graph document.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            graph_doc: GraphDocument instance
        """
        ...

    @abstractmethod
    async def get_callers(self, symbol_id: str) -> list[dict[str, Any]]:
        """Get symbols that call this symbol (returns dict for flexibility)"""
        ...

    @abstractmethod
    async def get_callees(self, symbol_id: str) -> list[dict[str, Any]]:
        """Get symbols called by this symbol (returns dict for flexibility)"""
        ...


@runtime_checkable
class FuzzyIndexPort(Protocol):
    """
    Fuzzy Search Port (PostgreSQL pg_trgm-based).

    Handles typos and incomplete queries.
    """

    @abstractmethod
    async def index(self, repo_id: str, snapshot_id: str, docs: "list[IndexDocument]") -> None:
        """Index documents for fuzzy search."""
        ...

    @abstractmethod
    async def upsert(self, repo_id: str, snapshot_id: str, docs: "list[IndexDocument]") -> None:
        """Upsert documents for fuzzy search."""
        ...

    @abstractmethod
    async def delete(self, repo_id: str, snapshot_id: str, doc_ids: list[str]) -> None:
        """Delete documents by ID."""
        ...

    @abstractmethod
    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> "list[SearchHit]":
        """
        Fuzzy search for identifiers/symbols.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Partial or misspelled identifier
            limit: Maximum results

        Returns:
            List of SearchHit with source="fuzzy"
        """
        ...


@runtime_checkable
class DomainMetaIndexPort(Protocol):
    """
    Domain Metadata Search Port (README/ADR/Docs).

    Searches documentation and architectural decision records.
    """

    @abstractmethod
    async def index(self, repo_id: str, snapshot_id: str, docs: "list[IndexDocument]") -> None:
        """Index domain documents (README, ADR, API specs)"""
        ...

    @abstractmethod
    async def upsert(self, repo_id: str, snapshot_id: str, docs: "list[IndexDocument]") -> None:
        """Upsert domain documents."""
        ...

    @abstractmethod
    async def delete(self, repo_id: str, snapshot_id: str, doc_ids: list[str]) -> None:
        """Delete documents by ID."""
        ...

    @abstractmethod
    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> "list[SearchHit]":
        """
        Search domain documents.

        Returns:
            List of SearchHit with source="domain"
        """
        ...


@runtime_checkable
class RuntimeIndexPort(Protocol):
    """
    Runtime Trace Index Port (Phase 3).

    Provides hot path and error-based search.
    """

    @abstractmethod
    def index_traces(self, repo_id: str, snapshot_id: str, traces: list[dict[str, Any]]) -> None:
        """Index runtime traces from OpenTelemetry"""
        ...

    @abstractmethod
    async def search(self, repo_id: str, snapshot_id: str, query: str, limit: int = 50) -> "list[SearchHit]":
        """
        Search based on runtime metrics.

        Returns:
            List of SearchHit with source="runtime"
        """
        ...


@runtime_checkable
class RepoMapPort(Protocol):
    """
    RepoMap Query Port.

    Provides read-only access to RepoMap snapshots for Retriever/Index layers.

    Usage:
        repomap_port = PostgresRepoMapStore(...)
        nodes = repomap_port.get_topk_by_importance(repo_id, snapshot_id, k=100)
        subtree = repomap_port.get_subtree(repo_id, snapshot_id, node_id)
    """

    @abstractmethod
    def get_snapshot(self, repo_id: str, snapshot_id: str) -> Any | None:  # RepoMapSnapshot
        """
        Get complete RepoMap snapshot.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot/commit identifier

        Returns:
            RepoMapSnapshot or None if not found
        """
        ...

    @abstractmethod
    def get_node(self, node_id: str) -> Any | None:  # RepoMapNode
        """
        Get single RepoMap node by ID.

        Args:
            node_id: RepoMap node ID

        Returns:
            RepoMapNode or None if not found
        """
        ...

    @abstractmethod
    def get_topk_by_importance(self, repo_id: str, snapshot_id: str, k: int = 100) -> list[Any]:  # list[RepoMapNode]
        """
        Get top K nodes sorted by importance score.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            k: Number of top nodes to return

        Returns:
            List of RepoMapNode sorted by importance (descending)
        """
        ...

    @abstractmethod
    def get_subtree(self, repo_id: str, snapshot_id: str, root_node_id: str) -> list[Any]:  # list[RepoMapNode]
        """
        Get node and all descendants.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            root_node_id: Root node ID for subtree

        Returns:
            List of RepoMapNode (root + all children recursively)
        """
        ...

    @abstractmethod
    def get_nodes_by_path(self, repo_id: str, snapshot_id: str, path: str) -> list[Any]:  # list[RepoMapNode]
        """
        Get all nodes matching a file/directory path.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            path: File or directory path

        Returns:
            List of RepoMapNode matching the path
        """
        ...

    @abstractmethod
    def get_nodes_by_fqn(self, repo_id: str, snapshot_id: str, fqn: str) -> list[Any]:  # list[RepoMapNode]
        """
        Get all nodes matching a fully qualified name.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            fqn: Fully qualified name

        Returns:
            List of RepoMapNode matching the FQN
        """
        ...


# ============================================================
# Server Layer Ports (API/MCP Server)
# ============================================================


class IndexingPort(Protocol):
    """인덱싱 포트"""

    @abstractmethod
    def index_repository(self, repo_path: str, **options) -> dict[str, Any]:
        """저장소 인덱싱"""
        ...

    @abstractmethod
    def get_indexing_status(self, repo_id: str) -> dict[str, Any]:
        """인덱싱 상태 조회"""
        ...


class SearchPort(Protocol):
    """검색 포트"""

    @abstractmethod
    async def search(self, query: str, **options) -> list[dict[str, Any]]:
        """코드 검색"""
        ...

    @abstractmethod
    def search_symbols(self, symbol_name: str, **options) -> list[dict[str, Any]]:
        """심볼 검색"""
        ...

    @abstractmethod
    def search_chunks(self, query: str, **options) -> list[dict[str, Any]]:
        """청크 검색"""
        ...


class GraphPort(Protocol):
    """그래프 포트"""

    @abstractmethod
    def get_callers(self, symbol_id: str) -> list[dict[str, Any]]:
        """호출자 조회"""
        ...

    @abstractmethod
    def get_callees(self, symbol_id: str) -> list[dict[str, Any]]:
        """피호출자 조회"""
        ...

    @abstractmethod
    def get_dependencies(self, node_id: str) -> list[dict[str, Any]]:
        """의존성 조회"""
        ...


class ContextPort(Protocol):
    """컨텍스트 포트"""

    @abstractmethod
    def build_context(self, query: str, **options) -> str:
        """컨텍스트 생성"""
        ...

    @abstractmethod
    def get_repomap(self, repo_id: str, **options) -> str:
        """레포맵 조회"""
        ...


class LLMPort(Protocol):
    """LLM 포트"""

    @abstractmethod
    async def generate(self, prompt: str, max_tokens: int = 500, temperature: float = 0.3) -> str:
        """텍스트 생성"""
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """임베딩 생성"""
        ...


class EnginePort(IndexingPort, SearchPort, GraphPort, ContextPort, Protocol):
    """
    통합 엔진 포트

    server 계층이 사용할 전체 인터페이스
    """

    pass
