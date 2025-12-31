"""
Unified Analysis Builder

통합 분석 빌더: Dataflow + PDG + Taint + Slicing

v2.1에서 추가된 고급 분석 기능을 IR에 통합.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_shared.common.logging_config import BatchLogger, is_debug_enabled
from codegraph_engine.code_foundation.domain.query.types import TaintMode
from codegraph_engine.code_foundation.infrastructure.analyzers.taint_analyzer import TaintAnalyzer
from codegraph_engine.code_foundation.infrastructure.ir.models.core import EdgeKind
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument

# Hexagonal: Optional import for reasoning_engine (graceful degradation)
# PDGBuilder and ProgramSlicer are optional dependencies
try:
    from codegraph_engine.reasoning_engine.infrastructure.pdg.pdg_builder import PDGBuilder

    _PDG_AVAILABLE = True
except ImportError:
    PDGBuilder = None  # type: ignore
    _PDG_AVAILABLE = False

# Inter-procedural analysis (context-sensitive slicing)
try:
    from codegraph_engine.reasoning_engine.infrastructure.slicer.interprocedural import (
        InterproceduralAnalyzer,
        FunctionContext,
        CallSite,
    )

    _INTERPROCEDURAL_AVAILABLE = True
except ImportError:
    InterproceduralAnalyzer = None  # type: ignore
    _INTERPROCEDURAL_AVAILABLE = False

# Alias analysis (pointer/reference tracking)
try:
    from codegraph_engine.code_foundation.infrastructure.analyzers.alias_analyzer import (
        AliasAnalyzer,
        AliasType,
    )

    _ALIAS_AVAILABLE = True
except ImportError:
    AliasAnalyzer = None  # type: ignore
    _ALIAS_AVAILABLE = False

# Inter-procedural taint analysis (cross-function tracking)
try:
    from codegraph_engine.code_foundation.infrastructure.analyzers.interprocedural_taint import (
        InterproceduralTaintAnalyzer,
    )

    _INTERPROCEDURAL_TAINT_AVAILABLE = True
except ImportError:
    InterproceduralTaintAnalyzer = None  # type: ignore
    _INTERPROCEDURAL_TAINT_AVAILABLE = False

# Rust native L6 analysis (10-20x faster)
try:
    from codegraph_engine.reasoning_engine.infrastructure.engine.native_analysis import (
        is_native_available,
        analyze_taint_native,
        build_pdg_native,
        backward_slice_native,
        forward_slice_native,
    )

    _RUST_NATIVE_AVAILABLE = is_native_available()
except ImportError:
    _RUST_NATIVE_AVAILABLE = False
    analyze_taint_native = None  # type: ignore
    build_pdg_native = None  # type: ignore

# Lazy import to avoid PermissionError on slicer module
if TYPE_CHECKING:
    from codegraph_engine.reasoning_engine.infrastructure.slicer.slicer import ProgramSlicer
    from codegraph_shared.kernel.slice.models import SliceConfig

logger = get_logger(__name__)


class UnifiedAnalyzer:
    """
    통합 분석기

    Dataflow + PDG + Taint + Slicing을 하나로 통합.
    IRDocument를 입력받아 고급 분석 정보를 추가.

    Taint Modes:
    - basic: Call graph 기반 (default)
    - path_sensitive: Path-sensitive 분석 (조건부 sanitization)
    - full: Interprocedural + Severity 판단
    - field_sensitive: Object field/array element tracking
    """

    def __init__(
        self,
        enable_pdg: bool = True,
        enable_taint: bool = True,
        enable_slicing: bool = True,
        taint_mode: str | TaintMode = TaintMode.BASIC,
        profiler=None,
        use_native: bool = True,
        enable_interprocedural: bool = True,
        enable_alias: bool = True,
    ):
        """
        Args:
            enable_pdg: PDG 분석 활성화
            enable_taint: Taint 분석 활성화
            enable_slicing: Slicing 활성화 (PDG 필요)
            taint_mode: Taint 분석 모드 (TaintMode enum 또는 문자열)
                - TaintMode.BASIC / "basic": Call graph 기반 (default)
                - TaintMode.PATH_SENSITIVE / "path_sensitive": CFG-aware
                - TaintMode.FIELD_SENSITIVE / "field_sensitive": Object tracking
                - TaintMode.FULL / "full": Deprecated → PATH_SENSITIVE
            profiler: Optional profiler for sub-step timing
            use_native: Use Rust native analysis (10-20x faster)
            enable_interprocedural: Enable inter-procedural analysis (cross-function)
            enable_alias: Enable alias analysis (pointer/reference tracking)

        Raises:
            ValueError: Invalid taint_mode
        """
        self.enable_pdg = enable_pdg
        self.enable_taint = enable_taint
        self.enable_slicing = enable_slicing and enable_pdg
        self.profiler = profiler

        # Advanced analysis flags
        self.enable_interprocedural = enable_interprocedural and _INTERPROCEDURAL_AVAILABLE
        self.enable_alias = enable_alias and _ALIAS_AVAILABLE

        # Log advanced analysis availability
        if enable_interprocedural and not _INTERPROCEDURAL_AVAILABLE:
            logger.warning("Inter-procedural analysis requested but not available")
        if enable_alias and not _ALIAS_AVAILABLE:
            logger.warning("Alias analysis requested but not available")

        # Rust native acceleration (if available)
        self.use_native = use_native and _RUST_NATIVE_AVAILABLE
        if self.use_native:
            logger.info("Using Rust native L6 analysis (10-20x faster)")
        elif use_native and not _RUST_NATIVE_AVAILABLE:
            logger.warning(
                "Rust native L6 analysis requested but not available. "
                "Build with: cd packages/codegraph-rust && maturin develop"
            )

        # Normalize taint_mode (case-insensitive string support)
        if isinstance(taint_mode, str):
            self._taint_mode = TaintMode.from_string(taint_mode)
        else:
            self._taint_mode = taint_mode

        # Initialize analyzers
        self.taint_analyzer = self._create_taint_analyzer(self._taint_mode) if enable_taint else None
        self.alias_analyzer = AliasAnalyzer() if self.enable_alias else None
        self.interprocedural_analyzer = None  # Initialized after PDG build

    @property
    def taint_mode(self) -> str:
        """Return taint_mode as string for backward compatibility."""
        return self._taint_mode.value

    def _create_taint_analyzer(self, mode: TaintMode):
        """
        Taint analyzer 생성

        Args:
            mode: TaintMode enum

        Returns:
            Appropriate taint analyzer
        """
        if mode == TaintMode.PATH_SENSITIVE:
            try:
                from codegraph_engine.code_foundation.infrastructure.analyzers.path_sensitive_taint import (
                    PathSensitiveTaintAnalyzer,
                )

                logger.info("Using PathSensitiveTaintAnalyzer")
                return PathSensitiveTaintAnalyzer
            except ImportError:
                logger.warning("PathSensitiveTaintAnalyzer not available, falling back to basic")
                return TaintAnalyzer()

        elif mode == TaintMode.FULL:
            # RFC-021 Phase 3: FullTaintEngine deprecated
            logger.warning(
                "taint_mode='full' is deprecated. "
                "Use QueryEngine.execute_flow(mode='full') instead. "
                "Falling back to path_sensitive mode."
            )
            try:
                from codegraph_engine.code_foundation.infrastructure.analyzers.path_sensitive_taint import (
                    PathSensitiveTaintAnalyzer,
                )

                return PathSensitiveTaintAnalyzer
            except ImportError:
                return TaintAnalyzer()

        elif mode == TaintMode.FIELD_SENSITIVE:
            try:
                from codegraph_engine.code_foundation.infrastructure.analyzers.field_sensitive_taint import (
                    FieldSensitiveTaintAnalyzer,
                )

                logger.info("Using FieldSensitiveTaintAnalyzer")
                return FieldSensitiveTaintAnalyzer
            except ImportError:
                logger.warning("FieldSensitiveTaintAnalyzer not available, falling back to basic")
                return TaintAnalyzer()

        else:  # TaintMode.BASIC
            logger.info("Using basic TaintAnalyzer")
            return TaintAnalyzer()

    def __init_stats(self):
        """Initialize stats counters."""
        self._stats = {
            "files_analyzed": 0,
            "pdg_nodes": 0,
            "pdg_edges": 0,
            "taint_findings": 0,
            "taint_mode": self._taint_mode.value,
            "interprocedural_functions": 0,
            "alias_count": 0,
        }

    def get_stats(self) -> dict[str, int | str]:
        """
        Get statistics from the last analysis run.

        Returns:
            Dictionary with PDG node/edge counts and taint findings.
        """
        if not hasattr(self, "_stats"):
            self.__init_stats()
        return self._stats.copy()

    def analyze(self, ir_doc: IRDocument, workspace_root: Path | None = None) -> IRDocument:
        """
        IR 문서에 고급 분석 정보 추가.

        Args:
            ir_doc: IR document
            workspace_root: Workspace root (for slicing)

        Returns:
            Enhanced IR document with PDG/Taint/Slicing
        """
        # Initialize stats if not present
        if not hasattr(self, "_stats"):
            self.__init_stats()

        logger.info(f"Starting unified analysis for {ir_doc.repo_id}")
        self._stats["files_analyzed"] += 1

        # Step 1: Build PDG from existing edges
        # NOTE: Python PDG is faster than Rust PDG due to data conversion overhead
        # Rust native is only used for Taint analysis, not PDG building
        if self.enable_pdg:
            logger.info("Building PDG (Python)...")
            pdg_builder = self._build_pdg_from_ir(ir_doc)

            # Store PDG in IR
            ir_doc.pdg_nodes = list(pdg_builder.nodes.values())
            ir_doc.pdg_edges = pdg_builder.edges
            ir_doc._pdg_index = pdg_builder

            # Update stats
            self._stats["pdg_nodes"] += len(pdg_builder.nodes)
            self._stats["pdg_edges"] += len(pdg_builder.edges)

            logger.info(f"PDG built: {len(pdg_builder.nodes)} nodes, {len(pdg_builder.edges)} edges")

            # Step 1.5: Inter-procedural analysis (context-sensitive)
            if self.enable_interprocedural and pdg_builder:
                logger.info("Running inter-procedural analysis...")
                self._run_interprocedural_analysis(ir_doc, pdg_builder)

        # Step 1.6: Alias analysis (pointer/reference tracking)
        if self.enable_alias and self.alias_analyzer:
            logger.info("Running alias analysis...")
            self._run_alias_analysis(ir_doc)

        # Step 2: Taint analysis
        if self.enable_taint:
            if self.profiler:
                from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import IRLayer

                with self.profiler.phase(IRLayer.ANALYSIS_INDEXES_TAINT):
                    if self.use_native:
                        logger.info("Running taint analysis (Rust native)...")
                        findings = self._analyze_taint_native(ir_doc)
                    else:
                        logger.info("Running taint analysis (Python)...")
                        findings = self._analyze_taint(ir_doc)
            else:
                if self.use_native:
                    logger.info("Running taint analysis (Rust native)...")
                    findings = self._analyze_taint_native(ir_doc)
                else:
                    logger.info("Running taint analysis (Python)...")
                    findings = self._analyze_taint(ir_doc)

            ir_doc.taint_findings = findings
            self._stats["taint_findings"] += len(findings)
            logger.info(f"Taint analysis complete: {len(findings)} findings")

        # Step 3: Setup slicer
        if self.enable_slicing and ir_doc._pdg_index:
            if self.profiler:
                from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import IRLayer

                with self.profiler.phase(IRLayer.ANALYSIS_INDEXES_SLICER):
                    logger.info("Setting up program slicer...")
                    slicer = self._setup_slicer(ir_doc, workspace_root)
            else:
                logger.info("Setting up program slicer...")
                slicer = self._setup_slicer(ir_doc, workspace_root)

            ir_doc._slicer = slicer
            logger.info("Slicer ready")

        return ir_doc

    def _setup_slicer(self, ir_doc: IRDocument, workspace_root: Path | None):
        """Setup program slicer (extracted for profiling)."""
        try:
            # Hexagonal: Optional import (graceful degradation)
            from codegraph_engine.reasoning_engine.infrastructure.slicer.slicer import ProgramSlicer
            from codegraph_shared.kernel.slice.models import SliceConfig

            config = SliceConfig(
                interprocedural=True,
                max_function_depth=2,
                max_depth=100,
            )
            return ProgramSlicer(
                pdg_builder=ir_doc._pdg_index,
                config=config,
                workspace_root=str(workspace_root) if workspace_root else None,
            )
        except ImportError:
            logger.warning("ProgramSlicer not available - reasoning_engine not installed")
            return None

    def _build_pdg_from_ir(self, ir_doc: IRDocument) -> PDGBuilder:
        """
        IR의 edge 정보로부터 PDG 구축.

        Args:
            ir_doc: IR document

        Returns:
            PDGBuilder instance
        """
        from codegraph_shared.kernel.pdg.models import DependencyType, PDGNode

        pdg = PDGBuilder()

        logger.info(f"Building PDG from IR: {len(ir_doc.nodes)} nodes, {len(ir_doc.edges)} edges")

        # Phase 1: Collect nodes/edges (ANALYSIS_INDEXES_COLLECT)
        if self.profiler:
            from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import IRLayer

            with self.profiler.phase(IRLayer.ANALYSIS_INDEXES_COLLECT):
                function_nodes = [n for n in ir_doc.nodes if n.kind.value in ["Function", "Method"]]
                relevant_edges = [
                    e for e in ir_doc.edges if e.kind in (EdgeKind.READS, EdgeKind.WRITES, EdgeKind.CALLS)
                ]
        else:
            function_nodes = [n for n in ir_doc.nodes if n.kind.value in ["Function", "Method"]]
            relevant_edges = [e for e in ir_doc.edges if e.kind in (EdgeKind.READS, EdgeKind.WRITES, EdgeKind.CALLS)]

        # Phase 2: Convert IR nodes to PDG nodes (ANALYSIS_INDEXES_PDG_NODES)
        # SOTA: 배치 로깅 (1000개 → 1개 요약)
        if self.profiler:
            from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import IRLayer

            with self.profiler.phase(IRLayer.ANALYSIS_INDEXES_PDG_NODES):
                with BatchLogger(logger, "pdg_node_conversion") as batch:
                    for node in function_nodes:
                        pdg_node = PDGNode(
                            node_id=node.id,
                            statement=node.name or "",
                            line_number=node.span.start_line,
                            defined_vars=set(),
                            used_vars=set(),
                            file_path=node.file_path,
                            start_line=node.span.start_line,
                            end_line=node.span.end_line,
                        )
                        pdg.nodes[node.id] = pdg_node

                        # 배치 레코드 (로그 안찍음, 메모리만)
                        if is_debug_enabled():
                            batch.record(node_id=node.id, kind=node.kind.value, name=node.name)
        else:
            with BatchLogger(logger, "pdg_node_conversion") as batch:
                for node in function_nodes:
                    pdg_node = PDGNode(
                        node_id=node.id,
                        statement=node.name or "",
                        line_number=node.span.start_line,
                        defined_vars=set(),
                        used_vars=set(),
                        file_path=node.file_path,
                        start_line=node.span.start_line,
                        end_line=node.span.end_line,
                    )
                    pdg.nodes[node.id] = pdg_node

                    if is_debug_enabled():
                        batch.record(node_id=node.id, kind=node.kind.value, name=node.name)

        logger.info(f"Created {len(function_nodes)} PDG nodes from {len(ir_doc.nodes)} IR nodes")

        # Phase 3: Convert IR edges to PDG edges (ANALYSIS_INDEXES_PDG_EDGES)
        if self.profiler:
            from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import IRLayer

            with self.profiler.phase(IRLayer.ANALYSIS_INDEXES_PDG_EDGES):
                self._convert_edges_to_pdg(relevant_edges, pdg)
        else:
            self._convert_edges_to_pdg(relevant_edges, pdg)

        return pdg

    def _convert_edges_to_pdg(self, edges, pdg):
        """Convert IR edges to PDG edges (extracted for profiling)."""
        from codegraph_shared.kernel.pdg.models import PDGEdge, DependencyType

        for edge in edges:
            # READS/WRITES → DATA dependency
            if edge.kind in (EdgeKind.READS, EdgeKind.WRITES):
                dep_type = DependencyType.DATA
                pdg_edge = PDGEdge(
                    from_node=edge.source_id,
                    to_node=edge.target_id,
                    dependency_type=dep_type,
                    label=edge.kind.value,
                )
                pdg.add_edge(pdg_edge)

                # Update defined/used vars (SOTA: O(1) set add)
                if edge.source_id in pdg.nodes:
                    pdg_node = pdg.nodes[edge.source_id]
                    var_name = edge.attrs.get("var_name", "")

                    if var_name:
                        if edge.kind == EdgeKind.WRITES:
                            pdg_node.defined_vars.add(var_name)
                        elif edge.kind == EdgeKind.READS:
                            pdg_node.used_vars.add(var_name)

            # CALLS → CONTROL dependency (interprocedural)
            elif edge.kind == EdgeKind.CALLS:
                dep_type = DependencyType.CONTROL
                pdg_edge = PDGEdge(
                    from_node=edge.source_id,
                    to_node=edge.target_id,
                    dependency_type=dep_type,
                    label="call",
                )
                pdg.add_edge(pdg_edge)

    def _analyze_taint(self, ir_doc: IRDocument) -> list:
        """
        Taint 분석 수행 (mode에 따라 다른 analyzer 사용)

        Args:
            ir_doc: IR document

        Returns:
            TaintPath 리스트
        """
        taint_findings = []

        # 1. Build call graph from IR edges
        call_graph = {}
        for edge in ir_doc.edges:
            if edge.kind == EdgeKind.CALLS:
                caller_id = edge.source_id
                callee_id = edge.target_id
                if caller_id not in call_graph:
                    call_graph[caller_id] = []
                call_graph[caller_id].append(callee_id)

        # 2. Build node map from IR nodes
        node_map = {node.id: node for node in ir_doc.nodes}

        # 3. Run taint analysis based on mode
        if call_graph and node_map:
            try:
                # Advanced analyzers (path_sensitive, field_sensitive, full)
                # Note: "full" mode now falls back to path_sensitive (RFC-021)
                if self.taint_mode in ["path_sensitive", "field_sensitive", "full"]:
                    taint_findings = self._analyze_advanced_taint(ir_doc, call_graph, node_map)

                # Basic TaintAnalyzer
                else:
                    taint_paths = self.taint_analyzer.analyze_taint_flow(
                        call_graph=call_graph,
                        node_map=node_map,
                    )
                    # Convert to Vulnerability format
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
                logger.warning(f"Taint analysis failed: {e}", exc_info=True)

        return taint_findings

    def _analyze_advanced_taint(
        self,
        ir_doc: IRDocument,
        call_graph: dict,
        node_map: dict,
    ) -> list[dict]:
        """
        Advanced taint analysis (path-sensitive or field-sensitive)

        Args:
            ir_doc: IR document with CFG/DFG
            call_graph: Call graph
            node_map: Node map

        Returns:
            Taint findings
        """
        findings = []

        # Need CFG for advanced analysis
        if not ir_doc.cfg_blocks:
            logger.warning("No CFG available for advanced taint analysis, falling back to basic")
            return findings

        try:
            # Extract sources and sinks from node map
            sources = set()
            sinks = set()

            for node_id, node in node_map.items():
                if hasattr(node, "name") and node.name:
                    name_lower = node.name.lower()
                    # Source detection
                    if any(s in name_lower for s in ["input", "request", "argv", "environ"]):
                        sources.add(node.name)
                    # Sink detection
                    if any(s in name_lower for s in ["execute", "eval", "exec", "system"]):
                        sinks.add(node_id)

            if not sources or not sinks:
                logger.info("No sources or sinks found for advanced taint analysis")
                return findings

            # Create CFG/DFG
            cfg = self._create_cfg_for_taint(ir_doc)
            dfg = self._create_dfg_for_taint(ir_doc)

            # Create analyzer with CFG/DFG
            if self.taint_mode == "path_sensitive":
                # taint_analyzer is PathSensitiveTaintAnalyzer class
                if isinstance(self.taint_analyzer, type):
                    from codegraph_engine.code_foundation.infrastructure.analyzers.path_sensitive_taint import (
                        create_path_sensitive_analyzer,
                    )

                    analyzer = create_path_sensitive_analyzer(cfg, dfg)
                    vulnerabilities = analyzer.analyze(sources=sources, sinks=sinks)

                    # Convert to standard format
                    for vuln in vulnerabilities:
                        findings.append(
                            {
                                "sink": vuln["sink"],
                                "tainted_vars": list(vuln["tainted_vars"]),
                                "path": vuln["path"],
                                "is_sanitized": False,
                            }
                        )

            elif self.taint_mode == "field_sensitive":
                # taint_analyzer is FieldSensitiveTaintAnalyzer class
                if isinstance(self.taint_analyzer, type):
                    analyzer = self.taint_analyzer(cfg, dfg)

                    # Convert sources to field format
                    source_fields = dict.fromkeys(sources, (None, None))

                    vulnerabilities = analyzer.analyze(sources=source_fields, sinks=sinks)

                    # Convert to standard format
                    for vuln in vulnerabilities:
                        findings.append(
                            {
                                "sink": vuln["sink"],
                                "tainted_var": vuln["tainted_var"],
                                "tainted_field": vuln.get("tainted_field"),
                                "severity": vuln["severity"],
                                "is_sanitized": False,
                            }
                        )

        except Exception as e:
            logger.warning(f"Advanced taint analysis failed: {e}", exc_info=True)

        return findings

    def _build_pdg_native(self, ir_doc: IRDocument) -> dict:
        """
        Build PDG using Rust native engine (5-10x faster).

        Args:
            ir_doc: IR document

        Returns:
            PDG stats dict: {node_count, edge_count, control_edges, data_edges}
        """
        # Collect function nodes
        function_nodes = [n for n in ir_doc.nodes if n.kind.value in ["Function", "Method"]]

        # Convert to Rust format
        nodes = []
        for node in function_nodes:
            nodes.append(
                {
                    "id": node.id,
                    "statement": node.name or "",
                    "line_number": node.span.start_line,
                    "defined_vars": [],
                    "used_vars": [],
                }
            )

        # Collect CFG edges
        cfg_edges = []
        for edge in ir_doc.cfg_edges:
            # Handle both dict and object formats
            if isinstance(edge, dict):
                cfg_edges.append(
                    {
                        "source": edge.get("source_block_id", ""),
                        "target": edge.get("target_block_id", ""),
                        "edge_type": str(edge.get("edge_type", "UNCONDITIONAL")),
                    }
                )
            else:
                cfg_edges.append(
                    {
                        "source": edge.source_block_id,
                        "target": edge.target_block_id,
                        "edge_type": edge.edge_type.value if hasattr(edge.edge_type, "value") else str(edge.edge_type),
                    }
                )

        # Collect DFG edges from IR edges
        dfg_edges = []
        for edge in ir_doc.edges:
            if edge.kind in (EdgeKind.READS, EdgeKind.WRITES):
                dfg_edges.append(
                    {
                        "from": edge.source_id,
                        "to": edge.target_id,
                        "variable": edge.attrs.get("var_name", ""),
                    }
                )

        # Call Rust native
        try:
            return build_pdg_native(
                function_id=ir_doc.repo_id,
                nodes=nodes,
                cfg_edges=cfg_edges,
                dfg_edges=dfg_edges,
            )
        except Exception as e:
            logger.warning(f"Rust native PDG build failed: {e}, falling back to Python")
            return {"node_count": 0, "edge_count": 0, "control_edges": 0, "data_edges": 0}

    def _analyze_taint_native(self, ir_doc: IRDocument) -> list:
        """
        Analyze taint flow using Rust native engine (10-20x faster).

        Args:
            ir_doc: IR document

        Returns:
            List of taint findings
        """
        # Build call graph from IR edges
        call_graph = []
        node_map = {node.id: node for node in ir_doc.nodes}

        # Group callees by caller
        callees_by_caller: dict[str, list[str]] = {}
        for edge in ir_doc.edges:
            if edge.kind == EdgeKind.CALLS:
                caller_id = edge.source_id
                callee_id = edge.target_id
                if caller_id not in callees_by_caller:
                    callees_by_caller[caller_id] = []
                callees_by_caller[caller_id].append(callee_id)

        # Convert to Rust format
        for node_id, callees in callees_by_caller.items():
            node = node_map.get(node_id)
            call_graph.append(
                {
                    "id": node_id,
                    "name": node.name if node else node_id,
                    "callees": callees,
                }
            )

        # Add nodes without outgoing calls
        for node in ir_doc.nodes:
            if node.id not in callees_by_caller:
                call_graph.append(
                    {
                        "id": node.id,
                        "name": node.name or node.id,
                        "callees": [],
                    }
                )

        if not call_graph:
            return []

        # Call Rust native
        try:
            taint_paths = analyze_taint_native(call_graph)

            # Convert to standard format
            findings = []
            for path in taint_paths:
                findings.append(
                    {
                        "source": path.get("source", ""),
                        "sink": path.get("sink", ""),
                        "path": path.get("path", []),
                        "is_sanitized": path.get("is_sanitized", False),
                        "severity": path.get("severity", "medium"),
                    }
                )
            return findings
        except Exception as e:
            logger.warning(f"Rust native taint analysis failed: {e}, falling back to Python")
            return self._analyze_taint(ir_doc)

    def _create_cfg_for_taint(self, ir_doc: IRDocument):
        """Create CFG object for taint analysis"""

        # Mock CFG with necessary attributes
        class MockCFG:
            def __init__(self, blocks, edges):
                self.entry = blocks[0].id if blocks else "entry"
                self.nodes = {block.id: block for block in blocks}
                self.edges = edges
                self.successors = {}
                self.predecessors = {}

                # Build successor/predecessor maps
                for edge in edges:
                    src = edge.source_block_id
                    tgt = edge.target_block_id
                    if src not in self.successors:
                        self.successors[src] = []
                    self.successors[src].append(tgt)

                    if tgt not in self.predecessors:
                        self.predecessors[tgt] = []
                    self.predecessors[tgt].append(src)

        return MockCFG(ir_doc.cfg_blocks, ir_doc.cfg_edges)

    def _create_dfg_for_taint(self, ir_doc: IRDocument):
        """Create DFG object for taint analysis"""

        # Mock DFG with necessary attributes
        class MockDFG:
            def __init__(self, snapshot):
                self.snapshot = snapshot
                self.variables = snapshot.variables if snapshot else []

        return MockDFG(ir_doc.dfg_snapshot)

    def _run_interprocedural_analysis(self, ir_doc: IRDocument, pdg_builder) -> None:
        """
        Run inter-procedural analysis for context-sensitive slicing.

        Args:
            ir_doc: IR document
            pdg_builder: PDG builder instance
        """
        if not _INTERPROCEDURAL_AVAILABLE or not InterproceduralAnalyzer:
            return

        try:
            # Initialize interprocedural analyzer with PDG
            self.interprocedural_analyzer = InterproceduralAnalyzer(pdg_builder)

            # Build function contexts from IR nodes
            function_contexts = {}
            for node in ir_doc.nodes:
                if node.kind.value in ["Function", "Method"]:
                    # Find call sites within this function
                    call_sites = []
                    for edge in ir_doc.edges:
                        if edge.kind == EdgeKind.CALLS and edge.source_id == node.id:
                            call_site = CallSite(
                                caller_node_id=edge.source_id,
                                callee_function=edge.target_id,
                                actual_params=[],  # TODO: Extract from IR
                                return_node_id=None,
                            )
                            call_sites.append(call_site)

                    # Create function context
                    context = FunctionContext(
                        function_name=node.name or node.id,
                        entry_node_id=node.id,
                        exit_node_id=node.id,  # Simplified
                        formal_params=[],  # TODO: Extract from IR
                        local_nodes={node.id},
                        call_sites=call_sites,
                    )
                    function_contexts[node.name or node.id] = context

            # Build call graph
            if function_contexts:
                self.interprocedural_analyzer.build_call_graph(function_contexts)
                logger.info(f"Inter-procedural: {len(function_contexts)} functions analyzed")

                # Store in IR document
                ir_doc._interprocedural_analyzer = self.interprocedural_analyzer
                self._stats["interprocedural_functions"] = len(function_contexts)

        except Exception as e:
            logger.warning(f"Inter-procedural analysis failed: {e}", exc_info=True)

    def _run_alias_analysis(self, ir_doc: IRDocument) -> None:
        """
        Run alias analysis for pointer/reference tracking.

        Args:
            ir_doc: IR document
        """
        if not self.alias_analyzer:
            return

        try:
            alias_count = 0

            # Extract assignment edges for alias detection
            for edge in ir_doc.edges:
                if edge.kind == EdgeKind.WRITES:
                    # Direct assignment: target = source
                    source_id = edge.source_id
                    target_id = edge.target_id

                    # Add alias relationship
                    self.alias_analyzer.add_alias(
                        source=source_id,
                        target=target_id,
                        alias_type=AliasType.DIRECT,
                        is_must=True,
                    )
                    alias_count += 1

                elif edge.kind == EdgeKind.READS:
                    # Potential alias through read
                    var_name = edge.attrs.get("var_name", "")
                    if var_name:
                        # Track variable aliases
                        self.alias_analyzer.add_alias(
                            source=var_name,
                            target=edge.target_id,
                            alias_type=AliasType.DIRECT,
                            is_must=False,  # May-alias
                        )
                        alias_count += 1

            logger.info(f"Alias analysis: {alias_count} aliases tracked")

            # Store in IR document
            ir_doc._alias_analyzer = self.alias_analyzer
            self._stats["alias_count"] = alias_count

        except Exception as e:
            logger.warning(f"Alias analysis failed: {e}", exc_info=True)

    def _analyze_taint_with_alias(self, ir_doc: IRDocument) -> list:
        """
        Taint analysis enhanced with alias information.

        Uses alias analysis to track taint through pointer/reference relationships.
        """
        findings = self._analyze_taint(ir_doc)

        if not self.alias_analyzer or not findings:
            return findings

        # Enhance findings with alias information
        enhanced_findings = []
        for finding in findings:
            # Check if source/sink have aliases
            source = finding.get("source", "")
            sink = finding.get("sink", "")

            # Get all aliases for source (may propagate taint)
            source_aliases = (
                self.alias_analyzer.get_aliases(source) if hasattr(self.alias_analyzer, "get_aliases") else set()
            )
            sink_aliases = (
                self.alias_analyzer.get_aliases(sink) if hasattr(self.alias_analyzer, "get_aliases") else set()
            )

            # Add alias info to finding
            enhanced_finding = finding.copy()
            enhanced_finding["source_aliases"] = list(source_aliases)
            enhanced_finding["sink_aliases"] = list(sink_aliases)
            enhanced_finding["alias_enhanced"] = bool(source_aliases or sink_aliases)

            enhanced_findings.append(enhanced_finding)

        return enhanced_findings


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
