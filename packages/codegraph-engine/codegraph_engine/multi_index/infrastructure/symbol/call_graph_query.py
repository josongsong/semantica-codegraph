"""
Call Graph Query Builder

그래프 기반 호출 관계 쿼리 담당 (SRP).

Responsibilities:
- Callers 쿼리 (함수를 호출하는 심볼들)
- Callees 쿼리 (함수가 호출하는 심볼들)
- References 쿼리 (심볼을 참조하는 노드들)
- Imports 쿼리 (모듈을 임포트하는 파일들)

Architecture:
- Primary: UnifiedGraphIndex (in-memory, no external DB)
- Fallback: Empty results with warning (graceful degradation)
- Legacy: Memgraph (deprecated, optional)

Hexagonal Architecture:
- CallGraphQueryAdapter: Implements CallGraphQueryPort
- code_foundation uses Port, multi_index provides Adapter
"""

from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.ports.analysis_ports import (
    CalleeInfo,
    CallerInfo,
    CallGraphQueryPort,
)

logger = get_logger(__name__)


class CallGraphQueryBuilder:
    """
    그래프 호출 관계 쿼리 빌더.

    UnifiedGraphIndex 기반 (Memgraph 의존성 제거).

    Usage:
        builder = CallGraphQueryBuilder()  # No args needed
        callers = await builder.search_callers(repo_id, snapshot_id, "func_name", 10)
        callees = await builder.search_callees(repo_id, snapshot_id, "func_name", 10)
    """

    def __init__(self, graph_store: Any = None):
        """
        Args:
            graph_store: Optional graph store (deprecated, for backwards compatibility)
        """
        self.graph_store = graph_store
        self._graph_index = None

    def _get_graph_index(self):
        """Get UnifiedGraphIndex (lazy init)."""
        if self._graph_index is None:
            try:
                from src.container import container

                self._graph_index = container.graph_index()
            except Exception as e:
                logger.debug(f"graph_index not available: {e}")
                self._graph_index = None
        return self._graph_index

    def _get_driver(self):
        """Memgraph driver 접근 (deprecated fallback)."""
        if not self.graph_store:
            return None
        store = self.graph_store._store if hasattr(self.graph_store, "_store") else self.graph_store
        if hasattr(store, "_driver"):
            return store._driver
        return None

    async def search_callers(
        self,
        repo_id: str,
        snapshot_id: str,
        symbol_name: str,
        limit: int,
    ) -> list[dict]:
        """
        주어진 심볼을 호출하는 함수들 검색.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            symbol_name: 대상 심볼명
            limit: 최대 결과 수

        Returns:
            호출자 노드 리스트
        """
        # Strategy 1: Try UnifiedGraphIndex (preferred, no external DB)
        graph_index = self._get_graph_index()
        if graph_index:
            try:
                return await self._search_callers_via_index(graph_index, symbol_name, limit)
            except Exception as e:
                logger.debug(f"GraphIndex callers search failed: {e}")

        # Strategy 2: Try Memgraph driver (legacy fallback)
        driver = self._get_driver()
        if driver:
            try:
                with driver.session() as session:
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
                    return [self._record_to_dict(r, "caller") for r in result]
            except Exception as e:
                logger.debug(f"Memgraph callers search failed: {e}")

        # Strategy 3: Graceful degradation
        logger.warning(f"No graph backend available for search_callers({symbol_name})")
        return []

    async def _search_callers_via_index(self, graph_index: Any, symbol_name: str, limit: int) -> list[dict]:
        """Search callers using UnifiedGraphIndex."""
        results = []

        # Find the target function
        funcs = graph_index.find_funcs_by_name(symbol_name)
        if not funcs:
            return []

        for func in funcs[:1]:  # Take first match
            # Get edges pointing TO this node (callers call this func)
            edges = graph_index.get_edges_to(func.id)
            for edge in edges[:limit]:
                if edge.kind in ("CALL", "CALLS", "call"):
                    caller_node = graph_index.get_node(edge.source_id)
                    if caller_node:
                        results.append(
                            {
                                "node_id": caller_node.id,
                                "name": caller_node.name,
                                "fqn": getattr(caller_node, "fqn", caller_node.name),
                                "file_path": getattr(caller_node, "path", ""),
                                "line": getattr(caller_node, "span_start_line", 0),
                                "kind": caller_node.kind.value
                                if hasattr(caller_node.kind, "value")
                                else str(caller_node.kind),
                            }
                        )

        return results[:limit]

    async def search_callees(
        self,
        repo_id: str,
        snapshot_id: str,
        symbol_name: str,
        limit: int,
    ) -> list[dict]:
        """
        주어진 심볼이 호출하는 함수들 검색.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            symbol_name: 대상 심볼명
            limit: 최대 결과 수

        Returns:
            피호출자 노드 리스트
        """
        # Strategy 1: Try UnifiedGraphIndex
        graph_index = self._get_graph_index()
        if graph_index:
            try:
                return await self._search_callees_via_index(graph_index, symbol_name, limit)
            except Exception as e:
                logger.debug(f"GraphIndex callees search failed: {e}")

        # Strategy 2: Try Memgraph driver (legacy)
        driver = self._get_driver()
        if driver:
            try:
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
                    return [self._record_to_dict(r, "callee") for r in result]
            except Exception as e:
                logger.debug(f"Memgraph callees search failed: {e}")

        # Strategy 3: Graceful degradation
        logger.warning(f"No graph backend available for search_callees({symbol_name})")
        return []

    async def _search_callees_via_index(self, graph_index: Any, symbol_name: str, limit: int) -> list[dict]:
        """Search callees using UnifiedGraphIndex."""
        results = []

        funcs = graph_index.find_funcs_by_name(symbol_name)
        if not funcs:
            return []

        for func in funcs[:1]:
            # Get edges FROM this node (this func calls others)
            edges = graph_index.get_edges_from(func.id)
            for edge in edges[:limit]:
                if edge.kind in ("CALL", "CALLS", "call"):
                    callee_node = graph_index.get_node(edge.target_id)
                    if callee_node:
                        results.append(
                            {
                                "node_id": callee_node.id,
                                "name": callee_node.name,
                                "fqn": getattr(callee_node, "fqn", callee_node.name),
                                "file_path": getattr(callee_node, "path", ""),
                                "line": getattr(callee_node, "span_start_line", 0),
                                "kind": callee_node.kind.value
                                if hasattr(callee_node.kind, "value")
                                else str(callee_node.kind),
                            }
                        )

        return results[:limit]

    async def search_references(
        self,
        repo_id: str,
        snapshot_id: str,
        symbol_name: str,
        limit: int,
    ) -> list[dict]:
        """
        주어진 심볼을 참조하는 모든 노드 검색.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            symbol_name: 대상 심볼명
            limit: 최대 결과 수

        Returns:
            참조 노드 리스트
        """
        # Strategy 1: Try UnifiedGraphIndex
        graph_index = self._get_graph_index()
        if graph_index:
            try:
                return await self._search_references_via_index(graph_index, symbol_name, limit)
            except Exception as e:
                logger.debug(f"GraphIndex references search failed: {e}")

        # Strategy 2: Try Memgraph driver (legacy)
        driver = self._get_driver()
        if driver:
            try:
                with driver.session() as session:
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
                    return [self._record_to_dict(r, "ref") for r in result]
            except Exception as e:
                logger.debug(f"Memgraph references search failed: {e}")

        # Strategy 3: Graceful degradation
        logger.warning(f"No graph backend available for search_references({symbol_name})")
        return []

    async def _search_references_via_index(self, graph_index: Any, symbol_name: str, limit: int) -> list[dict]:
        """Search references using UnifiedGraphIndex."""
        results = []

        # Search in functions, classes, variables
        targets = (
            graph_index.find_funcs_by_name(symbol_name)
            + graph_index.find_classes_by_name(symbol_name)
            + graph_index.find_vars_by_name(symbol_name)
        )

        for target in targets[:3]:  # Limit search scope
            edges = graph_index.get_edges_to(target.id)
            for edge in edges[:limit]:
                ref_node = graph_index.get_node(edge.source_id)
                if ref_node:
                    results.append(
                        {
                            "node_id": ref_node.id,
                            "name": ref_node.name,
                            "fqn": getattr(ref_node, "fqn", ref_node.name),
                            "file_path": getattr(ref_node, "path", ""),
                            "line": getattr(ref_node, "span_start_line", 0),
                            "kind": ref_node.kind.value if hasattr(ref_node.kind, "value") else str(ref_node.kind),
                        }
                    )

        return results[:limit]

    async def search_imports(
        self,
        repo_id: str,
        snapshot_id: str,
        module_name: str,
        limit: int,
    ) -> list[dict]:
        """
        주어진 모듈을 임포트하는 파일들 검색.

        Args:
            repo_id: 저장소 ID
            snapshot_id: 스냅샷 ID
            module_name: 대상 모듈명
            limit: 최대 결과 수

        Returns:
            임포트하는 파일 노드 리스트
        """
        # Strategy 1: Try UnifiedGraphIndex
        graph_index = self._get_graph_index()
        if graph_index:
            try:
                return await self._search_imports_via_index(graph_index, module_name, limit)
            except Exception as e:
                logger.debug(f"GraphIndex imports search failed: {e}")

        # Strategy 2: Try Memgraph driver (legacy)
        driver = self._get_driver()
        if driver:
            try:
                with driver.session() as session:
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
                    return [self._record_to_dict(r, "file") for r in result]
            except Exception as e:
                logger.debug(f"Memgraph imports search failed: {e}")

        # Strategy 3: Graceful degradation
        logger.warning(f"No graph backend available for search_imports({module_name})")
        return []

    async def _search_imports_via_index(self, graph_index: Any, module_name: str, limit: int) -> list[dict]:
        """Search imports using UnifiedGraphIndex."""
        results = []

        # Get all nodes and filter by import edges
        all_nodes = graph_index.get_all_nodes()

        for node in all_nodes[: limit * 10]:  # Scan limit
            edges = graph_index.get_edges_from(node.id)
            for edge in edges:
                if edge.kind in ("IMPORT", "IMPORTS", "import"):
                    target_node = graph_index.get_node(edge.target_id)
                    if target_node and module_name.lower() in str(target_node.name).lower():
                        results.append(
                            {
                                "node_id": node.id,
                                "name": node.name,
                                "fqn": getattr(node, "fqn", node.name),
                                "file_path": getattr(node, "path", ""),
                                "line": getattr(node, "span_start_line", 0),
                                "kind": node.kind.value if hasattr(node.kind, "value") else str(node.kind),
                            }
                        )
                        break  # One import per file is enough

        return results[:limit]

    async def get_callers(self, symbol_id: str) -> list[dict[str, Any]]:
        """
        심볼 ID로 호출자 조회.

        Args:
            symbol_id: 심볼 ID

        Returns:
            호출자 노드 리스트
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
        심볼 ID로 피호출자 조회.

        Args:
            symbol_id: 심볼 ID

        Returns:
            피호출자 노드 리스트
        """
        try:
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

    async def get_references(self, symbol_id: str) -> list[dict[str, Any]]:
        """
        심볼 ID로 참조자 조회.

        Args:
            symbol_id: 심볼 ID

        Returns:
            참조 노드 리스트
        """
        try:
            neighbors = await self.graph_store.query_neighbors_bulk([symbol_id], direction="incoming")
            ref_ids = neighbors.get(symbol_id, [])

            if not ref_ids:
                return []

            return await self.graph_store.query_nodes_by_ids(ref_ids)
        except Exception as e:
            logger.error(f"get_references failed for {symbol_id}: {e}")
            return []

    async def get_node_by_id(self, node_id: str) -> dict[str, Any] | None:
        """
        노드 ID로 노드 조회.

        Args:
            node_id: 노드 ID

        Returns:
            노드 데이터 또는 None
        """
        try:
            return await self.graph_store.query_node_by_id(node_id)
        except Exception as e:
            logger.error(f"get_node_by_id failed for {node_id}: {e}")
            return None

    def _record_to_dict(self, record, prefix: str) -> dict:
        """Memgraph 레코드를 dict로 변환."""
        return {
            "node_id": record[f"{prefix}.node_id"],
            "repo_id": record[f"{prefix}.repo_id"],
            "lang": record[f"{prefix}.lang"],
            "kind": record[f"{prefix}.kind"],
            "fqn": record[f"{prefix}.fqn"],
            "name": record[f"{prefix}.name"],
            "path": record[f"{prefix}.path"],
            "snapshot_id": record[f"{prefix}.snapshot_id"],
            "span_start_line": record[f"{prefix}.span_start_line"],
            "span_end_line": record[f"{prefix}.span_end_line"],
        }


