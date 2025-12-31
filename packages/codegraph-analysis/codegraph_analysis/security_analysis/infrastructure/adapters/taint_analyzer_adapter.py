"""
TaintAnalyzer Adapter for IRDocument

기존 taint_rules 시스템을 IRDocument에서 사용할 수 있도록 어댑터 제공

SOTA급 설계:
- 기존 taint_rules (검증된 700+ lines) 100% 활용
- IRDocument → call_graph, node_map 변환
- TaintPath → 새로운 Vulnerability 모델로 변환
"""

import logging

from codegraph_engine.code_foundation.infrastructure.analyzers.taint_analyzer import (
    TaintAnalyzer,
    TaintPath,
    TaintSink,
    TaintSource,
)
from codegraph_engine.code_foundation.infrastructure.analyzers.taint_rules.base import (
    SanitizerRule,
    SinkRule,
    SourceRule,
)
from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
from codegraph_analysis.security_analysis.infrastructure.adapters.variable_data_flow_tracker import (
    VariableDataFlowTracker,
)

logger = logging.getLogger(__name__)


class TaintAnalyzerAdapter:
    """
    TaintAnalyzer Adapter for IRDocument

    기존 TaintAnalyzer를 IRDocument와 함께 사용할 수 있도록 변환

    Features:
    - IRDocument → call_graph, node_map 변환
    - SourceRule → TaintSource 변환
    - SinkRule → TaintSink 변환
    - taint_rules 시스템 100% 활용
    """

    def __init__(
        self,
        source_rules: list[SourceRule],
        sink_rules: list[SinkRule],
        sanitizer_rules: list[SanitizerRule],
    ):
        """
        Args:
            source_rules: List of SourceRule from taint_rules
            sink_rules: List of SinkRule from taint_rules
            sanitizer_rules: List of SanitizerRule from taint_rules
        """
        self.source_rules = source_rules
        self.sink_rules = sink_rules
        self.sanitizer_rules = sanitizer_rules

        # ⭐ NEW: Variable data flow tracker
        self.data_flow_tracker = VariableDataFlowTracker()

        # Convert to TaintAnalyzer format
        sources = self._convert_sources()
        sinks = self._convert_sinks()
        sanitizers = self._convert_sanitizers()

        # Create TaintAnalyzer instance
        self.taint_analyzer = TaintAnalyzer(
            sources=sources,
            sinks=sinks,
            sanitizers=sanitizers,
        )

        logger.info(
            f"TaintAnalyzerAdapter initialized: "
            f"{len(sources)} sources, "
            f"{len(sinks)} sinks, "
            f"{len(sanitizers)} sanitizers"
        )

    def analyze(self, ir_document: IRDocument) -> list[TaintPath]:
        """
        Analyze taint flow in IRDocument

        Algorithm:
        1. IRDocument → call_graph, node_map 변환
        2. TaintAnalyzer.analyze_taint_flow() 실행
        3. TaintPath 반환

        Args:
            ir_document: IR document

        Returns:
            List of TaintPath
        """
        try:
            # 1. Extract call graph and node map from IR document
            call_graph, node_map = self._extract_graph_from_ir(ir_document)

            if not call_graph or not node_map:
                logger.warning("Empty call graph or node map")
                return []

            # 2. Find sources and sinks manually (TaintAnalyzer might return empty if no path)
            source_nodes = self.taint_analyzer._find_source_nodes(node_map)
            sink_nodes = self.taint_analyzer._find_sink_nodes(node_map)

            logger.debug(f"[ADAPTER ANALYZE] Found {len(source_nodes)} sources, {len(sink_nodes)} sinks")

            # 3. Run function-level taint analysis
            taint_paths = self.taint_analyzer.analyze_taint_flow(
                call_graph=call_graph,
                node_map=node_map,
            )

            logger.info(f"Found {len(taint_paths)} function-level taint paths")

            # ⭐ SOTA: If no function-level paths, try variable data flow for all source-sink pairs
            if not taint_paths and source_nodes and sink_nodes:
                logger.debug("No function-level paths, trying variable data flow...")
                logger.debug(f"source_nodes: {source_nodes}")
                logger.debug(f"sink_nodes: {sink_nodes}")

                for source_id in source_nodes:
                    logger.debug(f"Processing source: {source_id}")
                    for sink_id in sink_nodes:
                        logger.debug(f"Processing sink: {sink_id}")
                        # Use data flow tracker
                        data_paths = self.data_flow_tracker.find_data_flow_paths(
                            ir_document=ir_document,
                            source_id=source_id,
                            sink_id=sink_id,
                        )

                        if data_paths:
                            # Found path! Create TaintPath
                            from codegraph_engine.code_foundation.infrastructure.analyzers.taint_analyzer import (
                                TaintPath,
                            )

                            path_names = [self._get_node_name(node_id, node_map) for node_id in data_paths[0]]

                            source_node = node_map.get(source_id)
                            sink_node = node_map.get(sink_id)

                            if source_node and sink_node:
                                taint_path = TaintPath(
                                    source=source_node.name,
                                    sink=sink_node.name,
                                    path=path_names,
                                    is_sanitized=False,  # TODO: Check sanitization
                                )
                                taint_paths.append(taint_path)

                                logger.info(f"✅ Found variable data flow path: {' → '.join(path_names)}")

            logger.info(f"Found {len(taint_paths)} total taint paths")

            return taint_paths

        except Exception as e:
            logger.error(f"Taint analysis failed: {e}", exc_info=True)
            return []

    def _find_node_id_by_name(self, name: str, node_map: dict[str, Node]) -> str | None:
        """Find node ID by function/variable name"""
        import re

        for node_id, node in node_map.items():
            if hasattr(node, "name") and node.name:
                # Try regex match (since names are patterns)
                try:
                    if re.search(name, node.name) or name in node.name:
                        return node_id
                except re.error:
                    # Invalid regex pattern, fall back to simple string match
                    if name in node.name:
                        return node_id
        return None

    def _get_node_name(self, node_id: str, node_map: dict[str, Node]) -> str:
        """Get node name from ID"""
        node = node_map.get(node_id)
        if node and hasattr(node, "name") and node.name:
            return node.name
        return node_id.split(":")[-1] if ":" in node_id else node_id

    def _convert_sources(self) -> dict[str, TaintSource]:
        """
        Convert SourceRule to TaintSource

        Returns:
            Dict mapping pattern → TaintSource
        """
        sources = {}

        for rule in self.source_rules:
            sources[rule.pattern] = TaintSource(
                function_name=rule.pattern,
                description=rule.description,
            )

        return sources

    def _convert_sinks(self) -> dict[str, TaintSink]:
        """
        Convert SinkRule to TaintSink

        Returns:
            Dict mapping pattern → TaintSink
        """
        sinks = {}

        for rule in self.sink_rules:
            sinks[rule.pattern] = TaintSink(
                function_name=rule.pattern,
                description=rule.description,
                severity=rule.severity.value,
            )

        return sinks

    def _convert_sanitizers(self) -> set[str]:
        """
        Convert SanitizerRule to pattern set

        Returns:
            Set of sanitizer patterns
        """
        sanitizers = set()

        for rule in self.sanitizer_rules:
            sanitizers.add(rule.pattern)

        return sanitizers

    def _extract_graph_from_ir(
        self,
        ir_document: IRDocument,
    ) -> tuple[dict[str, list[str]], dict[str, Node]]:
        """
        Extract call graph and node map from IRDocument

        Args:
            ir_document: IR document

        Returns:
            (call_graph, node_map)
            - call_graph: {caller_id: [callee_id, ...]}
            - node_map: {node_id: Node}
        """
        call_graph: dict[str, list[str]] = {}
        node_map: dict[str, Node] = {}

        # Build node map
        for node in ir_document.nodes:
            node_map[node.id] = node

        # Build call graph from edges
        from codegraph_engine.code_foundation.infrastructure.ir.models.core import EdgeKind

        for edge in ir_document.edges:
            # Include CALLS (function calls) and data flow edges (READS, WRITES)
            if edge.kind in (EdgeKind.CALLS, EdgeKind.READS, EdgeKind.WRITES):
                if edge.source_id not in call_graph:
                    call_graph[edge.source_id] = []
                call_graph[edge.source_id].append(edge.target_id)

        logger.debug(f"Extracted graph: {len(node_map)} nodes, {sum(len(v) for v in call_graph.values())} edges")

        return call_graph, node_map

    def get_source_for_pattern(self, pattern: str) -> TaintSource | None:
        """Get TaintSource for a pattern"""
        return self.taint_analyzer.sources.get(pattern)

    def get_sink_for_pattern(self, pattern: str) -> TaintSink | None:
        """Get TaintSink for a pattern"""
        return self.taint_analyzer.sinks.get(pattern)
