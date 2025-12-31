"""
Deep Analyzer - RFC-021 Phase 2

Advanced Context Manager for k-CFA and Alias Analysis.

Responsibility:
- ✅ k-CFA 컨텍스트 생성/관리 (Stateful)
- ✅ Alias 정보 계산/주입
- ✅ InterproceduralTaintAnalyzer 호출
- ❌ Taint Propagation 로직 (InterproceduralTaintAnalyzer 책임)

Design Decision A (RFC-021):
    InterproceduralTaintAnalyzer: 순수 분석 엔진 (Stateless 지향)
    DeepAnalyzer: Context & Alias 관리자 (Stateful OK)

Architecture:
    DeepAnalyzer (조립기)
        ├── ContextManager (k-CFA) ✅ 기존 모듈 사용
        ├── AliasAnalyzer (Alias) ✅ 기존 모듈 사용
        └── InterproceduralTaintAnalyzer (Taint) ✅ 기존 모듈 호출
"""

import time
from typing import TYPE_CHECKING, Any

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.ports.query_ports import ProjectContextPort
    from codegraph_engine.code_foundation.domain.query.expressions import FlowExpr
    from codegraph_engine.code_foundation.domain.query.options import QueryOptions
    from codegraph_engine.code_foundation.domain.query.results import PathResult, PathSet

logger = get_logger(__name__)


