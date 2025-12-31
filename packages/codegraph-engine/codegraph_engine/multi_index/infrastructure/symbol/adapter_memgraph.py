"""
Memgraph Symbol Index Adapter

Implements SymbolIndexPort for graph-based symbol search using Memgraph.

Architecture:
    GraphDocument → Memgraph → Symbol Search → SearchHit
    Symbol Embedding → Qdrant → Semantic Symbol Search

Features:
    - Symbol search (by name, FQN)
    - Go-to-definition
    - Find references
    - Call graph queries (callers/callees)
    - Graph traversal
    - Semantic symbol search via embeddings

Design:
    Composition 패턴으로 책임 분리 (SRP):
    - CallGraphQueryBuilder: 그래프 쿼리 담당
    - SymbolEmbeddingManager: 시맨틱 임베딩 담당
    - MemgraphSymbolIndex: 통합 조정 및 라우팅
"""

from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.graph.models import GraphDocument
from codegraph_engine.multi_index.domain import GraphStoreProtocol
from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit

from .call_graph_query import CallGraphQueryBuilder
from .symbol_embedding import SymbolEmbeddingManager

logger = get_logger(__name__)


class MemgraphSymbolIndex:
    """
    Symbol search implementation using Memgraph graph database.

    Provides go-to-definition, find-references, and call graph queries.
    Supports semantic symbol search via embeddings stored in Qdrant.

    Composition:
        - _call_graph: CallGraphQueryBuilder (callers/callees/references)
        - _embedding: SymbolEmbeddingManager (semantic search)

    Usage:
        symbol_index = MemgraphSymbolIndex(
            graph_store=memgraph_store,
            embedding_provider=local_llm_adapter,  # Optional: for semantic search
            qdrant_client=qdrant_client,  # Optional: for semantic search
        )
        await symbol_index.index_graph(repo_id, snapshot_id, graph_doc)
        hits = await symbol_index.search(repo_id, snapshot_id, "MyClass", limit=10)
    """

    def __init__(
        self,
        graph_store: GraphStoreProtocol,
        embedding_provider: Any | None = None,
        qdrant_client: Any | None = None,
        symbol_embedding_collection: str = "symbol_embeddings",
        embedding_dim: int = 1024,  # bge-m3 dimension
    ):
        """
        Initialize Memgraph symbol index.

        Args:
            graph_store: MemgraphGraphStore instance (GraphStoreProtocol)
            embedding_provider: Optional embedding provider (OllamaAdapter) for semantic search
            qdrant_client: Optional AsyncQdrantClient for symbol embeddings
            symbol_embedding_collection: Qdrant collection name for symbol embeddings
            embedding_dim: Embedding dimension (1024 for bge-m3)
        """
        self.graph_store = graph_store

        # Composition: 책임 분리된 컴포넌트들
        self._call_graph = CallGraphQueryBuilder(graph_store)
        self._embedding = SymbolEmbeddingManager(
            embedding_provider=embedding_provider,
            qdrant_client=qdrant_client,
            collection_prefix=symbol_embedding_collection,
            embedding_dim=embedding_dim,
        )

    # ============================================================
    # SymbolIndexPort Implementation
    # ============================================================

    async def search(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        limit: int = 50,
    ) -> list[SearchHit]:
        """
        Symbol search with intent-based graph query routing.

        Supports:
        - Symbol name search: "Typer", "get_command"
        - Callers query: "callers of X", "functions that call X"
        - Callees query: "callees of X", "functions called by X"
        - References query: "references to X", "usages of X"
        - Imports query: "imports X", "files importing X"

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Symbol name or intent-based query
            limit: Maximum results

        Returns:
            List of SearchHit with source="symbol"
        """
        try:
            # 1. Analyze query intent and extract target symbol
            intent, target_symbol = self._analyze_query_intent(query)

            # 2. Execute appropriate graph query based on intent
            if intent == "callers" and target_symbol:
                results = await self._call_graph.search_callers(repo_id, snapshot_id, target_symbol, limit)
            elif intent == "callees" and target_symbol:
                results = await self._call_graph.search_callees(repo_id, snapshot_id, target_symbol, limit)
            elif intent == "references" and target_symbol:
                results = await self._call_graph.search_references(repo_id, snapshot_id, target_symbol, limit)
            elif intent == "imports" and target_symbol:
                results = await self._call_graph.search_imports(repo_id, snapshot_id, target_symbol, limit)
            elif intent == "semantic" or self._embedding.is_semantic_query(query):
                # Semantic search using embeddings
                if self._embedding.is_enabled:
                    return await self._embedding.search_semantic(repo_id, snapshot_id, query, limit)
                else:
                    # Fallback to text search if semantic not enabled
                    results = self._search_symbols(repo_id, snapshot_id, query, limit)
            else:
                # Default: search by name or FQN
                results = self._search_symbols(repo_id, snapshot_id, query, limit)

            return self._results_to_hits(results, intent)

        except Exception as e:
            logger.error(f"Symbol search failed: {e}")
            return []

    def _results_to_hits(self, results: list[dict], intent: str) -> list[SearchHit]:
        """쿼리 결과를 SearchHit 리스트로 변환."""
        hits = []
        for i, node in enumerate(results):
            score = 1.0 - (i * 0.01)  # Simple ranking by order
            hits.append(
                SearchHit(
                    chunk_id=node.get("node_id", ""),
                    score=score,
                    source="symbol",
                    content=f"{node.get('kind', '')}: {node.get('fqn', '')}",
                    file_path=node.get("path", ""),
                    metadata={
                        "name": node.get("name", ""),
                        "fqn": node.get("fqn", ""),
                        "kind": node.get("kind", ""),
                        "start_line": node.get("span_start_line"),
                        "end_line": node.get("span_end_line"),
                        "intent": intent,
                    },
                )
            )
        return hits

    def _analyze_query_intent(self, query: str) -> tuple[str, str | None]:
        """
        Analyze query to determine intent and extract target symbol.

        Returns:
            (intent, target_symbol) tuple
            intent: "callers", "callees", "references", "imports", "symbol"
            target_symbol: extracted symbol name or None
        """
        query_lower = query.lower()

        # Callers patterns
        callers_patterns = [
            "callers of ",
            "functions that call ",
            "methods that call ",
            "who calls ",
            "what calls ",
            "called by",
        ]
        for pattern in callers_patterns:
            if pattern in query_lower:
                idx = query_lower.find(pattern)
                target = query[idx + len(pattern) :].strip()
                target = target.split()[0] if target else None
                if target:
                    return ("callers", target)

        # Callees patterns
        callees_patterns = [
            "callees of ",
            "functions called by ",
            "methods called by ",
            "what does .* call",
            "calls from ",
        ]
        for pattern in callees_patterns:
            if pattern in query_lower:
                idx = query_lower.find(pattern)
                target = query[idx + len(pattern) :].strip()
                target = target.split()[0] if target else None
                if target:
                    return ("callees", target)

        # References patterns
        references_patterns = [
            "references to ",
            "usages of ",
            "uses of ",
            "where is .* used",
            "find references ",
        ]
        for pattern in references_patterns:
            if pattern in query_lower:
                idx = query_lower.find(pattern)
                target = query[idx + len(pattern) :].strip()
                target = target.split()[0] if target else None
                if target:
                    return ("references", target)

        # Imports patterns
        imports_patterns = [
            "files importing ",
            "imports ",
            "modules that import ",
            "who imports ",
            "what imports ",
        ]
        for pattern in imports_patterns:
            if pattern in query_lower:
                idx = query_lower.find(pattern)
                target = query[idx + len(pattern) :].strip()
                target = target.split()[0] if target else None
                if target:
                    return ("imports", target)

        # Default: symbol search
        return ("symbol", None)

    def _search_symbols(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        limit: int,
    ) -> list[dict]:
        """
        Search symbols by name or FQN using Memgraph.

        Uses CONTAINS for partial matching.
        """
        try:
            store = self.graph_store._store if hasattr(self.graph_store, "_store") else self.graph_store
            driver = store._driver

            with driver.session() as session:
                result = session.run(
                    """
                    MATCH (n:GraphNode {repo_id: $repo_id, snapshot_id: $snapshot_id})
                    WHERE n.name CONTAINS $search_term OR n.fqn CONTAINS $search_term
                    RETURN n.node_id, n.repo_id, n.lang, n.kind, n.fqn, n.name,
                           n.path, n.snapshot_id, n.span_start_line, n.span_end_line
                    LIMIT $limit
                    """,
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    search_term=query,
                    limit=limit,
                )

                return [
                    {
                        "node_id": record["n.node_id"],
                        "repo_id": record["n.repo_id"],
                        "lang": record["n.lang"],
                        "kind": record["n.kind"],
                        "fqn": record["n.fqn"],
                        "name": record["n.name"],
                        "path": record["n.path"],
                        "snapshot_id": record["n.snapshot_id"],
                        "span_start_line": record["n.span_start_line"],
                        "span_end_line": record["n.span_end_line"],
                    }
                    for record in result
                ]

        except Exception as e:
            logger.error(f"_search_symbols failed: {e}")
            return []

    # ============================================================
    # Graph Operations
    # ============================================================

    async def index_graph(
        self,
        repo_id: str,
        snapshot_id: str,
        graph_doc: GraphDocument,
    ) -> None:
        """
        Index graph document to Memgraph.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            graph_doc: GraphDocument instance
        """
        try:
            stats = await self.graph_store.save_graph(graph_doc, mode="upsert")
            logger.info(
                f"Symbol index: saved {stats['nodes_success']} nodes, "
                f"{stats['edges_success']} edges for {repo_id}:{snapshot_id}"
            )
        except Exception as e:
            logger.error(f"Symbol index_graph failed: {e}")
            raise

    async def delete_repo(self, repo_id: str, snapshot_id: str) -> None:
        """Delete repository index."""
        try:
            await self.graph_store.delete_snapshot(repo_id, snapshot_id)
            logger.info(f"Symbol index: deleted {repo_id}:{snapshot_id}")

            # Also delete symbol embeddings if semantic enabled
            if self._embedding.is_enabled:
                await self._embedding.delete_embeddings(repo_id, snapshot_id)
        except Exception as e:
            logger.error(f"delete_repo failed: {e}")
            raise

    # ============================================================
    # Call Graph Delegation (to CallGraphQueryBuilder)
    # ============================================================

    async def get_callers(self, symbol_id: str) -> list[dict[str, Any]]:
        """Get symbols that call this symbol."""
        return await self._call_graph.get_callers(symbol_id)

    async def get_callees(self, symbol_id: str) -> list[dict[str, Any]]:
        """Get symbols called by this symbol."""
        return await self._call_graph.get_callees(symbol_id)

    async def get_node_by_id(self, node_id: str) -> dict[str, Any] | None:
        """Get node by ID."""
        return await self._call_graph.get_node_by_id(node_id)

    async def get_references(self, symbol_id: str) -> list[dict[str, Any]]:
        """Get all nodes that reference this symbol."""
        return await self._call_graph.get_references(symbol_id)

    # ============================================================
    # Semantic Embedding Delegation (to SymbolEmbeddingManager)
    # ============================================================

    async def index_symbol_embeddings(
        self,
        repo_id: str,
        snapshot_id: str,
        graph_doc: GraphDocument,
        batch_size: int = 100,
    ) -> int:
        """
        Index symbol embeddings to Qdrant for semantic search.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            graph_doc: GraphDocument with symbols
            batch_size: Batch size for embedding generation

        Returns:
            Number of symbols indexed
        """
        return await self._embedding.index_embeddings(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            graph_doc=graph_doc,
            extract_file_path_fn=self._extract_file_path,
            batch_size=batch_size,
        )

    def _extract_file_path(self, node) -> str | None:
        """
        Extract file path from GraphNode using multiple sources.

        Priority:
        1. node.path (directly set, usually for FILE nodes)
        2. node.attrs["module_path"] (set by GraphBuilder for functions/methods)
        3. Extract from node.fqn (e.g., "func:repo::src/file.py::ClassName.method")
        4. Extract from node.id (e.g., "method:repo::src/file.py::Class.method")

        Args:
            node: GraphNode instance

        Returns:
            File path string or None if not extractable
        """
        # 1. Direct path (usually for FILE nodes)
        if node.path:
            return node.path

        # 2. From attrs (GraphBuilder stores module_path)
        attrs = node.attrs if hasattr(node, "attrs") and node.attrs else {}
        if isinstance(attrs, str):
            try:
                import json

                attrs = json.loads(attrs)
            except (json.JSONDecodeError, TypeError):
                attrs = {}

        module_path = attrs.get("module_path")
        if module_path:
            if "/" not in module_path and "." in module_path:
                return module_path.replace(".", "/") + ".py"
            return module_path

        # 3. Extract from FQN or ID
        for source in [node.id, node.fqn]:
            if not source:
                continue

            parts = source.split(":")
            for part in parts:
                if not part or part in (
                    "function",
                    "method",
                    "class",
                    "variable",
                    "module",
                    "file",
                    "field",
                ):
                    continue

                if "/" in part:
                    path_part = part.split("::")[0] if "::" in part else part

                    extensions = (
                        ".py",
                        ".ts",
                        ".tsx",
                        ".js",
                        ".jsx",
                        ".go",
                        ".java",
                        ".rs",
                        ".rb",
                        ".php",
                        ".c",
                        ".cpp",
                        ".h",
                    )
                    for ext in extensions:
                        if ext in path_part:
                            idx = path_part.find(ext) + len(ext)
                            return path_part[:idx]

        return None
