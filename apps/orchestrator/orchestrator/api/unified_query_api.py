"""
Unified Query API - 청크 + 정적분석 통합 쿼리

청크와 정적분석을 하나의 쿼리 인터페이스로 제공

Features:
1. Chunk Queries (SQL-like)
2. Static Analysis (Query DSL)
3. Combined Queries (Chunk + Analysis)

Usage:
    api = UnifiedQueryAPI(container)

    # Chunk query
    chunks = await api.find_chunks(
        kind="function",
        fqn_pattern="auth.*",
        file_path="backend/auth/*"
    )

    # Static analysis
    paths = api.find_taint_flows(
        source="request.GET",
        sink="execute"
    )

    # Combined
    vulnerable_chunks = await api.find_vulnerable_chunks(
        analysis="taint",
        severity="high"
    )
"""

from typing import Any

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class UnifiedQueryAPI:
    """
    Unified Query API

    통합 쿼리 인터페이스:
    - Chunk queries (PostgreSQL)
    - Static analysis (QueryEngine + DSL)
    - Hybrid queries (Combined)
    """

    def __init__(
        self,
        chunk_store: Any,
        query_engine: Any | None = None,
        retrieval_service: Any | None = None,
    ):
        """
        Args:
            chunk_store: Chunk storage (PostgresChunkStore)
            query_engine: Query engine for static analysis (optional)
            retrieval_service: Retrieval service for search (optional)
        """
        self.chunk_store = chunk_store
        self.query_engine = query_engine
        self.retrieval_service = retrieval_service

        logger.info("unified_query_api_initialized")

    # ============================================================
    # Chunk Queries (SQL-like)
    # ============================================================

    async def find_chunks(
        self,
        repo_id: str,
        snapshot_id: str | None = None,
        kind: str | None = None,
        fqn_pattern: str | None = None,
        file_path: str | None = None,
        language: str | None = None,
        visibility: str | None = None,
        limit: int = 100,
    ) -> list[Any]:
        """
        청크 검색 (SQL-like)

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            kind: Chunk kind (function, class, file, etc.)
            fqn_pattern: FQN pattern (SQL LIKE: "auth.%")
            file_path: File path pattern
            language: Programming language
            visibility: Symbol visibility (public, private)
            limit: Max results

        Returns:
            List of chunks

        Examples:
            # Find all auth functions
            await api.find_chunks(
                repo_id="myrepo",
                kind="function",
                fqn_pattern="auth.%"
            )

            # Find public classes in backend
            await api.find_chunks(
                repo_id="myrepo",
                kind="class",
                file_path="backend/%",
                visibility="public"
            )
        """
        logger.info(
            "chunk_query_start",
            repo_id=repo_id,
            kind=kind,
            fqn_pattern=fqn_pattern,
        )

        # Build SQL query dynamically
        pool = await self.chunk_store._get_pool()

        conditions = ["repo_id = $1", "is_deleted = FALSE"]
        params = [repo_id]
        param_idx = 2

        if snapshot_id:
            conditions.append(f"snapshot_id = ${param_idx}")
            params.append(snapshot_id)
            param_idx += 1

        if kind:
            conditions.append(f"kind = ${param_idx}")
            params.append(kind)
            param_idx += 1

        if fqn_pattern:
            conditions.append(f"fqn LIKE ${param_idx}")
            params.append(fqn_pattern)
            param_idx += 1

        if file_path:
            conditions.append(f"file_path LIKE ${param_idx}")
            params.append(file_path)
            param_idx += 1

        if language:
            conditions.append(f"language = ${param_idx}")
            params.append(language)
            param_idx += 1

        if visibility:
            conditions.append(f"symbol_visibility = ${param_idx}")
            params.append(visibility)
            param_idx += 1

        query = f"""
            SELECT * FROM chunks
            WHERE {" AND ".join(conditions)}
            ORDER BY fqn
            LIMIT ${param_idx}
        """
        params.append(limit)

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            chunks = [self.chunk_store._chunk_from_row(row) for row in rows]

        logger.info("chunk_query_complete", count=len(chunks))
        return chunks

    async def find_chunks_in_lines(
        self,
        repo_id: str,
        file_path: str,
        start_line: int,
        end_line: int,
    ) -> list[Any]:
        """
        특정 라인 범위의 청크 찾기

        Args:
            repo_id: Repository ID
            file_path: File path
            start_line: Start line
            end_line: End line

        Returns:
            List of chunks in line range
        """
        pool = await self.chunk_store._get_pool()

        query = """
            SELECT * FROM chunks
            WHERE repo_id = $1
              AND file_path = $2
              AND start_line <= $4
              AND end_line >= $3
              AND is_deleted = FALSE
            ORDER BY start_line
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, repo_id, file_path, start_line, end_line)
            chunks = [self.chunk_store._chunk_from_row(row) for row in rows]

        logger.info("line_range_query_complete", count=len(chunks))
        return chunks

    # ============================================================
    # Static Analysis Queries (Query DSL)
    # ============================================================

    def find_taint_flows(
        self,
        source_pattern: str,
        sink_pattern: str,
        max_depth: int = 10,
    ) -> Any:
        """
        Taint flow 찾기 (Query DSL)

        Args:
            source_pattern: Source pattern (e.g., "request.GET")
            sink_pattern: Sink pattern (e.g., "execute")
            max_depth: Max traversal depth

        Returns:
            PathSet with taint flows

        Example:
            paths = api.find_taint_flows(
                source_pattern="request",
                sink_pattern="sql"
            )

            for path in paths:
                print(f"Vulnerable: {path}")
        """
        if not self.query_engine:
            raise RuntimeError("QueryEngine not available")

        from codegraph_engine.code_foundation.domain.query.factories import E, Q

        # Build query
        source = Q.Source(source_pattern)
        sink = Q.Sink(sink_pattern)
        query = (source >> sink).via(E.DFG).depth(max_depth)

        # Execute
        paths = self.query_engine.execute_any_path(query)

        logger.info(
            "taint_query_complete",
            source=source_pattern,
            sink=sink_pattern,
            paths=len(paths.paths),
        )

        return paths

    def find_call_chains(
        self,
        from_func: str,
        to_func: str,
        max_depth: int = 5,
    ) -> Any:
        """
        호출 체인 찾기

        Args:
            from_func: Source function
            to_func: Target function
            max_depth: Max call depth

        Returns:
            PathSet with call chains
        """
        if not self.query_engine:
            raise RuntimeError("QueryEngine not available")

        from codegraph_engine.code_foundation.domain.query.factories import E, Q

        query = (Q.Func(from_func) >> Q.Func(to_func)).via(E.CALL).depth(max_depth)

        paths = self.query_engine.execute_any_path(query)

        logger.info(
            "call_chain_query_complete",
            from_func=from_func,
            to_func=to_func,
            chains=len(paths.paths),
        )

        return paths

    def find_data_dependencies(
        self,
        from_var: str,
        to_var: str,
        max_hops: int = 5,
    ) -> Any:
        """
        데이터 의존성 찾기

        Args:
            from_var: Source variable
            to_var: Target variable
            max_hops: Max data flow hops

        Returns:
            PathSet with data dependencies
        """
        if not self.query_engine:
            raise RuntimeError("QueryEngine not available")

        from codegraph_engine.code_foundation.domain.query.factories import E, Q

        query = (Q.Var(from_var) >> Q.Var(to_var)).via(E.DFG).depth(max_hops)

        paths = self.query_engine.execute_any_path(query)

        logger.info(
            "dependency_query_complete",
            from_var=from_var,
            to_var=to_var,
            dependencies=len(paths.paths),
        )

        return paths

    # ============================================================
    # Hybrid Queries (Chunk + Analysis)
    # ============================================================

    async def find_vulnerable_chunks(
        self,
        repo_id: str,
        snapshot_id: str,
        analysis_type: str = "taint",
        severity: str = "high",
        limit: int = 50,
    ) -> list[dict]:
        """
        취약한 청크 찾기 (Chunk + Taint 분석)

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            analysis_type: Analysis type ("taint", "null", etc.)
            severity: Severity filter ("high", "medium", "low")
            limit: Max results

        Returns:
            List of vulnerable chunks with analysis results
        """
        # Step 1: Run taint analysis
        if not self.query_engine or analysis_type != "taint":
            return []

        from codegraph_engine.code_foundation.domain.query.factories import E, Q

        # Find all taint flows
        source = Q.Source("request")
        sink = Q.Sink("sql")
        query = (source >> sink).via(E.DFG).depth(10)

        paths = self.query_engine.execute_any_path(query)

        # Step 2: Map paths to chunks
        vulnerable_chunks = []

        for path in paths.paths[:limit]:
            # Get file path and line from path
            if path.nodes:
                first_node = path.nodes[0]
                file_path = first_node.attrs.get("file_path")
                line = first_node.attrs.get("line_number")

                if file_path and line:
                    # Find chunk at this location
                    chunk = await self.chunk_store.find_chunk_by_file_and_line(repo_id, file_path, line)

                    if chunk:
                        vulnerable_chunks.append(
                            {
                                "chunk": chunk,
                                "vulnerability": {
                                    "type": "taint",
                                    "severity": severity,
                                    "path": str(path),
                                },
                            }
                        )

        logger.info(
            "vulnerable_chunks_found",
            count=len(vulnerable_chunks),
            analysis=analysis_type,
        )

        return vulnerable_chunks

    async def find_high_complexity_chunks(
        self,
        repo_id: str,
        snapshot_id: str,
        threshold: float = 10.0,
        limit: int = 50,
    ) -> list[Any]:
        """
        복잡도 높은 청크 찾기

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            threshold: Complexity threshold (Cyclomatic)
            limit: Max results

        Returns:
            List of high-complexity chunks
        """
        # Query chunks with complexity in attrs (JSONB)
        pool = await self.chunk_store._get_pool()

        query = """
            SELECT * FROM chunks
            WHERE repo_id = $1
              AND snapshot_id = $2
              AND kind IN ('function', 'method')
              AND (attrs->>'complexity')::float > $3
              AND is_deleted = FALSE
            ORDER BY (attrs->>'complexity')::float DESC
            LIMIT $4
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, repo_id, snapshot_id, threshold, limit)
            chunks = [self.chunk_store._chunk_from_row(row) for row in rows]

        logger.info("high_complexity_query_complete", count=len(chunks))
        return chunks

    # ============================================================
    # Search Queries (Natural Language)
    # ============================================================

    async def search_chunks(
        self,
        repo_id: str,
        snapshot_id: str,
        query: str,
        limit: int = 20,
    ) -> list[Any]:
        """
        자연어로 청크 검색

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            query: Natural language query
            limit: Max results

        Returns:
            List of matching chunks
        """
        if not self.retrieval_service:
            raise RuntimeError("Retrieval service not available")

        # Use retrieval service
        result = await self.retrieval_service.retrieve(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            query=query,
            token_budget=4000,
        )

        # Extract chunk IDs from result
        chunk_ids = [hit.chunk_id for hit in result.hits[:limit]]

        # Load chunks
        chunks_dict = await self.chunk_store.get_chunks_batch(chunk_ids)
        chunks = [chunks_dict[cid] for cid in chunk_ids if cid in chunks_dict]

        logger.info("search_query_complete", query_preview=query[:50], count=len(chunks))
        return chunks


