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

Performance:
    - UNWIND-based batch operations
    - Indexed node lookups
    - Vector similarity search for semantic queries
"""

import uuid
from typing import Any

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.graph.models import GraphDocument
from src.contexts.multi_index.infrastructure.common.documents import SearchHit

logger = get_logger(__name__)


class MemgraphSymbolIndex:
    """
    Symbol search implementation using Memgraph graph database.

    Provides go-to-definition, find-references, and call graph queries.
    Supports semantic symbol search via embeddings stored in Qdrant.

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
        graph_store: Any,
        embedding_provider: Any | None = None,
        qdrant_client: Any | None = None,
        symbol_embedding_collection: str = "symbol_embeddings",
        embedding_dim: int = 1024,  # bge-m3 dimension
    ):
        """
        Initialize Memgraph symbol index.

        Args:
            graph_store: MemgraphGraphStore instance
            embedding_provider: Optional embedding provider (OllamaAdapter) for semantic search
            qdrant_client: Optional AsyncQdrantClient for symbol embeddings
            symbol_embedding_collection: Qdrant collection name for symbol embeddings
            embedding_dim: Embedding dimension (1024 for bge-m3)
        """
        self.graph_store = graph_store
        self.embedding_provider = embedding_provider
        self.qdrant_client = qdrant_client
        self.symbol_embedding_collection = symbol_embedding_collection
        self.embedding_dim = embedding_dim
        self._semantic_enabled = embedding_provider is not None and qdrant_client is not None

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
                results = await self._search_callers(repo_id, snapshot_id, target_symbol, limit)
            elif intent == "callees" and target_symbol:
                results = await self._search_callees(repo_id, snapshot_id, target_symbol, limit)
            elif intent == "references" and target_symbol:
                results = await self._search_references(repo_id, snapshot_id, target_symbol, limit)
            elif intent == "imports" and target_symbol:
                results = await self._search_imports(repo_id, snapshot_id, target_symbol, limit)
            elif intent == "semantic" or self._is_semantic_query(query):
                # Semantic search using embeddings
                if self._semantic_enabled:
                    return await self._search_semantic(repo_id, snapshot_id, query, limit)
                else:
                    # Fallback to text search if semantic not enabled
                    results = self._search_symbols(repo_id, snapshot_id, query, limit)
            else:
                # Default: search by name or FQN
                results = self._search_symbols(repo_id, snapshot_id, query, limit)

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

        except Exception as e:
            logger.error(f"Symbol search failed: {e}")
            return []

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
                # Extract symbol after pattern
                idx = query_lower.find(pattern)
                target = query[idx + len(pattern) :].strip()
                # Clean up target (remove common suffixes)
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

    async def _search_callers(self, repo_id: str, snapshot_id: str, symbol_name: str, limit: int) -> list[dict]:
        """Search for functions that call the given symbol."""
        try:
            store = self.graph_store._store if hasattr(self.graph_store, "_store") else self.graph_store
            driver = store._driver

            with driver.session() as session:
                # Find callers via CALLS edge
                result = session.run(
                    """
                    MATCH (caller:GraphNode)-[:CALLS]->(callee:GraphNode)
                    WHERE callee.repo_id = $repo_id
                      AND callee.snapshot_id = $snapshot_id
                      AND (callee.name CONTAINS $symbol_name OR callee.fqn CONTAINS $symbol_name)
                    RETURN DISTINCT caller.node_id, caller.repo_id, caller.lang, caller.kind,
                           caller.fqn, caller.name, caller.path, caller.snapshot_id,
                           caller.span_start_line, caller.span_end_line
                    LIMIT $limit
                    """,
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    symbol_name=symbol_name,
                    limit=limit,
                )

                return [
                    {
                        "node_id": r["caller.node_id"],
                        "repo_id": r["caller.repo_id"],
                        "lang": r["caller.lang"],
                        "kind": r["caller.kind"],
                        "fqn": r["caller.fqn"],
                        "name": r["caller.name"],
                        "path": r["caller.path"],
                        "snapshot_id": r["caller.snapshot_id"],
                        "span_start_line": r["caller.span_start_line"],
                        "span_end_line": r["caller.span_end_line"],
                    }
                    for r in result
                ]
        except Exception as e:
            logger.error(f"_search_callers failed: {e}")
            return []

    async def _search_callees(self, repo_id: str, snapshot_id: str, symbol_name: str, limit: int) -> list[dict]:
        """Search for functions called by the given symbol."""
        try:
            store = self.graph_store._store if hasattr(self.graph_store, "_store") else self.graph_store
            driver = store._driver

            with driver.session() as session:
                result = session.run(
                    """
                    MATCH (caller:GraphNode)-[:CALLS]->(callee:GraphNode)
                    WHERE caller.repo_id = $repo_id
                      AND caller.snapshot_id = $snapshot_id
                      AND (caller.name CONTAINS $symbol_name OR caller.fqn CONTAINS $symbol_name)
                    RETURN DISTINCT callee.node_id, callee.repo_id, callee.lang, callee.kind,
                           callee.fqn, callee.name, callee.path, callee.snapshot_id,
                           callee.span_start_line, callee.span_end_line
                    LIMIT $limit
                    """,
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    symbol_name=symbol_name,
                    limit=limit,
                )

                return [
                    {
                        "node_id": r["callee.node_id"],
                        "repo_id": r["callee.repo_id"],
                        "lang": r["callee.lang"],
                        "kind": r["callee.kind"],
                        "fqn": r["callee.fqn"],
                        "name": r["callee.name"],
                        "path": r["callee.path"],
                        "snapshot_id": r["callee.snapshot_id"],
                        "span_start_line": r["callee.span_start_line"],
                        "span_end_line": r["callee.span_end_line"],
                    }
                    for r in result
                ]
        except Exception as e:
            logger.error(f"_search_callees failed: {e}")
            return []

    async def _search_references(self, repo_id: str, snapshot_id: str, symbol_name: str, limit: int) -> list[dict]:
        """Search for all references to the given symbol."""
        try:
            store = self.graph_store._store if hasattr(self.graph_store, "_store") else self.graph_store
            driver = store._driver

            with driver.session() as session:
                # Find all nodes with incoming edges to the target
                result = session.run(
                    """
                    MATCH (ref:GraphNode)-[]->(target:GraphNode)
                    WHERE target.repo_id = $repo_id
                      AND target.snapshot_id = $snapshot_id
                      AND (target.name CONTAINS $symbol_name OR target.fqn CONTAINS $symbol_name)
                    RETURN DISTINCT ref.node_id, ref.repo_id, ref.lang, ref.kind,
                           ref.fqn, ref.name, ref.path, ref.snapshot_id,
                           ref.span_start_line, ref.span_end_line
                    LIMIT $limit
                    """,
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    symbol_name=symbol_name,
                    limit=limit,
                )

                return [
                    {
                        "node_id": r["ref.node_id"],
                        "repo_id": r["ref.repo_id"],
                        "lang": r["ref.lang"],
                        "kind": r["ref.kind"],
                        "fqn": r["ref.fqn"],
                        "name": r["ref.name"],
                        "path": r["ref.path"],
                        "snapshot_id": r["ref.snapshot_id"],
                        "span_start_line": r["ref.span_start_line"],
                        "span_end_line": r["ref.span_end_line"],
                    }
                    for r in result
                ]
        except Exception as e:
            logger.error(f"_search_references failed: {e}")
            return []

    async def _search_imports(self, repo_id: str, snapshot_id: str, module_name: str, limit: int) -> list[dict]:
        """Search for files that import the given module."""
        try:
            store = self.graph_store._store if hasattr(self.graph_store, "_store") else self.graph_store
            driver = store._driver

            with driver.session() as session:
                # Find files with IMPORTS edge to the module
                result = session.run(
                    """
                    MATCH (file:GraphNode)-[:IMPORTS]->(module:GraphNode)
                    WHERE file.repo_id = $repo_id
                      AND file.snapshot_id = $snapshot_id
                      AND (module.name CONTAINS $module_name OR module.fqn CONTAINS $module_name)
                    RETURN DISTINCT file.node_id, file.repo_id, file.lang, file.kind,
                           file.fqn, file.name, file.path, file.snapshot_id,
                           file.span_start_line, file.span_end_line
                    LIMIT $limit
                    """,
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    module_name=module_name,
                    limit=limit,
                )

                return [
                    {
                        "node_id": r["file.node_id"],
                        "repo_id": r["file.repo_id"],
                        "lang": r["file.lang"],
                        "kind": r["file.kind"],
                        "fqn": r["file.fqn"],
                        "name": r["file.name"],
                        "path": r["file.path"],
                        "snapshot_id": r["file.snapshot_id"],
                        "span_start_line": r["file.span_start_line"],
                        "span_end_line": r["file.span_end_line"],
                    }
                    for r in result
                ]
        except Exception as e:
            logger.error(f"_search_imports failed: {e}")
            return []

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

    async def get_callers(self, symbol_id: str) -> list[dict[str, Any]]:
        """
        Get symbols that call this symbol.

        Args:
            symbol_id: Symbol/function identifier

        Returns:
            List of caller nodes as dicts
        """
        try:
            caller_ids = await self.graph_store.query_called_by(symbol_id)
            if not caller_ids:
                return []

            return await self.graph_store.query_nodes_by_ids(caller_ids)
        except Exception as e:
            logger.error(f"get_callers failed for {symbol_id}: {e}")
            return []

    async def get_callees(self, symbol_id: str) -> list[dict[str, Any]]:
        """
        Get symbols called by this symbol.

        Args:
            symbol_id: Symbol/function identifier

        Returns:
            List of callee nodes as dicts
        """
        try:
            # Query outgoing CALLS edges
            neighbors = await self.graph_store.query_neighbors_bulk(
                [symbol_id], rel_types=["CALLS"], direction="outgoing"
            )
            callee_ids = neighbors.get(symbol_id, [])

            if not callee_ids:
                return []

            return await self.graph_store.query_nodes_by_ids(callee_ids)
        except Exception as e:
            logger.error(f"get_callees failed for {symbol_id}: {e}")
            return []

    async def get_node_by_id(self, node_id: str) -> dict[str, Any] | None:
        """
        Get node by ID.

        Args:
            node_id: Node/symbol identifier

        Returns:
            Node data as dict or None if not found
        """
        try:
            return await self.graph_store.query_node_by_id(node_id)
        except Exception as e:
            logger.error(f"get_node_by_id failed for {node_id}: {e}")
            return None

    async def get_references(self, symbol_id: str) -> list[dict[str, Any]]:
        """
        Get all nodes that reference this symbol.

        Args:
            symbol_id: Symbol identifier

        Returns:
            List of nodes that reference this symbol
        """
        try:
            # Query incoming edges of all types
            neighbors = await self.graph_store.query_neighbors_bulk([symbol_id], direction="incoming")
            ref_ids = neighbors.get(symbol_id, [])

            if not ref_ids:
                return []

            return await self.graph_store.query_nodes_by_ids(ref_ids)
        except Exception as e:
            logger.error(f"get_references failed for {symbol_id}: {e}")
            return []

    # ============================================================
    # Additional Symbol Search Methods
    # ============================================================

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
            # Access underlying driver via graph_store._store._driver
            store = self.graph_store._store if hasattr(self.graph_store, "_store") else self.graph_store
            driver = store._driver

            with driver.session() as session:
                # Search by name or FQN (case-insensitive contains)
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

                nodes = []
                for record in result:
                    nodes.append(
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
                    )
                return nodes

        except Exception as e:
            logger.error(f"_search_symbols failed: {e}")
            return []

    async def delete_repo(self, repo_id: str, snapshot_id: str) -> None:
        """Delete repository index."""
        try:
            await self.graph_store.delete_snapshot(repo_id, snapshot_id)
            logger.info(f"Symbol index: deleted {repo_id}:{snapshot_id}")

            # Also delete symbol embeddings if semantic enabled
            if self._semantic_enabled:
                await self._delete_symbol_embeddings(repo_id, snapshot_id)
        except Exception as e:
            logger.error(f"delete_repo failed: {e}")
            raise

    # ============================================================
    # Semantic Symbol Search (Embedding-based)
    # ============================================================

    def _is_semantic_query(self, query: str) -> bool:
        """
        Detect if query is semantic (natural language) vs exact symbol search.

        Semantic queries:
        - Multi-word natural language: "function that validates input"
        - Questions: "how to parse arguments?"
        - Descriptive: "error handling in CLI"

        Non-semantic (exact):
        - Single word: "Typer"
        - CamelCase: "ArgumentParser"
        - snake_case: "get_command"
        - dot notation: "typer.main"
        """
        # Short queries with no spaces are likely exact symbol names
        if " " not in query and len(query) < 50:
            return False

        # Contains question words
        question_words = ["how", "what", "where", "which", "why", "when", "find"]
        query_lower = query.lower()
        if any(query_lower.startswith(w) for w in question_words):
            return True

        # Multiple words suggest natural language
        words = query.split()
        if len(words) >= 3:
            return True

        # Contains common semantic phrases
        semantic_phrases = [
            "function that",
            "method for",
            "class that",
            "handles",
            "validates",
            "parses",
            "converts",
            "creates",
            "returns",
            "error handling",
            "input validation",
            "data processing",
        ]
        if any(phrase in query_lower for phrase in semantic_phrases):
            return True

        return False

    async def _search_semantic(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        limit: int,
    ) -> list[SearchHit]:
        """
        Semantic symbol search using embeddings.

        1. Embed the query using bge-m3
        2. Search Qdrant for similar symbol embeddings
        3. Return SearchHit results

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            query: Natural language query
            limit: Maximum results

        Returns:
            List of SearchHit with source="symbol"
        """
        if not self._semantic_enabled:
            logger.warning("Semantic search not enabled (missing embedding_provider or qdrant_client)")
            return []

        try:
            # 1. Embed query
            query_embedding = await self.embedding_provider.embed(query)

            # 2. Build filter for repo_id and snapshot_id
            collection_name = self._get_symbol_collection_name(repo_id, snapshot_id)

            # 3. Search Qdrant
            try:
                results = await self.qdrant_client.search(
                    collection_name=collection_name,
                    query_vector=query_embedding,
                    limit=limit,
                )
            except Exception as e:
                logger.warning(f"Qdrant semantic search failed: {e}")
                return []

            # 4. Convert to SearchHits
            hits = []
            for result in results:
                payload = result.payload or {}
                kind = payload.get("kind", "")
                fqn = payload.get("fqn", "")
                name = payload.get("name", "")
                path = payload.get("path")

                hits.append(
                    SearchHit(
                        chunk_id=payload.get("node_id", ""),
                        score=result.score,
                        source="symbol",
                        file_path=path,
                        symbol_id=payload.get("node_id", ""),
                        metadata={
                            "name": name,
                            "fqn": fqn,
                            "kind": kind,
                            "preview": f"{kind}: {fqn}",  # Use preview for display
                            "symbol_fqn": fqn,
                            "start_line": payload.get("span_start_line"),
                            "end_line": payload.get("span_end_line"),
                            "intent": "semantic",
                            "semantic_score": result.score,
                        },
                    )
                )

            logger.info(f"Semantic symbol search: query='{query[:50]}...', results={len(hits)}")
            return hits

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    async def index_symbol_embeddings(
        self,
        repo_id: str,
        snapshot_id: str,
        graph_doc: GraphDocument,
        batch_size: int = 100,
    ) -> int:
        """
        Index symbol embeddings to Qdrant for semantic search.

        Extracts symbols from GraphDocument, embeds their name+FQN+kind,
        and stores in Qdrant.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier
            graph_doc: GraphDocument with symbols
            batch_size: Batch size for embedding generation

        Returns:
            Number of symbols indexed
        """
        if not self._semantic_enabled:
            logger.info("Semantic search not enabled, skipping symbol embedding indexing")
            return 0

        try:
            from qdrant_client.models import PointStruct

            # 1. Extract symbols from graph document
            # GraphDocument uses graph_nodes (dict) instead of nodes
            symbols = []
            nodes = graph_doc.graph_nodes.values() if hasattr(graph_doc, "graph_nodes") else []
            for node in nodes:
                # Only index meaningful symbols (functions, classes, methods)
                kind = node.kind.value if hasattr(node.kind, "value") else str(node.kind)
                # GraphNodeKind values are capitalized: Function, Class, Method, etc.
                kind_lower = kind.lower()
                if kind_lower in ("function", "class", "method", "module", "variable", "field"):
                    # Extract file_path from multiple sources:
                    # 1. node.path (set for FILE nodes)
                    # 2. node.attrs.module_path (stored by GraphBuilder)
                    # 3. Extract from FQN (e.g., "func:repo::src/file.py::ClassName.method")
                    file_path = self._extract_file_path(node)

                    # Create embedding text: name + fqn + kind
                    embed_text = f"{node.name} {node.fqn} {kind}"
                    symbols.append(
                        {
                            "node_id": node.id,
                            "name": node.name,
                            "fqn": node.fqn,
                            "kind": kind,
                            "path": file_path,
                            "span_start_line": node.span.start_line if node.span else None,
                            "span_end_line": node.span.end_line if node.span else None,
                            "embed_text": embed_text,
                            "repo_id": repo_id,
                            "snapshot_id": snapshot_id,
                        }
                    )

            if not symbols:
                logger.info(f"No symbols to embed for {repo_id}:{snapshot_id}")
                return 0

            # 2. Create collection if needed
            collection_name = self._get_symbol_collection_name(repo_id, snapshot_id)
            await self._ensure_symbol_collection(collection_name)

            # 3. Generate embeddings in batches
            logger.info(f"Generating embeddings for {len(symbols)} symbols...")
            all_embeddings = []

            for i in range(0, len(symbols), batch_size):
                batch = symbols[i : i + batch_size]
                texts = [s["embed_text"] for s in batch]
                embeddings = await self.embedding_provider.embed_batch(texts)
                all_embeddings.extend(embeddings)

                if (i + batch_size) % 100 == 0:
                    logger.debug(f"Embedded {min(i + batch_size, len(symbols))}/{len(symbols)} symbols")

            # 4. Create Qdrant points
            points = []
            for sym, embedding in zip(symbols, all_embeddings, strict=False):
                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, sym["node_id"]))
                points.append(
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload={
                            "node_id": sym["node_id"],
                            "name": sym["name"],
                            "fqn": sym["fqn"],
                            "kind": sym["kind"],
                            "path": sym["path"],
                            "span_start_line": sym["span_start_line"],
                            "span_end_line": sym["span_end_line"],
                            "repo_id": sym["repo_id"],
                            "snapshot_id": sym["snapshot_id"],
                        },
                    )
                )

            # 5. Upsert to Qdrant in batches
            upsert_batch_size = 100
            for i in range(0, len(points), upsert_batch_size):
                batch = points[i : i + upsert_batch_size]
                await self.qdrant_client.upsert(
                    collection_name=collection_name,
                    points=batch,
                )

            logger.info(f"Symbol embeddings indexed: {len(points)} symbols for {repo_id}:{snapshot_id}")
            return len(points)

        except Exception as e:
            logger.error(f"Symbol embedding indexing failed: {e}")
            return 0

    def _get_symbol_collection_name(self, repo_id: str, snapshot_id: str) -> str:
        """Get Qdrant collection name for symbol embeddings."""
        snapshot_short = snapshot_id[:8] if len(snapshot_id) > 8 else snapshot_id
        return f"{self.symbol_embedding_collection}_{repo_id}_{snapshot_short}"

    async def _ensure_symbol_collection(self, collection_name: str) -> None:
        """Create symbol embedding collection if not exists."""
        try:
            from qdrant_client.models import Distance, VectorParams

            collections = await self.qdrant_client.get_collections()
            exists = any(c.name == collection_name for c in collections.collections)

            if not exists:
                logger.info(f"Creating symbol embedding collection: {collection_name}")
                await self.qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dim,
                        distance=Distance.COSINE,
                    ),
                )
        except Exception as e:
            logger.error(f"Failed to ensure symbol collection: {e}")
            raise

    async def _delete_symbol_embeddings(self, repo_id: str, snapshot_id: str) -> None:
        """Delete symbol embeddings from Qdrant."""
        try:
            collection_name = self._get_symbol_collection_name(repo_id, snapshot_id)
            await self.qdrant_client.delete_collection(collection_name=collection_name)
            logger.info(f"Deleted symbol embedding collection: {collection_name}")
        except Exception as e:
            logger.warning(f"Failed to delete symbol embeddings: {e}")

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
            # attrs might be JSON string from Memgraph
            try:
                import json

                attrs = json.loads(attrs)
            except (json.JSONDecodeError, TypeError):
                attrs = {}

        module_path = attrs.get("module_path")
        if module_path:
            # module_path might be "src.folder.file" format, convert to path
            if "/" not in module_path and "." in module_path:
                return module_path.replace(".", "/") + ".py"
            return module_path

        # 3. Extract from FQN or ID
        # ID format variations:
        #   "function:repo:path/to/file.py:function_name"
        #   "method:repo::path/to/file.py::ClassName.method_name"
        #   "variable:typer:tests/test_tutorial/test.py:test_func.var"
        for source in [node.id, node.fqn]:
            if not source:
                continue

            # Split by : (single colon) and look for file path pattern
            parts = source.split(":")
            for part in parts:
                # Skip empty parts, repo_id, type prefixes
                if not part or part in ("function", "method", "class", "variable", "module", "file", "field"):
                    continue

                # Check if this part looks like a file path
                if "/" in part:
                    # Extract file path (may have suffix like "::ClassName")
                    # Pattern: path/to/file.py or path/to/file.py::ClassName
                    path_part = part.split("::")[0] if "::" in part else part

                    # Check for common file extensions
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
                            # Extract up to and including the extension
                            idx = path_part.find(ext) + len(ext)
                            return path_part[:idx]

        return None
