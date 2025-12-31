"""
Index Manager - 인메모리 인덱스 관리 및 QueryDSL.

인덱싱 완료 후 모든 레이어를 메모리에 로드하고
QueryDSL로 바로 쿼리 가능하게 제공.

Usage:
    # 인덱스 로드
    manager = IndexManager()
    manager.load_from_caches(ir_cache, global_ctx_cache, chunk_cache)

    # QueryDSL 사용
    results = manager.query("find function related to authentication")
    symbols = manager.get_symbols("Calculator")
    deps = manager.get_dependencies("src/main.py")
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IndexStats:
    """인덱스 통계."""

    files: int = 0
    nodes: int = 0
    edges: int = 0
    occurrences: int = 0
    symbols: int = 0
    dependencies: int = 0
    chunks: int = 0

    def __str__(self) -> str:
        return (
            f"IndexStats(files={self.files}, nodes={self.nodes}, edges={self.edges}, "
            f"occurrences={self.occurrences}, symbols={self.symbols}, "
            f"dependencies={self.dependencies}, chunks={self.chunks})"
        )


@dataclass
class QueryResult:
    """쿼리 결과."""

    results: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    query_time_ms: float = 0.0

    def __str__(self) -> str:
        return f"QueryResult(total={self.total}, time={self.query_time_ms:.2f}ms)"


class IndexManager:
    """
    인메모리 인덱스 매니저.

    모든 인덱스 레이어를 메모리에 로드하고 통합 쿼리 인터페이스 제공.
    """

    def __init__(self):
        """초기화."""
        # Core indexes
        self.ir_documents: dict[str, Any] = {}
        self.global_context: Any = None
        self.chunks: list[Any] = []

        # Metadata
        self.repo_id: str = ""
        self.repo_path: str = ""
        self.snapshot_id: str = ""

        # Stats
        self.stats = IndexStats()

    def load_from_caches(
        self,
        ir_cache: dict[str, Any],
        global_ctx_cache: dict[str, Any] | None = None,
        chunk_cache: dict[str, Any] | None = None,
        ir_cache_key: str | None = None,
        global_ctx_key: str | None = None,
        chunk_cache_key: str | None = None,
    ):
        """
        캐시에서 인덱스 로드.

        Args:
            ir_cache: IR 캐시
            global_ctx_cache: GlobalContext 캐시
            chunk_cache: Chunk 캐시
            ir_cache_key: IR 캐시 키 (None이면 첫 번째 항목 사용)
            global_ctx_key: GlobalContext 캐시 키
            chunk_cache_key: Chunk 캐시 키
        """
        # Load IR
        if ir_cache_key is None:
            # Use first key
            ir_cache_key = next(iter(ir_cache.keys())) if ir_cache else None

        if ir_cache_key and ir_cache_key in ir_cache:
            ir_data = ir_cache[ir_cache_key]
            self.ir_documents = ir_data.get("ir_documents", {})
            self.repo_id = ir_data.get("repo_id", "")
            self.repo_path = ir_data.get("repo_path", "")
            self.snapshot_id = ir_data.get("snapshot_id", "")

            # Calculate stats
            self.stats.files = len(self.ir_documents)
            for ir_doc in self.ir_documents.values():
                if hasattr(ir_doc, "nodes"):
                    self.stats.nodes += len(ir_doc.nodes)
                if hasattr(ir_doc, "edges"):
                    self.stats.edges += len(ir_doc.edges)
                if hasattr(ir_doc, "occurrences"):
                    self.stats.occurrences += len(ir_doc.occurrences)

        # Load GlobalContext
        if global_ctx_cache and global_ctx_key:
            if global_ctx_key in global_ctx_cache:
                ctx_data = global_ctx_cache[global_ctx_key]
                self.global_context = ctx_data.get("global_ctx")
                if self.global_context:
                    self.stats.symbols = getattr(self.global_context, "total_symbols", 0)
                    # Count dependencies
                    if hasattr(self.global_context, "dependencies"):
                        self.stats.dependencies = sum(len(deps) for deps in self.global_context.dependencies.values())

        # Load Chunks
        if chunk_cache and chunk_cache_key:
            if chunk_cache_key in chunk_cache:
                chunk_data = chunk_cache[chunk_cache_key]
                self.chunks = chunk_data.get("chunks", [])
                self.stats.chunks = len(self.chunks)

    def get_stats(self) -> IndexStats:
        """인덱스 통계 반환."""
        return self.stats

    # ============================================================
    # QueryDSL - 간단한 쿼리 인터페이스
    # ============================================================

    def get_file(self, file_path: str) -> dict[str, Any] | None:
        """파일 IR 조회."""
        ir_doc = self.ir_documents.get(file_path)
        if not ir_doc:
            return None

        return {
            "file_path": getattr(ir_doc, "file_path", file_path),
            "nodes": len(getattr(ir_doc, "nodes", [])),
            "edges": len(getattr(ir_doc, "edges", [])),
            "has_bfg": len(getattr(ir_doc, "bfg_graphs", [])) > 0,
            "has_dfg": len(getattr(ir_doc, "dfg_graphs", [])) > 0,
            "has_ssa": len(getattr(ir_doc, "ssa_graphs", [])) > 0,
        }

    def get_symbols(self, pattern: str) -> list[dict[str, Any]]:
        """
        심볼 검색 (GlobalContext 사용).

        Args:
            pattern: 심볼 이름 패턴 (부분 매칭)

        Returns:
            매칭된 심볼 리스트
        """
        if not self.global_context:
            return []

        results = []
        pattern_lower = pattern.lower()

        if hasattr(self.global_context, "symbol_table"):
            for fqn, (node, file_path) in self.global_context.symbol_table.items():
                if pattern_lower in fqn.lower():
                    # Handle span (could be dict or object)
                    span = getattr(node, "span", None)
                    line = None
                    if span:
                        if isinstance(span, dict):
                            line = span.get("start_line")
                        else:
                            line = getattr(span, "start_line", None)

                    results.append(
                        {
                            "fqn": fqn,
                            "node_id": getattr(node, "id", ""),
                            "kind": getattr(node, "kind", ""),
                            "file_path": file_path,
                            "line": line,
                        }
                    )

        return results

    def get_dependencies(self, file_path: str) -> dict[str, Any]:
        """
        파일 의존성 조회.

        Args:
            file_path: 파일 경로

        Returns:
            의존성 정보
        """
        if not self.global_context:
            return {"dependencies": [], "dependents": []}

        deps = []
        dependents = []

        if hasattr(self.global_context, "dependencies"):
            deps = list(self.global_context.dependencies.get(file_path, set()))

        if hasattr(self.global_context, "dependents"):
            dependents = list(self.global_context.dependents.get(file_path, set()))

        return {
            "file_path": file_path,
            "dependencies": deps,
            "dependents": dependents,
            "dep_count": len(deps),
            "dependent_count": len(dependents),
        }

    def find_nodes(self, kind: str | None = None, name_pattern: str | None = None) -> list[dict[str, Any]]:
        """
        노드 검색.

        Args:
            kind: 노드 종류 필터 (예: "function", "class")
            name_pattern: 이름 패턴 (부분 매칭)

        Returns:
            매칭된 노드 리스트
        """
        results = []

        for file_path, ir_doc in self.ir_documents.items():
            if not hasattr(ir_doc, "nodes"):
                continue

            for node in ir_doc.nodes:
                # Kind filter
                if kind and getattr(node, "kind", "") != kind:
                    continue

                # Name pattern filter
                node_name = getattr(node, "name", "")
                if name_pattern and name_pattern.lower() not in node_name.lower():
                    continue

                # Handle span
                span = getattr(node, "span", None)
                line = None
                if span:
                    if isinstance(span, dict):
                        line = span.get("start_line")
                    else:
                        line = getattr(span, "start_line", None)

                results.append(
                    {
                        "id": getattr(node, "id", ""),
                        "kind": getattr(node, "kind", ""),
                        "name": node_name,
                        "fqn": getattr(node, "fqn", ""),
                        "file_path": file_path,
                        "line": line,
                    }
                )

        return results

    def get_function_flow(self, function_fqn: str) -> dict[str, Any] | None:
        """
        함수의 flow graph 조회 (BFG, CFG, DFG, SSA).

        Args:
            function_fqn: 함수 FQN

        Returns:
            Flow graph 정보
        """
        # Find function in IR documents
        for file_path, ir_doc in self.ir_documents.items():
            if not hasattr(ir_doc, "nodes"):
                continue

            # Find function node
            function_node = None
            for node in ir_doc.nodes:
                if getattr(node, "fqn", "") == function_fqn and getattr(node, "kind", "") == "function":
                    function_node = node
                    break

            if not function_node:
                continue

            function_id = getattr(function_node, "id", "")

            # Collect flow graphs
            result = {
                "function_fqn": function_fqn,
                "function_id": function_id,
                "file_path": file_path,
                "bfg": None,
                "cfg": [],
                "dfg": None,
                "ssa": None,
            }

            # BFG
            if hasattr(ir_doc, "bfg_graphs"):
                for bfg in ir_doc.bfg_graphs:
                    if getattr(bfg, "function_id", "") == function_id:
                        result["bfg"] = {
                            "entry_block": getattr(bfg, "entry_block_id", ""),
                            "exit_block": getattr(bfg, "exit_block_id", ""),
                            "blocks": len(getattr(bfg, "blocks", [])),
                            "statements": getattr(bfg, "total_statements", 0),
                        }
                        break

            # CFG
            if hasattr(ir_doc, "cfg_edges"):
                result["cfg"] = [
                    {
                        "source": getattr(edge, "source_block_id", ""),
                        "target": getattr(edge, "target_block_id", ""),
                        "type": getattr(edge, "edge_type", ""),
                    }
                    for edge in ir_doc.cfg_edges
                ]

            # DFG
            if hasattr(ir_doc, "dfg_graphs"):
                for dfg in ir_doc.dfg_graphs:
                    if getattr(dfg, "function_id", "") == function_id:
                        result["dfg"] = {
                            "nodes": getattr(dfg, "node_count", 0),
                            "edges": getattr(dfg, "edge_count", 0),
                        }
                        break

            # SSA
            if hasattr(ir_doc, "ssa_graphs"):
                for ssa in ir_doc.ssa_graphs:
                    if getattr(ssa, "function_id", "") == function_id:
                        result["ssa"] = {
                            "variables": getattr(ssa, "variable_count", 0),
                            "phi_nodes": getattr(ssa, "phi_node_count", 0),
                        }
                        break

            return result

        return None

    def get_chunks_for_file(self, file_path: str) -> list[dict[str, Any]]:
        """
        파일의 청크 조회.

        Args:
            file_path: 파일 경로

        Returns:
            청크 리스트
        """
        results = []

        for chunk in self.chunks:
            chunk_file = getattr(chunk, "file_path", "")
            if file_path in chunk_file:
                results.append(
                    {
                        "chunk_id": getattr(chunk, "chunk_id", ""),
                        "content": getattr(chunk, "content", "")[:100] + "...",
                        "start_line": getattr(chunk, "start_line", 0),
                        "end_line": getattr(chunk, "end_line", 0),
                        "kind": getattr(chunk, "chunk_kind", ""),
                    }
                )

        return results

    # ============================================================
    # Advanced QueryDSL
    # ============================================================

    def query_semantic(self, query_type: str, **kwargs) -> QueryResult:
        """
        Semantic 쿼리 (BFG, CFG, DFG, SSA 활용).

        Query types:
            - "find_loops": 루프 찾기
            - "find_branches": 분기 찾기
            - "trace_variable": 변수 추적 (DFG)
            - "find_phi_nodes": SSA phi node 찾기
        """
        import time

        start = time.time()
        results = []

        if query_type == "find_functions_with_loops":
            # BFG에서 루프가 있는 함수 찾기
            for file_path, ir_doc in self.ir_documents.items():
                if not hasattr(ir_doc, "bfg_graphs"):
                    continue

                for bfg in ir_doc.bfg_graphs:
                    # Check if BFG has loops (back edges)
                    function_id = getattr(bfg, "function_id", "")
                    blocks = getattr(bfg, "blocks", [])

                    if len(blocks) > 2:  # Simple heuristic
                        # Find function node
                        for node in ir_doc.nodes:
                            if getattr(node, "id", "") == function_id:
                                results.append(
                                    {
                                        "function_fqn": getattr(node, "fqn", ""),
                                        "file_path": file_path,
                                        "blocks": len(blocks),
                                    }
                                )
                                break

        elif query_type == "find_functions_with_ssa":
            # SSA가 있는 함수 찾기
            for file_path, ir_doc in self.ir_documents.items():
                if not hasattr(ir_doc, "ssa_graphs"):
                    continue

                for ssa in ir_doc.ssa_graphs:
                    function_id = getattr(ssa, "function_id", "")
                    phi_count = getattr(ssa, "phi_node_count", 0)
                    var_count = getattr(ssa, "variable_count", 0)

                    if phi_count > 0:
                        # Find function node
                        for node in ir_doc.nodes:
                            if getattr(node, "id", "") == function_id:
                                results.append(
                                    {
                                        "function_fqn": getattr(node, "fqn", ""),
                                        "file_path": file_path,
                                        "phi_nodes": phi_count,
                                        "variables": var_count,
                                    }
                                )
                                break

        query_time_ms = (time.time() - start) * 1000

        return QueryResult(
            results=results,
            total=len(results),
            query_time_ms=query_time_ms,
        )

    def get_call_graph(self, max_depth: int = 2) -> dict[str, list[str]]:
        """
        호출 그래프 추출.

        Args:
            max_depth: 최대 깊이

        Returns:
            caller → callees 매핑
        """
        call_graph: dict[str, list[str]] = {}

        for file_path, ir_doc in self.ir_documents.items():
            if not hasattr(ir_doc, "edges"):
                continue

            for edge in ir_doc.edges:
                if getattr(edge, "kind", "") == "calls":
                    source_id = getattr(edge, "source_id", "")
                    target_id = getattr(edge, "target_id", "")

                    # Find source and target FQNs
                    source_fqn = self._find_node_fqn(source_id)
                    target_fqn = self._find_node_fqn(target_id)

                    if source_fqn and target_fqn:
                        call_graph.setdefault(source_fqn, []).append(target_fqn)

        return call_graph

    def _find_node_fqn(self, node_id: str) -> str | None:
        """노드 ID로 FQN 찾기."""
        for ir_doc in self.ir_documents.values():
            if not hasattr(ir_doc, "nodes"):
                continue

            for node in ir_doc.nodes:
                if getattr(node, "id", "") == node_id:
                    return getattr(node, "fqn", None)

        return None

    def summary(self) -> str:
        """인덱스 요약 출력."""
        lines = [
            "=" * 80,
            "Index Manager Summary".center(80),
            "=" * 80,
            "",
            f"Repository: {self.repo_id}",
            f"Path: {self.repo_path}",
            f"Snapshot: {self.snapshot_id}",
            "",
            "Indexes Loaded:",
            f"  ✅ IR Documents: {self.stats.files} files",
            f"  ✅ Nodes: {self.stats.nodes:,}",
            f"  ✅ Edges: {self.stats.edges:,}",
            f"  ✅ Occurrences: {self.stats.occurrences:,}",
            f"  ✅ Symbols (GlobalContext): {self.stats.symbols:,}",
            f"  ✅ Dependencies: {self.stats.dependencies:,}",
            f"  ✅ Chunks: {self.stats.chunks:,}",
            "",
            "Available Queries:",
            "  • manager.get_file(file_path)",
            "  • manager.get_symbols(pattern)",
            "  • manager.get_dependencies(file_path)",
            "  • manager.find_nodes(kind, name_pattern)",
            "  • manager.get_function_flow(function_fqn)",
            "  • manager.query_semantic('find_functions_with_loops')",
            "  • manager.get_call_graph()",
            "",
            "=" * 80,
        ]
        return "\n".join(lines)