# ============================================================
# Query Builder (Fluent API)
# ============================================================


class ChunkQueryBuilder:
    """
    Fluent API for building chunk queries

    Usage:
        query = (ChunkQueryBuilder()
            .repo("myrepo")
            .kind("function")
            .in_file("backend/auth/*")
            .visibility("public")
            .limit(50)
        )

        chunks = await api.execute(query)
    """

    def __init__(self):
        self._repo_id: str | None = None
        self._snapshot_id: str | None = None
        self._kind: str | None = None
        self._fqn_pattern: str | None = None
        self._file_path: str | None = None
        self._language: str | None = None
        self._visibility: str | None = None
        self._limit: int = 100

    def repo(self, repo_id: str, snapshot_id: str | None = None) -> "ChunkQueryBuilder":
        """Set repository"""
        self._repo_id = repo_id
        self._snapshot_id = snapshot_id
        return self

    def kind(self, kind: str) -> "ChunkQueryBuilder":
        """Filter by chunk kind"""
        self._kind = kind
        return self

    def fqn(self, pattern: str) -> "ChunkQueryBuilder":
        """Filter by FQN pattern (SQL LIKE)"""
        self._fqn_pattern = pattern
        return self

    def in_file(self, path_pattern: str) -> "ChunkQueryBuilder":
        """Filter by file path pattern"""
        self._file_path = path_pattern
        return self

    def language(self, lang: str) -> "ChunkQueryBuilder":
        """Filter by language"""
        self._language = lang
        return self

    def visibility(self, vis: str) -> "ChunkQueryBuilder":
        """Filter by visibility"""
        self._visibility = vis
        return self

    def limit(self, n: int) -> "ChunkQueryBuilder":
        """Set limit"""
        self._limit = n
        return self

    def build(self) -> dict[str, Any]:
        """Build query params"""
        return {
            "repo_id": self._repo_id,
            "snapshot_id": self._snapshot_id,
            "kind": self._kind,
            "fqn_pattern": self._fqn_pattern,
            "file_path": self._file_path,
            "language": self._language,
            "visibility": self._visibility,
            "limit": self._limit,
        }


