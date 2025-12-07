"""
Unified Analysis Builder

통합 분석 빌더: Dataflow + PDG + Taint + Slicing

v2.1에서 추가된 고급 분석 기능을 IR에 통합.
"""

from pathlib import Path

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.analyzers.taint_analyzer import TaintAnalyzer
from src.contexts.code_foundation.infrastructure.ir.models.document import IRDocument
from src.contexts.reasoning_engine.infrastructure.pdg.pdg_builder import PDGBuilder
from src.contexts.reasoning_engine.infrastructure.slicer.slicer import ProgramSlicer, SliceConfig

logger = get_logger(__name__)


class UnifiedAnalyzer:
    """
    통합 분석기

    Dataflow + PDG + Taint + Slicing을 하나로 통합.
    IRDocument를 입력받아 고급 분석 정보를 추가.
    """

    def __init__(
        self,
        enable_pdg: bool = True,
        enable_taint: bool = True,
        enable_slicing: bool = True,
    ):
        """
        Args:
            enable_pdg: PDG 분석 활성화
            enable_taint: Taint 분석 활성화
            enable_slicing: Slicing 활성화 (PDG 필요)
        """
        self.enable_pdg = enable_pdg
        self.enable_taint = enable_taint
        self.enable_slicing = enable_slicing and enable_pdg

        # Analyzers
        self.taint_analyzer = TaintAnalyzer() if enable_taint else None

    def analyze(self, ir_doc: IRDocument, workspace_root: Path | None = None) -> IRDocument:
        """
        IR 문서에 고급 분석 정보 추가.

        Args:
            ir_doc: IR document
            workspace_root: Workspace root (for slicing)

        Returns:
            Enhanced IR document with PDG/Taint/Slicing
        """
        logger.info(f"Starting unified analysis for {ir_doc.repo_id}")

        # Step 1: Build PDG from existing edges
        if self.enable_pdg:
            logger.info("Building PDG...")
            pdg_builder = self._build_pdg_from_ir(ir_doc)

            # Store PDG in IR
            ir_doc.pdg_nodes = list(pdg_builder.nodes.values())
            ir_doc.pdg_edges = pdg_builder.edges
            ir_doc._pdg_index = pdg_builder

            logger.info(f"PDG built: {len(pdg_builder.nodes)} nodes, {len(pdg_builder.edges)} edges")

        # Step 2: Taint analysis
        if self.enable_taint and self.taint_analyzer:
            logger.info("Running taint analysis...")
            findings = self._analyze_taint(ir_doc)
            ir_doc.taint_findings = findings
            logger.info(f"Taint analysis complete: {len(findings)} findings")

        # Step 3: Setup slicer
        if self.enable_slicing and ir_doc._pdg_index:
            logger.info("Setting up program slicer...")
            config = SliceConfig(
                interprocedural=True,
                max_function_depth=2,
                max_depth=100,
            )
            slicer = ProgramSlicer(
                pdg_builder=ir_doc._pdg_index,
                config=config,
                workspace_root=str(workspace_root) if workspace_root else None,
            )
            ir_doc._slicer = slicer
            logger.info("Slicer ready")

        return ir_doc

    def _build_pdg_from_ir(self, ir_doc: IRDocument) -> PDGBuilder:
        """
        IR의 edge 정보로부터 PDG 구축.

        Args:
            ir_doc: IR document

        Returns:
            PDGBuilder instance
        """
        from src.contexts.reasoning_engine.infrastructure.pdg.pdg_builder import DependencyType, PDGNode

        pdg = PDGBuilder()

        logger.info(f"Building PDG from IR: {len(ir_doc.nodes)} nodes, {len(ir_doc.edges)} edges")

        # Convert IR nodes to PDG nodes
        function_count = 0
        for node in ir_doc.nodes:
            # Function/Method만 PDG node로 변환
            logger.debug(f"Processing node: {node.kind.value} | {node.name}")
            if node.kind.value in ["Function", "Method"]:
                function_count += 1
                logger.debug(f"  → Creating PDG node for {node.name}")
                pdg_node = PDGNode(
                    node_id=node.id,
                    statement=node.name or "",
                    line_number=node.span.start_line,
                    defined_vars=[],  # Extract from WRITES edges
                    used_vars=[],  # Extract from READS edges
                    file_path=node.file_path,
                    start_line=node.span.start_line,
                    end_line=node.span.end_line,
                )
                pdg.nodes[node.id] = pdg_node

        logger.info(f"Created {function_count} PDG nodes from {len(ir_doc.nodes)} IR nodes")

        # Convert IR edges to PDG edges
        from src.contexts.reasoning_engine.infrastructure.pdg.pdg_builder import PDGEdge

        for edge in ir_doc.edges:
            # READS/WRITES → DATA dependency
            if edge.kind.value in ["READS", "WRITES"]:
                dep_type = DependencyType.DATA
                pdg_edge = PDGEdge(
                    from_node=edge.source_id,
                    to_node=edge.target_id,
                    dependency_type=dep_type,
                    label=edge.kind.value,
                )
                pdg.add_edge(pdg_edge)

                # Update defined/used vars
                if edge.source_id in pdg.nodes:
                    pdg_node = pdg.nodes[edge.source_id]
                    var_name = edge.attrs.get("var_name", "")

                    if var_name:  # Only if var_name is not empty
                        if edge.kind.value == "WRITES":
                            if var_name not in pdg_node.defined_vars:
                                pdg_node.defined_vars.append(var_name)
                        elif edge.kind.value == "READS":
                            if var_name not in pdg_node.used_vars:
                                pdg_node.used_vars.append(var_name)

            # CALLS → CONTROL dependency (interprocedural)
            elif edge.kind.value == "CALLS":
                dep_type = DependencyType.CONTROL
                pdg_edge = PDGEdge(
                    from_node=edge.source_id,
                    to_node=edge.target_id,
                    dependency_type=dep_type,
                    label="call",
                )
                pdg.add_edge(pdg_edge)

        return pdg

    def _analyze_taint(self, ir_doc: IRDocument) -> list:
        """
        Taint 분석 수행

        Args:
            ir_doc: IR document

        Returns:
            TaintPath 리스트
        """
        taint_findings = []

        # 1. Build call graph from IR edges
        call_graph = {}
        for edge in ir_doc.edges:
            if edge.kind.value == "CALLS":
                caller_id = edge.source_id
                callee_id = edge.target_id
                if caller_id not in call_graph:
                    call_graph[caller_id] = []
                call_graph[caller_id].append(callee_id)

        # 2. Build node map from IR nodes
        node_map = {node.id: node for node in ir_doc.nodes}

        # 3. Run taint analysis if we have data
        if call_graph and node_map:
            try:
                taint_paths = self.taint_analyzer.analyze_taint_flow(call_graph=call_graph, node_map=node_map)

                # Convert to TaintFinding format (if IRDocument expects different format)
                for path in taint_paths:
                    taint_findings.append(
                        {
                            "source": path.source,
                            "sink": path.sink,
                            "path": path.path,
                            "is_sanitized": path.is_sanitized,
                        }
                    )

            except Exception as e:
                logger.warning(f"Taint analysis failed: {e}")

        return taint_findings


def enhance_ir_with_advanced_analysis(
    ir_doc: IRDocument,
    workspace_root: Path | None = None,
    enable_pdg: bool = True,
    enable_taint: bool = True,
    enable_slicing: bool = True,
) -> IRDocument:
    """
    Helper function: IR에 고급 분석 추가.

    Args:
        ir_doc: IR document
        workspace_root: Workspace root
        enable_pdg: Enable PDG
        enable_taint: Enable taint analysis
        enable_slicing: Enable slicing

    Returns:
        Enhanced IR document
    """
    analyzer = UnifiedAnalyzer(
        enable_pdg=enable_pdg,
        enable_taint=enable_taint,
        enable_slicing=enable_slicing,
    )

    return analyzer.analyze(ir_doc, workspace_root)