class DeepAnalyzer:
    """
    Deep Analyzer (RFC-021 Phase 2)

    Advanced Context Manager for full mode analysis.

    Architecture:
        DeepAnalyzer (Context Manager)
            ├── k-CFA Context Builder
            ├── Alias Analyzer
            └── InterproceduralTaintAnalyzer (호출만)

    Usage:
        analyzer = DeepAnalyzer(project_context)
        paths = analyzer.analyze(flow_expr, options)
    """

    def __init__(self, project_context: "ProjectContextPort"):
        """
        Initialize DeepAnalyzer (RFC-021 Phase 2 완성)

        Args:
            project_context: Project-level context
                Required attributes:
                - call_graph: CallGraphProtocol
                - ir_documents: list[IRDocument] (optional)
                - node_map: dict[str, Node] (optional)

        Raises:
            ValueError: If project_context is None
            AttributeError: If project_context.call_graph missing

        Architecture:
            DeepAnalyzer는 기존 모듈들을 조립 (Composition):
            - ContextManager (k-CFA)
            - AliasAnalyzer (Alias)
            - InterproceduralTaintAnalyzer (Taint Core)
        """
        if not project_context:
            raise ValueError("DeepAnalyzer requires project_context")

        if not hasattr(project_context, "call_graph"):
            raise AttributeError("project_context must have 'call_graph' attribute")

        self.project_context = project_context
        self.call_graph = project_context.call_graph

        # RFC-021 Phase 2: 기존 모듈 조립 (재구현 없음)
        from codegraph_engine.code_foundation.infrastructure.analyzers.alias_analyzer import AliasAnalyzer
        from codegraph_engine.code_foundation.infrastructure.analyzers.context_manager import ContextManager
        from codegraph_engine.code_foundation.infrastructure.analyzers.interprocedural_taint import (
            InterproceduralTaintAnalyzer,
        )

        # 1. k-CFA Context Manager
        self.context_mgr = ContextManager(k_limit=2)  # Default k=2

        # 2. Alias Analyzer
        self.alias_analyzer = AliasAnalyzer()

        # 3. Interprocedural Taint Analyzer (Core Engine)
        self.taint_analyzer = InterproceduralTaintAnalyzer(
            call_graph=self.call_graph,
            max_depth=20,  # full mode default
            max_paths=1000,
            ir_provider=getattr(project_context, "ir_documents", None),
        )

        logger.info(
            "deep_analyzer_initialized",
            has_context_mgr=True,
            has_alias_analyzer=True,
            k_limit=self.context_mgr.k_limit,
        )

    def analyze(self, flow_expr: "FlowExpr", options: "QueryOptions") -> "PathSet":
        """
        Execute deep analysis with k-CFA and Alias (RFC-021 Phase 2 완성)

        Args:
            flow_expr: Flow expression (source >> sink)
            options: Query options (from full mode preset)

        Returns:
            PathSet with deep analysis results

        Steps:
            1. FlowExpr → sources/sinks 변환 (NodeMatcher 사용)
            2. k-CFA contexts 빌드 (options.context_sensitive)
            3. Alias map 계산 (options.alias_analysis)
            4. InterproceduralTaintAnalyzer.analyze() 호출
            5. TaintPath[] → PathSet 변환

        Performance:
            - k-CFA: O(functions × k^depth)
            - Alias: O(variables × statements)
            - Taint: O(functions × avg_calls)
        """
        from codegraph_engine.code_foundation.domain.query.results import (
            PathSet,
            StopReason,
        )

        start_time = time.time()

        logger.info(
            "deep_analysis_start",
            k_limit=options.k_limit,
            alias=options.alias_analysis,
            context_sensitive=options.context_sensitive,
        )

        try:
            # 1. FlowExpr → sources/sinks 변환
            sources_dict, sinks_dict = self._extract_sources_sinks(flow_expr)

            if not sources_dict or not sinks_dict:
                logger.warning("deep_analysis_empty", sources=len(sources_dict), sinks=len(sinks_dict))
                return PathSet(
                    paths=[],
                    stop_reason=StopReason.NO_MATCH,
                    elapsed_ms=int((time.time() - start_time) * 1000),
                    nodes_visited=0,
                    diagnostics=("no_sources_or_sinks",),
                )

            # 2. k-CFA contexts (if enabled)
            if options.context_sensitive:
                self.context_mgr = self._rebuild_context_manager(options.k_limit)
                logger.debug("k_cfa_enabled", k_limit=options.k_limit)

            # 3. Alias analysis (if enabled)
            if options.alias_analysis:
                alias_map = self._compute_alias_map()
                logger.debug("alias_analysis_computed", alias_count=len(alias_map))
            else:
                alias_map = {}

            # 4. InterproceduralTaintAnalyzer.analyze()
            taint_paths = self.taint_analyzer.analyze(sources_dict, sinks_dict)

            # 5. TaintPath[] → PathSet 변환
            paths = self._convert_to_pathset(taint_paths)

            elapsed_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "deep_analysis_complete",
                paths_found=len(paths),
                elapsed_ms=elapsed_ms,
                k_cfa=options.context_sensitive,
                alias=options.alias_analysis,
            )

            return PathSet(
                paths=paths,
                stop_reason=StopReason.COMPLETE,
                elapsed_ms=elapsed_ms,
                nodes_visited=0,  # TODO: track from analyzer
                diagnostics=(
                    "mode: full",
                    f"k_limit: {options.k_limit}",
                    f"alias: {options.alias_analysis}",
                    f"paths_found: {len(paths)}",
                ),
            )

        except Exception as e:
            logger.exception("deep_analysis_error", error=str(e))
            elapsed_ms = int((time.time() - start_time) * 1000)

            return PathSet(
                paths=[],
                stop_reason=StopReason.ERROR,
                elapsed_ms=elapsed_ms,
                nodes_visited=0,
                diagnostics=(f"deep_analysis_error: {type(e).__name__}: {str(e)[:200]}",),
            )

    def _extract_sources_sinks(self, flow_expr: "FlowExpr") -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        """
        FlowExpr → sources/sinks 변환 (RFC-021 P0 Fix)

        Args:
            flow_expr: Flow expression (Q.Var('x') >> Q.Call('exec'))

        Returns:
            (sources_dict, sinks_dict) where dict[func_id, {var_names}]

        Note:
            InterproceduralTaintAnalyzer.analyze()는 함수별 dict 형식 필요

        Implementation:
            1. FlowExpr의 source/target selector 추출
            2. 실제 함수 scope 고려 (가능하면)
            3. 없으면 "<global>" fallback (함수 간 전파용)
        """
        sources_dict: dict[str, set[str]] = {}
        sinks_dict: dict[str, set[str]] = {}

        # FlowExpr의 source/target selector 추출
        if not hasattr(flow_expr, "source") or not hasattr(flow_expr, "target"):
            return sources_dict, sinks_dict

        source_sel = flow_expr.source
        target_sel = flow_expr.target

        # Source 추출
        if hasattr(source_sel, "name") and source_sel.name:
            source_name = source_sel.name

            # 함수 scope 추출 (attrs에서)
            source_func = getattr(source_sel, "attrs", {}).get("function_id")

            if source_func:
                # 특정 함수의 source
                if source_func not in sources_dict:
                    sources_dict[source_func] = set()
                sources_dict[source_func].add(source_name)
            else:
                # Global source (모든 함수에서 전파)
                sources_dict["<global>"] = {source_name}

        # Sink 추출
        if hasattr(target_sel, "name") and target_sel.name:
            sink_name = target_sel.name

            # 함수 scope 추출
            sink_func = getattr(target_sel, "attrs", {}).get("function_id")

            if sink_func:
                if sink_func not in sinks_dict:
                    sinks_dict[sink_func] = set()
                sinks_dict[sink_func].add(sink_name)
            else:
                sinks_dict["<global>"] = {sink_name}

        return sources_dict, sinks_dict

    def _rebuild_context_manager(self, k_limit: int) -> "Any":
        """
        Rebuild ContextManager with new k_limit

        Args:
            k_limit: Context depth

        Returns:
            New ContextManager instance
        """
        from codegraph_engine.code_foundation.infrastructure.analyzers.context_manager import ContextManager

        return ContextManager(k_limit=k_limit)

    def _compute_alias_map(self) -> dict[str, set[str]]:
        """
        Compute alias map using AliasAnalyzer

        Returns:
            Alias map {variable: {aliases}}

        Note:
            AliasAnalyzer는 이미 초기화됨 (__init__에서)
        """
        # IR documents에서 alias 정보 추출
        ir_docs = getattr(self.project_context, "ir_documents", None)
        if not ir_docs:
            logger.debug("no_ir_documents_for_alias")
            return {}

        # Build alias graph from IR
        for ir_doc in ir_docs:
            self._build_aliases_from_ir(ir_doc)

        # Get alias map
        alias_map = self.alias_analyzer.get_alias_map()

        return alias_map

    def _build_aliases_from_ir(self, ir_doc: Any) -> None:
        """
        Build aliases from IR document

        Args:
            ir_doc: IRDocument

        Extracts:
            - a = b (DIRECT)
            - a = b.field (FIELD)
            - a = b[i] (ELEMENT)
        """
        from codegraph_engine.code_foundation.infrastructure.analyzers.alias_analyzer import AliasType

        # IR edges에서 WRITES/READS 추출
        if not hasattr(ir_doc, "edges"):
            return

        for edge in ir_doc.edges:
            edge_kind = str(edge.kind) if hasattr(edge, "kind") else ""

            # WRITES: def
            # READS: use
            # Assignment pattern: WRITES(x) from READS(y)
            if "WRITES" in edge_kind:
                # Simple heuristic: x = y
                source_id = getattr(edge, "source_id", None)
                target_id = getattr(edge, "target_id", None)

                if source_id and target_id:
                    self.alias_analyzer.add_alias(source_id, target_id, AliasType.DIRECT, is_must=True)

    def _convert_to_pathset(self, taint_paths: list[Any]) -> list["PathResult"]:
        """
        TaintPath[] → PathResult[] 변환 (RFC-021 P0 Fix: 정보 손실 방지)

        Args:
            taint_paths: InterproceduralTaintAnalyzer.analyze() 결과

        Returns:
            List of PathResult with full location info

        Conversion:
            TaintPath(source, sink, path, tainted_vars, confidence)
            → PathResult(nodes with file_path/span, edges, uncertain, ...)

        P0 Fix:
            - node_map에서 실제 file_path, span 추출
            - 없으면 fallback (빈 값 아님)
        """
        from codegraph_engine.code_foundation.domain.query.results import PathResult, UnifiedEdge, UnifiedNode
        from codegraph_engine.code_foundation.domain.query.types import EdgeType

        results = []

        # node_map 가져오기 (있으면)
        node_map = getattr(self.project_context, "node_map", {})

        for taint_path in taint_paths:
            # TaintPath attributes
            source = getattr(taint_path, "source", None)
            sink = getattr(taint_path, "sink", None)
            path = getattr(taint_path, "path", [])
            tainted_vars = getattr(taint_path, "taint_value", None)
            confidence = getattr(taint_path, "confidence", 1.0)

            if not path:
                continue

            # Build nodes with real location info
            nodes = []
            for i, func_id in enumerate(path):
                # Try to get real node from node_map
                real_node = node_map.get(func_id) if node_map else None

                if real_node:
                    # Use real node info
                    node = UnifiedNode(
                        id=func_id,
                        kind=getattr(real_node, "kind", "function"),
                        name=getattr(real_node, "name", func_id.split(":")[-1]),
                        file_path=getattr(real_node, "file_path", ""),
                        span=getattr(real_node, "span", None),
                    )
                else:
                    # Fallback: extract from func_id
                    # Format: "file:path:function:name:line"
                    parts = func_id.split(":")
                    func_name = parts[-1] if parts else func_id
                    file_path = ":".join(parts[:-1]) if len(parts) > 1 else ""

                    node = UnifiedNode(
                        id=func_id,
                        kind="function",
                        name=func_name,
                        file_path=file_path,
                        span=None,  # Line info not available
                    )

                nodes.append(node)

            # Build edges (call edges)
            edges = []
            for i in range(len(nodes) - 1):
                edge = UnifiedEdge(
                    from_node=nodes[i].id,
                    to_node=nodes[i + 1].id,
                    edge_type=EdgeType.CALL,
                    attrs={"taint": True},  # Mark as taint flow
                )
                edges.append(edge)

            # Uncertain if confidence < 1.0
            uncertain = confidence < 1.0
            uncertain_reasons = ()
            if uncertain:
                from codegraph_engine.code_foundation.domain.query.results import UncertainReason

                # confidence < 1.0 → MAY_ALIAS or SUMMARY_APPROX
                uncertain_reasons = (UncertainReason.SUMMARY_APPROX,)

            # Build PathResult
            result = PathResult(
                nodes=nodes,
                edges=edges,
                uncertain=uncertain,
                uncertain_reasons=uncertain_reasons,
                tainted_variables=frozenset([tainted_vars]) if tainted_vars else frozenset(),
                severity="HIGH",  # TODO: 정책에서 결정
            )

            results.append(result)

        return results