# ============================================================
# Convenience Functions
# ============================================================


async def query_chunks_by_kind(
    api: UnifiedQueryAPI,
    repo_id: str,
    kind: str,
    limit: int = 100,
) -> list[Any]:
    """
    Kind로 청크 검색

    Example:
        functions = await query_chunks_by_kind(api, "myrepo", "function")
    """
    return await api.find_chunks(repo_id=repo_id, kind=kind, limit=limit)


async def query_chunks_by_file(
    api: UnifiedQueryAPI,
    repo_id: str,
    file_path: str,
) -> list[Any]:
    """
    파일로 청크 검색

    Example:
        chunks = await query_chunks_by_file(api, "myrepo", "auth/service.py")
    """
    return await api.find_chunks(repo_id=repo_id, file_path=file_path, limit=1000)


def query_taint_in_function(
    api: UnifiedQueryAPI,
    func_name: str,
) -> Any:
    """
    특정 함수 내 Taint 찾기

    Example:
        paths = query_taint_in_function(api, "process_payment")
    """
    from codegraph_engine.code_foundation.domain.query.factories import E, Q

    source = Q.Source("request")
    sink = Q.Sink("sql")
    query = (source >> sink).via(E.DFG).within(Q.Func(func_name))

    return api.query_engine.execute_any_path(query)