class CallGraphQueryAdapter(CallGraphQueryPort):
    """
    CallGraphQueryPort Adapter (Hexagonal Architecture)

    Wraps CallGraphQueryBuilder to implement CallGraphQueryPort.

    Usage:
        adapter = CallGraphQueryAdapter()
        callers = await adapter.get_callers(repo_id, snapshot_id, "func_name")

    Architecture:
        - Implements code_foundation's CallGraphQueryPort
        - Uses internal CallGraphQueryBuilder
        - Returns Port-defined types (CallerInfo, CalleeInfo)
    """

    def __init__(self, graph_store: Any = None):
        """
        Initialize adapter.

        Args:
            graph_store: Optional graph store (passed to CallGraphQueryBuilder)
        """
        self._builder = CallGraphQueryBuilder(graph_store)

    async def get_callers(
        self,
        repo_id: str,
        snapshot_id: str,
        symbol_name: str,
        limit: int = 20,
    ) -> list[CallerInfo]:
        """
        Get functions that call a given symbol.

        Implements CallGraphQueryPort.get_callers

        Returns:
            List of CallerInfo (Port-defined type)
        """
        # Use internal builder
        raw_results = await self._builder.search_callers(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            symbol_name=symbol_name,
            limit=limit,
        )

        # Convert to Port types
        return [
            CallerInfo(
                caller_name=r.get("name", r.get("caller_name", "unknown")),
                file_path=r.get("file_path", r.get("path", "")),
                line=r.get("line", r.get("span_start_line", 0)),
                call_type="direct",
            )
            for r in raw_results
        ]

    async def get_callees(
        self,
        repo_id: str,
        snapshot_id: str,
        symbol_name: str,
        limit: int = 20,
    ) -> list[CalleeInfo]:
        """
        Get functions called by a given symbol.

        Implements CallGraphQueryPort.get_callees

        Returns:
            List of CalleeInfo (Port-defined type)
        """
        # Use internal builder
        raw_results = await self._builder.search_callees(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            symbol_name=symbol_name,
            limit=limit,
        )

        # Convert to Port types
        return [
            CalleeInfo(
                callee_name=r.get("name", r.get("callee_name", "unknown")),
                file_path=r.get("file_path", r.get("path", "")),
                line=r.get("line", r.get("span_start_line", 0)),
            )
            for r in raw_results
        ]


# Factory function for DI
def create_call_graph_adapter(graph_store: Any = None) -> CallGraphQueryPort:
    """
    Factory function to create CallGraphQueryAdapter.

    Usage in DI container:
        container.register("call_graph_query", create_call_graph_adapter)

    Returns:
        CallGraphQueryPort implementation
    """
    return CallGraphQueryAdapter(graph_store)
