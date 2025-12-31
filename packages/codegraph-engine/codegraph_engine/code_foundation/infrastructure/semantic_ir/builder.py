"""
Semantic IR Builder

Orchestrates all semantic IR builders (Type, Signature, BFG, CFG, DFG).

Phase 1: Type + Signature
Phase 2: + BFG (Basic Blocks) + CFG (Control Flow Edges)
Phase 3: + DFG
"""

from typing import TYPE_CHECKING, Protocol

from codegraph_shared.common.observability import get_logger, record_counter, record_histogram
from codegraph_engine.code_foundation.infrastructure.dfg.builder import DfgBuilder
from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument
from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.builder import BfgBuilder
from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.builder import CfgBuilder
from codegraph_engine.code_foundation.infrastructure.semantic_ir.config import (
    _DEBUG_ENABLED,
    BODY_HASH_LENGTH,
    BODY_HASH_PREFIX,
    INCREMENTAL_UPDATE_THRESHOLD,
)
from codegraph_engine.code_foundation.infrastructure.semantic_ir.context import (
    SemanticIndex,
    SemanticIrSnapshot,
)
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.builder import ExpressionBuilder
from codegraph_engine.code_foundation.infrastructure.semantic_ir.id_utils import (
    convert_cfg_id_to_bfg_id,
    extract_file_path,
)
from codegraph_engine.code_foundation.infrastructure.semantic_ir.performance_monitor import PerformanceMonitor
from codegraph_engine.code_foundation.infrastructure.semantic_ir.signature.builder import SignatureIrBuilder
from codegraph_engine.code_foundation.infrastructure.semantic_ir.type_linker import TypeLinker
from codegraph_engine.code_foundation.infrastructure.semantic_ir.typing.builder import TypeIrBuilder
from codegraph_engine.code_foundation.domain.type_inference.config import LocalFlowConfig
from codegraph_engine.code_foundation.infrastructure.type_inference.local_flow_inferencer import LocalFlowTypeInferencer

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.semantic_ir.mode import SemanticIrBuildMode
    from codegraph_engine.code_foundation.domain.semantic_ir.ports import BodyHashPort
    from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig  # RFC-036
    from codegraph_engine.code_foundation.infrastructure.parsing import AstTree, SourceFile
    from codegraph_engine.code_foundation.infrastructure.profiling import Profiler


# ============================================================
# Protocol (Interface)
# ============================================================


class SemanticIrBuilder(Protocol):
    """
    Semantic IR builder interface.

    Converts Structural IR → Semantic IR.
    """

    def build_full(self, ir_doc: IRDocument) -> tuple[SemanticIrSnapshot, SemanticIndex]:
        """
        Build complete semantic IR from structural IR.

        Args:
            ir_doc: Structural IR document

        Returns:
            (semantic_snapshot, semantic_index)
        """
        ...

    def apply_delta(
        self,
        ir_doc: IRDocument,
        existing_snapshot: SemanticIrSnapshot,
        existing_index: SemanticIndex,
    ) -> tuple[SemanticIrSnapshot, SemanticIndex]:
        """
        Apply incremental changes to semantic IR.

        Args:
            ir_doc: Updated structural IR
            existing_snapshot: Previous semantic snapshot
            existing_index: Previous semantic index

        Returns:
            (new_snapshot, new_index)
        """
        ...


# ============================================================
# Default Implementation
# ============================================================


class DefaultSemanticIrBuilder:
    """
    Default semantic IR builder implementation.

    Orchestrates type, signature, BFG, CFG, and DFG builders.

    Phase 1: Type + Signature only
    Phase 2: + BFG (Basic Blocks) + CFG (Control Flow Edges)
    Phase 3: + DFG
    """

    def __init__(
        self,
        type_builder: TypeIrBuilder | None = None,
        signature_builder: SignatureIrBuilder | None = None,
        bfg_builder: BfgBuilder | None = None,
        cfg_builder: CfgBuilder | None = None,
        expression_builder: ExpressionBuilder | None = None,
        dfg_builder: DfgBuilder | None = None,
        enable_performance_monitoring: bool = False,
        profiler: "Profiler | None" = None,
        body_hash_port: "BodyHashPort | None" = None,  # ⭐ SOTA: Hexagonal Architecture
        local_flow_type_inferencer: LocalFlowTypeInferencer | None = None,
        local_flow_config: LocalFlowConfig | None = None,
    ):
        """
        Initialize with sub-builders.

        SOTA Enhancement: Hexagonal Architecture with BodyHashPort
        - Domain (this class) depends on Port (interface)
        - Adapter (SHA256BodyHashAdapter) implements Port
        - Clean separation: Domain ← Port ← Infrastructure

        Args:
            type_builder: Type system builder
            signature_builder: Signature builder
            bfg_builder: BFG builder (basic blocks)
            cfg_builder: CFG builder (control flow edges)
            expression_builder: Expression builder (for DFG)
            dfg_builder: DFG builder
            enable_performance_monitoring: Enable detailed performance tracking
            profiler: Optional profiler for benchmarking
            body_hash_port: Port for computing body hashes (Hexagonal Architecture)
        """
        self.logger = get_logger(__name__)
        self.type_builder = type_builder or TypeIrBuilder()
        self.signature_builder = signature_builder or SignatureIrBuilder()
        self.bfg_builder = bfg_builder or BfgBuilder()
        self.cfg_builder = cfg_builder or CfgBuilder()
        self.expression_builder = expression_builder or ExpressionBuilder()

        # Initialize DFG builder
        if dfg_builder is None:
            dfg_builder = DfgBuilder()
        self.dfg_builder = dfg_builder
        # Hexagonal/DI: allow injection for testing/experimentation
        # SOTA: Config-based initialization (no hardcoding)
        if local_flow_type_inferencer:
            self._local_flow_type_inferencer = local_flow_type_inferencer
        else:
            config = local_flow_config or LocalFlowConfig()
            self._local_flow_type_inferencer = LocalFlowTypeInferencer(config=config)

        # Initialize performance monitor
        self.enable_performance_monitoring = enable_performance_monitoring
        self._performance_monitor = (
            PerformanceMonitor(enable_memory_tracking=True) if enable_performance_monitoring else None
        )

        # Profiler (optional, for benchmarking)
        self._profiler = profiler

        # ⭐ SOTA: Hexagonal Architecture - Dependency Injection
        # Default to SHA256BodyHashAdapter if no port provided
        if body_hash_port is None:
            from codegraph_engine.code_foundation.infrastructure.semantic_ir.adapters import (
                SHA256BodyHashAdapter,
                create_default_metrics_adapter,
            )

            # Create adapter with production metrics
            metrics_adapter = create_default_metrics_adapter(enable_metrics=True)
            body_hash_port = SHA256BodyHashAdapter(source_map=None, metrics_port=metrics_adapter)
        self._body_hash_port = body_hash_port

        # ⭐ SOTA: Extract services to reduce God Class (1811 → ~1000 lines)
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.body_hash_service import BodyHashService
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.incremental_updater import (
            IncrementalSemanticIrUpdater,
        )

        self._body_hash_service = BodyHashService(body_hash_port, self.logger)
        self._incremental_updater = IncrementalSemanticIrUpdater(
            type_builder=self.type_builder,
            signature_builder=self.signature_builder,
            bfg_builder=self.bfg_builder,
            cfg_builder=self.cfg_builder,
            expression_builder=self.expression_builder,
            body_hash_service=self._body_hash_service,
            performance_monitor=self._performance_monitor,
            logger=self.logger,
        )

        if _DEBUG_ENABLED:
            self.logger.debug(
                "semantic_ir_builder_initialized",
                enable_performance_monitoring=enable_performance_monitoring,
                has_type_builder=type_builder is not None,
                has_signature_builder=signature_builder is not None,
                has_bfg_builder=bfg_builder is not None,
                has_cfg_builder=cfg_builder is not None,
                has_expression_builder=expression_builder is not None,
                has_dfg_builder=dfg_builder is not None,
                has_body_hash_port=body_hash_port is not None,
                has_body_hash_service=True,
                has_incremental_updater=True,
            )
        record_counter("semantic_ir_builder_initialized_total")

    def build_full(
        self,
        ir_doc: IRDocument,
        source_map: dict[str, tuple["SourceFile", "AstTree"]] | None = None,
        mode: "SemanticIrBuildMode | None" = None,
        build_config: "BuildConfig | None" = None,  # 🆕 RFC-036: Tier-aware building
    ) -> tuple[SemanticIrSnapshot, SemanticIndex]:
        """
        Build complete semantic IR from structural IR.

        SOTA Enhancement: Mode-aware building for performance optimization.

        Modes:
        - QUICK: Signature + Type only (10x faster, for incremental updates)
        - FULL: Complete CFG/DFG/BFG (for deep analysis)

        Phase 1: Type + Signature
        Phase 2: + BFG + CFG + Expressions + Type Linking (FULL mode only)
        Phase 3: + DFG + Variable Sync (FULL mode only)

        Args:
            ir_doc: Structural IR document
            source_map: Optional mapping of file_path -> (SourceFile, AstTree) for enhanced analysis
                       Pre-parsed AST prevents duplicate parsing (60-70% performance improvement)
            mode: Build mode (QUICK or FULL). Defaults to FULL for backward compatibility.
            build_config: 🆕 RFC-036: Build configuration for tier-aware building (optional)

        Returns:
            (semantic_snapshot, semantic_index)

        Raises:
            ValueError: If IR document is invalid or pipeline validation fails
        """
        # Import here to avoid circular dependency
        from codegraph_engine.code_foundation.domain.semantic_ir.mode import SemanticIrBuildMode

        # Default to FULL mode for backward compatibility
        if mode is None:
            mode = SemanticIrBuildMode.FULL

        # ⭐ CRITICAL: Clear cache to prevent pollution from previous builds
        self._body_hash_service.clear_cache()
        # ⭐ SOTA: Clear statement index cache for O(log n) lookup optimization
        self.expression_builder.clear_caches()

        self.logger.info(
            "semantic_ir_build_full_started",
            ir_nodes_count=len(ir_doc.nodes) if ir_doc else 0,
            has_source_map=source_map is not None,
            source_files_count=len(source_map) if source_map else 0,
            mode=mode.value,
        )
        record_counter("semantic_ir_build_full_total", labels={"type": "full", "mode": mode.value})

        # Start performance monitoring if enabled
        if self._performance_monitor:
            self._performance_monitor.start_pipeline()

        # Ensure source_map is not None
        if source_map is None:
            source_map = {}

        # === Input Validation ===
        self._validate_ir_document(ir_doc)

        # === Phase 1: Type System & Signatures (Always) ===
        if self._profiler:
            self._profiler.start_phase("semantic_phase1_types")
        types, type_index = self._build_phase1_types(ir_doc)
        if self._profiler:
            self._profiler.end_phase("semantic_phase1_types")

        if self._profiler:
            self._profiler.start_phase("semantic_phase1_signatures")
        signatures, signature_index, function_nodes = self._build_phase1_signatures(ir_doc, source_map)
        if self._profiler:
            self._profiler.end_phase("semantic_phase1_signatures")

        # === Phase 2 & 3: CFG/DFG/BFG (mode-aware) ===
        # Use mode.skip_* methods for fine-grained control
        if not mode.skip_cfg():
            # Phase 2a: BFG (Basic Block Flow Graph)
            if not mode.skip_bfg():
                if self._profiler:
                    self._profiler.start_phase("semantic_phase2a_bfg")
                bfg_graphs, bfg_blocks = self._build_phase2a_bfg(ir_doc, source_map, function_nodes)
                if self._profiler:
                    self._profiler.end_phase("semantic_phase2a_bfg")
            else:
                bfg_graphs, bfg_blocks = [], []

            # Phase 2b: CFG (Control Flow Graph)
            if self._profiler:
                self._profiler.start_phase("semantic_phase2b_cfg")
            cfg_graphs, cfg_blocks, cfg_edges = self._build_phase2b_cfg(bfg_graphs, bfg_blocks, source_map)
            if self._profiler:
                self._profiler.end_phase("semantic_phase2b_cfg")

            # Phase 2c: Expressions (for taint analysis)
            if not mode.skip_expressions():
                if self._profiler:
                    self._profiler.start_phase("semantic_phase2c_expressions")
                expressions = self._build_phase2c_expressions(ir_doc, bfg_blocks, source_map)
                self._link_types_to_expressions(expressions, types, ir_doc)
                if self._profiler:
                    self._profiler.end_phase("semantic_phase2c_expressions")
            else:
                expressions = []

            # Phase 2.5: Local Flow Type Inference (SOTA observability)
            if not mode.skip_expressions() and expressions and cfg_graphs:
                if self._profiler:
                    self._profiler.start_phase("semantic_phase2d_local_flow")
                self._local_flow_type_inferencer.infer_and_annotate(ir_doc, cfg_graphs, expressions)

                # Observability: Track local flow stats
                local_stats = self._local_flow_type_inferencer.stats
                record_histogram("local_flow_updated_expressions", local_stats.updated_expressions)
                record_histogram("local_flow_updated_returns", local_stats.updated_returns)
                if self._profiler:
                    self._profiler.end_phase("semantic_phase2d_local_flow")

            # Phase 3: DFG (Data Flow Graph)
            # 🆕 RFC-036: Tier-aware DFG building with threshold
            if not mode.skip_dfg():
                if self._profiler:
                    self._profiler.start_phase("semantic_phase3_dfg")
                dfg_snapshot = self._build_phase3_dfg_with_tier(ir_doc, bfg_blocks, expressions, build_config)
                if self._profiler:
                    self._profiler.end_phase("semantic_phase3_dfg")
            else:
                dfg_snapshot = None

            # Variable Sync (BFG → CFG)
            if bfg_blocks and cfg_blocks:
                if self._profiler:
                    self._profiler.start_phase("semantic_phase4_sync")
                self._sync_variables_bfg_to_cfg(bfg_blocks, cfg_blocks)
                if self._profiler:
                    self._profiler.end_phase("semantic_phase4_sync")
        else:
            # QUICK mode: Skip all CFG/DFG/BFG
            bfg_graphs = []
            bfg_blocks = []
            cfg_graphs = []
            cfg_blocks = []
            cfg_edges = []
            expressions = []
            dfg_snapshot = None

        # === Build Results ===
        semantic_snapshot = SemanticIrSnapshot(
            types=types,
            signatures=signatures,
            bfg_graphs=bfg_graphs,
            bfg_blocks=bfg_blocks,
            cfg_graphs=cfg_graphs,
            cfg_blocks=cfg_blocks,
            cfg_edges=cfg_edges,
            expressions=expressions,
            dfg_snapshot=dfg_snapshot,
        )

        semantic_index = SemanticIndex(
            type_index=type_index,
            signature_index=signature_index,
        )

        # === Final Validation (when CFG is built) ===
        if not mode.skip_cfg() and cfg_graphs:
            self._validate_final_consistency(bfg_graphs, cfg_graphs, cfg_edges, function_nodes, signatures)

        # === Performance Report ===
        self._generate_performance_report(ir_doc, cfg_blocks, cfg_edges, expressions, dfg_snapshot)

        # === Observability: Span Interning Stats ===
        from codegraph_engine.code_foundation.infrastructure.ir.models.span_pool import SpanPool

        span_stats = SpanPool.get_stats()
        record_histogram("span_pool_size", span_stats["pool_size"])
        record_histogram("span_pool_hit_rate_percent", int(span_stats["hit_rate"] * 100))
        record_counter("span_pool_evictions_total", value=span_stats["eviction_count"])

        if _DEBUG_ENABLED:
            self.logger.debug(
                "span_pool_stats",
                pool_size=span_stats["pool_size"],
                hit_rate=f"{span_stats['hit_rate']:.1%}",
                evictions=span_stats["eviction_count"],
            )

        self.logger.info(
            "semantic_ir_build_full_completed",
            types_count=len(types),
            signatures_count=len(signatures),
            bfg_graphs_count=len(bfg_graphs),
            bfg_blocks_count=len(bfg_blocks),
            cfg_graphs_count=len(cfg_graphs),
            cfg_blocks_count=len(cfg_blocks),
            cfg_edges_count=len(cfg_edges),
            expressions_count=len(expressions),
            dfg_variables_count=len(dfg_snapshot.variables) if dfg_snapshot else 0,
            mode=mode.value,
        )
        record_counter("semantic_ir_build_full_completed_total", labels={"status": "success", "mode": mode.value})
        record_histogram("semantic_ir_types_count", len(types))
        record_histogram("semantic_ir_signatures_count", len(signatures))
        record_histogram("semantic_ir_cfg_blocks_count", len(cfg_blocks))
        record_histogram("semantic_ir_cfg_edges_count", len(cfg_edges))

        return semantic_snapshot, semantic_index

    def apply_delta(
        self,
        ir_doc: IRDocument,
        existing_snapshot: SemanticIrSnapshot,
        existing_index: SemanticIndex,
        source_map: dict[str, tuple["SourceFile", "AstTree"]] | None = None,
        mode: "SemanticIrBuildMode | None" = None,
    ) -> tuple[SemanticIrSnapshot, SemanticIndex]:
        """
        Apply incremental changes.

        Detects changed functions and only rebuilds affected semantic entities.
        Reuses unchanged entities from existing snapshot.

        Args:
            ir_doc: Updated structural IR
            existing_snapshot: Previous snapshot
            existing_index: Previous index
            source_map: Optional source file map
            mode: Build mode (QUICK or FULL). Defaults to FULL for backward compatibility.

        Returns:
            (new_snapshot, new_index)
        """
        # Import here to avoid circular dependency
        from codegraph_engine.code_foundation.domain.semantic_ir.mode import SemanticIrBuildMode

        # Default to FULL mode for backward compatibility
        if mode is None:
            mode = SemanticIrBuildMode.FULL
        # ⭐ SOTA: Clear body hash cache for fresh computation
        # Prevents cache pollution from previous builds
        self._body_hash_service.clear_cache()
        # ⭐ SOTA: Clear statement index cache for O(log n) lookup optimization
        self.expression_builder.clear_caches()

        self.logger.info(
            "semantic_ir_apply_delta_started",
            ir_nodes_count=len(ir_doc.nodes),
            existing_signatures_count=len(existing_snapshot.signatures),
            has_source_map=source_map is not None,
        )
        record_counter("semantic_ir_apply_delta_total", labels={"type": "incremental"})

        # Start performance monitoring if enabled
        if self._performance_monitor:
            self._performance_monitor.start_pipeline()

        # Detect changed functions (with source_map for SOTA body hash)
        # ⭐ SOTA: Delegated to IncrementalSemanticIrUpdater
        if self._performance_monitor:
            with self._performance_monitor.stage("Detect Changed Functions"):
                changed_function_ids = self._incremental_updater.detect_changed_functions(
                    ir_doc, existing_snapshot, source_map
                )
                self._performance_monitor.record_items(len(changed_function_ids))
        else:
            changed_function_ids = self._incremental_updater.detect_changed_functions(
                ir_doc, existing_snapshot, source_map
            )

        if not changed_function_ids:
            # No changes, return existing snapshot
            self.logger.info("semantic_ir_no_changes_detected", message="Reusing existing snapshot")
            record_counter("semantic_ir_no_changes_total")

            # End monitoring with zero operations
            if self._performance_monitor:
                metrics = self._performance_monitor.end_pipeline(
                    total_nodes=len(ir_doc.nodes),
                    total_blocks=len(existing_snapshot.cfg_blocks),
                    total_edges=len(existing_snapshot.cfg_edges),
                    total_expressions=0,
                    total_variables=len(existing_snapshot.dfg_snapshot.variables)
                    if existing_snapshot.dfg_snapshot
                    else 0,
                )
                self.logger.info("semantic_ir_performance_report", report=metrics.format_report())

            return existing_snapshot, existing_index

        self.logger.info(
            "semantic_ir_incremental_rebuild_started",
            changed_functions_count=len(changed_function_ids),
            message="Performing incremental rebuild",
        )
        record_counter("semantic_ir_incremental_rebuilds_total")
        record_histogram("semantic_ir_changed_functions_count", len(changed_function_ids))

        # Rebuild only changed functions
        new_snapshot = self._rebuild_changed_functions(
            ir_doc, existing_snapshot, changed_function_ids, source_map or {}, mode
        )

        # CRITICAL OPTIMIZATION: Incremental index update (10-20x faster)
        # ⭐ SOTA: Delegated to IncrementalSemanticIrUpdater
        if self._performance_monitor:
            with self._performance_monitor.stage("Update Indexes Incrementally"):
                new_index = self._incremental_updater.update_index_incrementally(
                    existing_index, existing_snapshot, new_snapshot, changed_function_ids
                )
                self._performance_monitor.record_items(len(changed_function_ids))
        else:
            new_index = self._incremental_updater.update_index_incrementally(
                existing_index, existing_snapshot, new_snapshot, changed_function_ids
            )

        # Generate performance report if monitoring enabled
        if self._performance_monitor:
            var_count = len(new_snapshot.dfg_snapshot.variables) if new_snapshot.dfg_snapshot else 0

            metrics = self._performance_monitor.end_pipeline(
                total_nodes=len(ir_doc.nodes),
                total_blocks=len(new_snapshot.cfg_blocks),
                total_edges=len(new_snapshot.cfg_edges),
                total_expressions=0,  # Not tracked separately in apply_delta
                total_variables=var_count,
            )

            # Log formatted performance report
            self.logger.info("semantic_ir_performance_report", report=metrics.format_report())

        self.logger.info(
            "semantic_ir_apply_delta_completed",
            new_signatures_count=len(new_snapshot.signatures),
            new_cfg_blocks_count=len(new_snapshot.cfg_blocks),
            new_cfg_edges_count=len(new_snapshot.cfg_edges),
            changed_functions_count=len(changed_function_ids),
        )
        record_counter("semantic_ir_apply_delta_completed_total", labels={"status": "success"})
        record_histogram("semantic_ir_incremental_signatures_count", len(new_snapshot.signatures))

        return new_snapshot, new_index

    def get_metrics(self):
        """
        Get pipeline performance metrics.

        Returns:
            PipelineMetrics object if monitoring is enabled, None otherwise.

        Example:
            builder = DefaultSemanticIrBuilder(enable_performance_monitoring=True)
            snapshot, index = builder.build_full(ir_doc, source_map)
            metrics = builder.get_metrics()
            if metrics:
                print(metrics.format_report())
        """
        if self._performance_monitor:
            return self._performance_monitor._metrics
        return None

    def _detect_changed_functions(
        self,
        ir_doc: IRDocument,
        existing_snapshot: SemanticIrSnapshot,
        source_map: dict[str, tuple["SourceFile", "AstTree"]] | None = None,
    ) -> set[str]:
        """
        Detect which functions have changed by comparing IR documents.

        SOTA SOLUTION: Compute body hash from actual source code
        to detect body changes that IR Generator's signature_hash misses.

        Args:
            ir_doc: New IR document
            existing_snapshot: Previous semantic snapshot
            source_map: Source file map for body hash computation

        Returns:
            Set of changed function IDs
        """
        changed_function_ids = set()

        # Build existing function map
        existing_functions = {}
        for sig in existing_snapshot.signatures:
            existing_functions[sig.owner_node_id] = sig

        # Build new IR signature map (for signature-level comparison)
        new_ir_signatures = {sig.owner_node_id: sig for sig in ir_doc.signatures}

        # Check new functions
        new_function_nodes = [n for n in ir_doc.nodes if n.kind.name in ("FUNCTION", "METHOD")]

        new_functions_count = 0
        modified_functions_count = 0

        for func_node in new_function_nodes:
            func_id = func_node.id
            existing_sig = existing_functions.get(func_id)

            if not existing_sig:
                # New function
                if _DEBUG_ENABLED:
                    self.logger.debug("semantic_ir_new_function_detected", function_id=func_id)
                changed_function_ids.add(func_id)
                new_functions_count += 1
            else:
                # Check 1: Signature-level comparison (IR signature hash)
                new_ir_sig = new_ir_signatures.get(func_id)
                if new_ir_sig and existing_sig.signature_hash:
                    if new_ir_sig.signature_hash != existing_sig.signature_hash:
                        if _DEBUG_ENABLED:
                            self.logger.debug(
                                "semantic_ir_changed_function_detected",
                                function_id=func_id,
                                reason="signature_hash_mismatch",
                            )
                        changed_function_ids.add(func_id)
                        modified_functions_count += 1
                        continue

                # Check 2: SOTA body hash comparison (from actual source, with caching)
                if source_map:
                    new_body_hash, error = self._compute_function_body_hash_cached(func_node, source_map)
                    existing_body_hash = existing_sig.raw_body_hash if hasattr(existing_sig, "raw_body_hash") else None

                    if new_body_hash and existing_body_hash:
                        # Both have hash - strict comparison
                        if new_body_hash != existing_body_hash:
                            if _DEBUG_ENABLED:
                                self.logger.debug(
                                    "semantic_ir_changed_function_detected",
                                    function_id=func_id,
                                    reason="body_hash_mismatch",
                                    old_hash=existing_body_hash,
                                    new_hash=new_body_hash,
                                )
                            changed_function_ids.add(func_id)
                            modified_functions_count += 1
                            continue
                        else:
                            # ⭐ CRITICAL FIX: Body hash same → skip fallback
                            # No need to check heuristic if body hash matches
                            continue
                    elif new_body_hash or existing_body_hash:
                        # ⭐ BACKWARD COMPATIBILITY: Migration mode
                        # Only one has hash - rebuild to ensure consistency
                        if _DEBUG_ENABLED:
                            self.logger.debug(
                                "semantic_ir_body_hash_migration",
                                function_id=func_id,
                                has_new=bool(new_body_hash),
                                has_existing=bool(existing_body_hash),
                                action="rebuild_for_migration",
                            )
                        changed_function_ids.add(func_id)
                        modified_functions_count += 1
                        continue

                # Check 3: Fallback heuristic comparison
                if self._function_has_changed(func_node, existing_sig):
                    if _DEBUG_ENABLED:
                        self.logger.debug(
                            "semantic_ir_changed_function_detected",
                            function_id=func_id,
                            reason="heuristic",
                        )
                    changed_function_ids.add(func_id)
                    modified_functions_count += 1

        # Check deleted functions
        new_function_ids = {n.id for n in new_function_nodes}
        deleted_functions_count = 0
        for existing_func_id in existing_functions.keys():
            if existing_func_id not in new_function_ids:
                if _DEBUG_ENABLED:
                    self.logger.debug("semantic_ir_deleted_function_detected", function_id=existing_func_id)
                changed_function_ids.add(existing_func_id)
                deleted_functions_count += 1

        self.logger.info(
            "semantic_ir_change_detection_completed",
            new_functions=new_functions_count,
            modified_functions=modified_functions_count,
            deleted_functions=deleted_functions_count,
            total_changed=len(changed_function_ids),
        )
        record_counter("semantic_ir_functions_detected_total", labels={"change_type": "new"}, value=new_functions_count)
        record_counter(
            "semantic_ir_functions_detected_total", labels={"change_type": "modified"}, value=modified_functions_count
        )
        record_counter(
            "semantic_ir_functions_detected_total", labels={"change_type": "deleted"}, value=deleted_functions_count
        )

        return changed_function_ids

    def _function_has_changed(self, func_node, existing_sig) -> bool:
        """
        Check if function has changed by comparing with existing signature.

        Uses precise heuristics for change detection with balanced trade-offs:
        - Prioritizes accuracy to minimize false negatives (missing changes)
        - Accepts some false positives (redundant rebuilds) for safety
        - Uses multiple signals: name, signature_id, hash, span

        Args:
            func_node: New function node from IR
            existing_sig: Existing SignatureEntity

        Returns:
            True if function has changed, False otherwise
        """
        # 1. Compare name - if renamed, function changed
        if func_node.name != existing_sig.name:
            return True

        # 2. Compare signature ID first (most reliable)
        # signature_id encodes the function signature structure
        if hasattr(func_node, "signature_id") and func_node.signature_id:
            if func_node.signature_id != existing_sig.id:
                return True
            # If signature_id matches, likely unchanged
            # Continue to check hash for body changes

        # 3. Compare signature hash if available (detects body changes)
        # signature_hash encodes the full signature + body structure
        if existing_sig.signature_hash:
            new_hash = None
            if hasattr(func_node, "signature_hash") and func_node.signature_hash:
                new_hash = func_node.signature_hash

            if new_hash:
                # Extract hash suffix (e.g., "sha256:abc123" -> "abc123")
                old_hash = (
                    existing_sig.signature_hash.split(":")[-1]
                    if ":" in existing_sig.signature_hash
                    else existing_sig.signature_hash
                )
                new_hash_value = new_hash.split(":")[-1] if ":" in new_hash else new_hash
                if new_hash_value != old_hash:
                    return True

        # 4. If we have signature_id match and no contradicting signals, assume unchanged
        if hasattr(func_node, "signature_id") and func_node.signature_id:
            if func_node.signature_id == existing_sig.id:
                # signature_id matches and no hash mismatch detected
                return False

        # 5. Fallback: Check span as last resort
        # If span changed significantly, function likely changed
        if hasattr(func_node, "span") and func_node.span:
            # Check if line count changed by > 20%
            old_lines = existing_sig.raw.count("\n") + 1 if existing_sig.raw else 1
            new_lines = func_node.span.end_line - func_node.span.start_line + 1
            if abs(new_lines - old_lines) > max(1, old_lines * 0.2):
                return True

        # 6. If no reliable comparison method, be conservative
        # This ensures we don't miss changes, at the cost of some redundant rebuilds
        if not existing_sig.signature_hash and (not hasattr(func_node, "signature_id") or not func_node.signature_id):
            # No reliable signals, assume changed (conservative)
            return True

        # If all checks pass, function hasn't changed
        return False

    def _update_index_incrementally(
        self,
        existing_index: SemanticIndex,
        existing_snapshot: SemanticIrSnapshot,
        new_snapshot: SemanticIrSnapshot,
        changed_function_ids: set[str],
    ) -> SemanticIndex:
        """
        Update index incrementally instead of full rebuild.

        CRITICAL OPTIMIZATION: This method provides 10-20x speedup for large codebases
        by only updating changed entities instead of rebuilding entire index.

        Strategy:
        1. Reuse existing index entries for unchanged functions
        2. Update only entries for changed functions
        3. Remove entries for deleted functions
        4. Add entries for new functions

        Complexity: O(m) where m = changed functions, vs O(n) for full rebuild

        Args:
            existing_index: Previous index
            existing_snapshot: Previous snapshot
            new_snapshot: New snapshot
            changed_function_ids: Set of changed function IDs

        Returns:
            New index with incremental updates
        """
        # Build lookup sets
        {sig.id for sig in existing_snapshot.signatures}
        existing_owner_ids = {sig.owner_node_id for sig in existing_snapshot.signatures}
        new_sig_by_owner = {sig.owner_node_id: sig for sig in new_snapshot.signatures}

        # If no changes at all, reuse existing index
        if len(changed_function_ids) == 0:
            return existing_index

        # For small changes, incremental update is much faster
        # For large changes (>threshold), fall back to full rebuild
        change_ratio = len(changed_function_ids) / max(1, len(existing_owner_ids))
        if change_ratio > INCREMENTAL_UPDATE_THRESHOLD:
            # Too many changes, full rebuild is simpler
            return SemanticIndex(
                type_index=self.type_builder._build_index(new_snapshot.types),
                signature_index=self.signature_builder._build_index(new_snapshot.signatures),
            )

        # Incremental update: Copy existing index structure
        # TypeIndex: Shallow copy (types rarely change)
        new_type_index = existing_index.type_index

        # SignatureIndex: Update incrementally
        # SignatureIndex is a SignatureIndex object with function_to_signature dict
        if hasattr(existing_index.signature_index, "function_to_signature"):
            # Copy existing mapping
            new_function_to_signature = existing_index.signature_index.function_to_signature.copy()

            # Update changed functions
            for owner_id in changed_function_ids:
                if owner_id in new_sig_by_owner:
                    # Function still exists, update mapping
                    sig = new_sig_by_owner[owner_id]
                    new_function_to_signature[owner_id] = sig.id
                elif owner_id in new_function_to_signature:
                    # Function deleted, remove mapping
                    del new_function_to_signature[owner_id]

            # Create new SignatureIndex
            from codegraph_engine.code_foundation.infrastructure.semantic_ir.context import SignatureIndex

            new_sig_index = SignatureIndex(function_to_signature=new_function_to_signature)
        else:
            # Fallback: Full rebuild if structure unexpected
            new_sig_index = self.signature_builder._build_index(new_snapshot.signatures)

        # Type index: Only rebuild if types changed (rare)
        if len(new_snapshot.types) != len(existing_snapshot.types):
            new_type_index = self.type_builder._build_index(new_snapshot.types)

        return SemanticIndex(
            type_index=new_type_index,
            signature_index=new_sig_index,
        )

    def _compute_function_body_hash(self, func_node, source_map: dict[str, tuple["SourceFile", "AstTree"]]) -> str:
        """
        Compute hash of function body content from source code.

        SOTA SOLUTION with STRICT error handling:
        - Validates all inputs explicitly
        - Raises ValueError on any invalid state
        - Prevents silent failures that cause False Negatives

        Args:
            func_node: Function node from IR
            source_map: Source file map (REQUIRED)

        Returns:
            SHA256 hash of function body (format: "body_sha256:XXXXXXXXXXXXXXXX")

        Raises:
            ValueError: If source_map missing, file not found, or span invalid
        """
        import hashlib

        # STRICT: source_map required
        if not source_map:
            raise ValueError(
                f"source_map is required for body hash computation. "
                f"Function: {func_node.id}. "
                f"Cannot detect body changes without source code."
            )

        # STRICT: file must exist in source_map
        if func_node.file_path not in source_map:
            raise ValueError(
                f"File '{func_node.file_path}' not found in source_map. "
                f"Function: {func_node.id}. "
                f"Available files: {list(source_map.keys())}"
            )

        # STRICT: span required
        if not hasattr(func_node, "span") or not func_node.span:
            raise ValueError(
                f"Function node missing span attribute. Function: {func_node.id}. Cannot extract body without span."
            )

        source_file, _ = source_map[func_node.file_path]

        # STRICT: source content validation
        if not source_file.content:
            raise ValueError(f"Source file has no content. File: {func_node.file_path}, Function: {func_node.id}")

        lines = source_file.content.splitlines()
        start_line = func_node.span.start_line - 1  # 0-indexed
        end_line = func_node.span.end_line  # inclusive

        # STRICT: bounds checking
        if start_line < 0:
            raise ValueError(f"Invalid span: start_line={func_node.span.start_line} < 1. Function: {func_node.id}")

        if end_line > len(lines):
            raise ValueError(
                f"Span out of bounds: end_line={end_line} > total_lines={len(lines)}. "
                f"Function: {func_node.id}, File: {func_node.file_path}"
            )

        if start_line >= end_line:
            raise ValueError(f"Invalid span: start_line={start_line} >= end_line={end_line}. Function: {func_node.id}")

        # Extract body
        body_lines = lines[start_line:end_line]
        body_content = "\n".join(body_lines)

        # Compute SHA256 hash
        hash_obj = hashlib.sha256(body_content.encode("utf-8"))
        hash_hex = hash_obj.hexdigest()[:BODY_HASH_LENGTH]

        return f"{BODY_HASH_PREFIX}:{hash_hex}"

    def _compute_function_body_hash_safe(
        self, func_node, source_map: dict[str, tuple["SourceFile", "AstTree"]] | None
    ) -> tuple[str | None, str | None]:
        """
        Safe wrapper for _compute_function_body_hash that handles errors gracefully.

        Returns:
            (hash, error_message): Either (hash, None) or (None, error_msg)
        """
        if not source_map:
            return None, "source_map_missing"

        try:
            hash_value = self._compute_function_body_hash(func_node, source_map)
            return hash_value, None
        except ValueError as e:
            # Log error but don't crash
            if _DEBUG_ENABLED:
                self.logger.debug(
                    "body_hash_computation_failed",
                    function_id=func_node.id,
                    error=str(e),
                )
            return None, f"computation_error: {str(e)}"
        except Exception as e:
            # Unexpected error
            self.logger.error(
                "body_hash_unexpected_error",
                function_id=func_node.id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return None, f"unexpected_error: {type(e).__name__}"

    def _compute_function_body_hash_cached(
        self, func_node, source_map: dict[str, tuple["SourceFile", "AstTree"]] | None
    ) -> tuple[str | None, str | None]:
        """
        SOTA: Hexagonal Architecture - delegate to Port.

        Domain → Port (interface) → Adapter (implementation)

        Benefits:
        - Domain independent of SourceFile/AstTree
        - Adapter handles caching, metrics, thread-safety
        - Easy to swap implementations (e.g., Redis cache)

        Returns:
            (hash, error_message): Either (hash, None) or (None, error_msg)
        """
        # Update adapter's source_map if needed
        if hasattr(self._body_hash_port, "update_source_map") and source_map:
            self._body_hash_port.update_source_map(source_map)

        # Delegate to port
        if not hasattr(func_node, "span") or not func_node.span:
            return None, f"Function node missing span: {func_node.id}"

        hash_value, error = self._body_hash_port.compute_hash(func_node.file_path, func_node.span)

        return hash_value, error

    def clear_body_hash_cache(self):
        """
        Clear body hash cache (Hexagonal Architecture - delegate to service).

        SOTA: Builder → Service → Port → Adapter
        """
        self._body_hash_service.clear_cache()
        self.expression_builder.clear_caches()

    def _rebuild_changed_functions(
        self,
        ir_doc: IRDocument,
        existing_snapshot: SemanticIrSnapshot,
        changed_function_ids: set[str],
        source_map: dict[str, "SourceFile"],
        mode: "SemanticIrBuildMode",
    ) -> SemanticIrSnapshot:
        """
        Rebuild semantic entities for changed functions only.

        Refactored to eliminate duplication via helper methods.
        Reduced from 216 lines → 85 lines (60% reduction).

        Args:
            ir_doc: New IR document
            existing_snapshot: Previous snapshot
            changed_function_ids: Set of changed function IDs
            source_map: Source file map

        Returns:
            New semantic snapshot with incremental updates
        """
        if _DEBUG_ENABLED:
            self.logger.debug(
                "semantic_ir_rebuild_changed_functions_started",
                changed_functions_count=len(changed_function_ids),
                existing_signatures_count=len(existing_snapshot.signatures),
            )

        # ============================================================
        # Step 1: Filter out unchanged entities
        # ============================================================
        if self._performance_monitor:
            with self._performance_monitor.stage("Filter Unchanged Entities"):
                filtered = self._filter_unchanged_entities(existing_snapshot, changed_function_ids)
                kept_sigs = len(filtered["signatures"])
                total_sigs = len(existing_snapshot.signatures)
                self._performance_monitor.record_items(kept_sigs)
                if _DEBUG_ENABLED:
                    self.logger.debug(
                        "semantic_ir_filter_unchanged_entities",
                        kept_signatures=kept_sigs,
                        total_signatures=total_sigs,
                        filtered_signatures=total_sigs - kept_sigs,
                        stage="incremental",
                    )
        else:
            filtered = self._filter_unchanged_entities(existing_snapshot, changed_function_ids)

        # Extract filtered data
        new_types = filtered["types"]
        new_signatures = filtered["signatures"]
        new_bfg_graphs = filtered["bfg_graphs"]
        new_bfg_blocks = filtered["bfg_blocks"]
        new_cfg_graphs = filtered["cfg_graphs"]
        new_cfg_blocks = filtered["cfg_blocks"]
        new_cfg_edges = filtered["cfg_edges"]

        # ============================================================
        # Step 2: Rebuild changed functions
        # ============================================================
        changed_func_nodes = [n for n in ir_doc.nodes if n.id in changed_function_ids]
        ir_signatures_by_node_id = {sig.owner_node_id: sig for sig in ir_doc.signatures}
        expressions = []

        if self._performance_monitor:
            with self._performance_monitor.stage("Rebuild Changed Functions"):
                for func_node in changed_func_nodes:
                    result = self._rebuild_single_function(
                        func_node, ir_doc, ir_signatures_by_node_id, source_map, expressions, mode
                    )

                    # Append rebuilt entities to accumulator lists
                    if result["signature"]:
                        new_signatures.append(result["signature"])
                    if result["bfg_graph"]:
                        new_bfg_graphs.append(result["bfg_graph"])
                    new_bfg_blocks.extend(result["bfg_blocks"])
                    new_cfg_graphs.extend(result["cfg_graphs"])
                    new_cfg_blocks.extend(result["cfg_blocks"])
                    new_cfg_edges.extend(result["cfg_edges"])

                self._performance_monitor.record_items(len(changed_func_nodes))
        else:
            for func_node in changed_func_nodes:
                result = self._rebuild_single_function(
                    func_node, ir_doc, ir_signatures_by_node_id, source_map, expressions, mode
                )

                # Append rebuilt entities to accumulator lists
                if result["signature"]:
                    new_signatures.append(result["signature"])
                if result["bfg_graph"]:
                    new_bfg_graphs.append(result["bfg_graph"])
                new_bfg_blocks.extend(result["bfg_blocks"])
                new_cfg_graphs.extend(result["cfg_graphs"])
                new_cfg_blocks.extend(result["cfg_blocks"])
                new_cfg_edges.extend(result["cfg_edges"])

        # ============================================================
        # Step 3: Rebuild DFG for changed functions
        # ============================================================
        # DISABLED: LocalFlowTypeInferencer causes 5x slowdown - needs optimization
        if self._performance_monitor:
            with self._performance_monitor.stage("Rebuild DFG"):
                # if new_cfg_graphs and expressions:
                #     self._local_flow_type_inferencer.infer_and_annotate(ir_doc, new_cfg_graphs, expressions)
                dfg_snapshot = self.dfg_builder.build_full(ir_doc, new_bfg_blocks, expressions)
                if dfg_snapshot:
                    self._performance_monitor.record_items(len(dfg_snapshot.variables))
        else:
            # if new_cfg_graphs and expressions:
            #     self._local_flow_type_inferencer.infer_and_annotate(ir_doc, new_cfg_graphs, expressions)
            dfg_snapshot = self.dfg_builder.build_full(ir_doc, new_bfg_blocks, expressions)

        # ============================================================
        # Step 4: Copy variable tracking from BFG to CFG
        # ============================================================
        if self._performance_monitor:
            with self._performance_monitor.stage("Variable Sync (BFG→CFG)"):
                synced_count = self._sync_bfg_to_cfg_variables(new_bfg_blocks, new_cfg_blocks)
                self._performance_monitor.record_items(synced_count)
        else:
            synced_count = self._sync_bfg_to_cfg_variables(new_bfg_blocks, new_cfg_blocks)

        # ============================================================
        # Step 5: Build new snapshot
        # ============================================================
        new_snapshot = SemanticIrSnapshot(
            types=new_types,
            signatures=new_signatures,
            bfg_graphs=new_bfg_graphs,
            bfg_blocks=new_bfg_blocks,
            cfg_graphs=new_cfg_graphs,
            cfg_blocks=new_cfg_blocks,
            cfg_edges=new_cfg_edges,
            dfg_snapshot=dfg_snapshot,
        )

        return new_snapshot

    def _build_expressions_from_blocks(self, ir_doc: IRDocument, bfg_blocks, source_map):
        """
        Build expression IR from BFG blocks.

        Extracts expressions from each block using the expression builder.
        Uses early-return pattern to reduce nesting complexity.

        Args:
            bfg_blocks: List of BFG blocks to process
            source_map: Dict mapping file_path -> SourceFile for source code access

        Returns:
            List of Expression objects
        """
        expressions = []

        if not source_map:
            self.logger.warning(
                "semantic_ir_no_source_map",
                phase="phase_2c",
                message="No source_map provided. Expression generation skipped. DFG will be limited.",
            )
            record_counter("semantic_ir_expression_build_skipped_total", labels={"reason": "no_source_map"})
            return expressions

        if _DEBUG_ENABLED:
            self.logger.debug(
                "semantic_ir_build_expressions_started",
                phase="phase_2c",
                source_files_count=len(source_map),
                bfg_blocks_count=len(bfg_blocks),
                source_map_keys=list(source_map.keys())[:5],  # Log first 5 keys
            )

        # SOTA: Collect expressions from all blocks WITHOUT Pyright calls
        # Then do ONE batch Pyright call per file at the end
        # This reduces LSP calls from O(blocks) to O(files)
        expressions_by_file: dict[str, tuple[list, "SourceFile"]] = {}
        node_file_path_by_id: dict[str, str] = {}
        for n in ir_doc.nodes:
            if getattr(n, "id", None) and getattr(n, "file_path", None):
                node_file_path_by_id[n.id] = n.file_path

        for block in bfg_blocks:
            block_exprs, resolved_file_path = self._process_block_for_expression(
                block, source_map, node_file_path_by_id, _defer_pyright=True
            )
            if block_exprs:
                # Group by file for batch enrichment
                if resolved_file_path and resolved_file_path in source_map:
                    source_data = source_map[resolved_file_path]
                    source_file = source_data[0] if isinstance(source_data, tuple) else source_data
                    if resolved_file_path not in expressions_by_file:
                        expressions_by_file[resolved_file_path] = ([], source_file)
                    expressions_by_file[resolved_file_path][0].extend(block_exprs)
                expressions.extend(block_exprs)

        # SOTA: Pyright batch enrichment is now DEFERRED
        # LocalFlowTypeInferencer runs FIRST (in Phase 3) to resolve 80-90% of types locally
        # Then remaining unresolved expressions get Pyright fallback via batch_enrich_final()
        # This reduces Pyright calls by 80-90% and eliminates 100s+ of LSP overhead
        #
        # Old (slow): expressions → Pyright batch (100s)
        # New (fast): expressions → LocalFlow (0.5s) → Pyright fallback for unresolved only
        #
        # NOTE: batch_enrich_expressions() call removed here.
        # Pyright fallback happens in _finalize_expression_types() after LocalFlow inference.

        if _DEBUG_ENABLED:
            self.logger.debug(
                "semantic_ir_expressions_generated",
                phase="phase_2c",
                total_expressions=len(expressions),
                files_enriched=len(expressions_by_file),
            )
        record_histogram("semantic_ir_expressions_generated_count", len(expressions))
        return expressions

    def _process_block_for_expression(
        self,
        block,
        source_map,
        node_file_path_by_id: dict[str, str],
        *,
        _defer_pyright: bool = False,
    ) -> tuple[list, str | None]:
        """
        Process a single BFG block to extract expressions.

        Uses early-return pattern to reduce nesting:
        - Check if file_path can be extracted (if not, warn and return)
        - Check if file_path exists in source_map (if not, skip and return)
        - Build expressions from block

        Args:
            block: BFG block to process
            source_map: Dict mapping file_path -> (SourceFile, AstTree) or file_path -> SourceFile
            _defer_pyright: If True, skip Pyright enrichment for file-level batching

        Returns:
            List of expressions extracted from this block
        """

        if _DEBUG_ENABLED:
            self.logger.debug(
                "semantic_ir_process_block",
                phase="phase_2c",
                function_node_id=block.function_node_id,
            )

        # Extract file_path using safe parsing utility
        file_path = extract_file_path(block.function_node_id)
        # Hash IDs cannot encode file_path; fall back to canonical Node.file_path
        if file_path == "<hash_id>" or not file_path:
            file_path = node_file_path_by_id.get(block.function_node_id)
        if _DEBUG_ENABLED:
            self.logger.debug("semantic_ir_file_path_extracted", phase="phase_2c", file_path=file_path)

        # Early return: file_path extraction failed
        if not file_path:
            self.logger.warning(
                "semantic_ir_file_path_extraction_failed",
                phase="phase_2c",
                function_node_id=block.function_node_id,
            )
            return [], None

        # Early return: file_path not in source_map
        if file_path not in source_map:
            if _DEBUG_ENABLED:
                self.logger.debug(
                    "semantic_ir_file_path_not_in_source_map",
                    phase="phase_2c",
                    file_path=file_path,
                    message="Skipping block",
                )
            return [], file_path

        # Happy path: build expressions
        # Handle both tuple (SourceFile, AstTree) and plain SourceFile
        source_data = source_map[file_path]

        # CRITICAL: Validate source_data is not None (defensive programming)
        if source_data is None:
            if _DEBUG_ENABLED:
                self.logger.debug(
                    "semantic_ir_source_data_none",
                    phase="phase_2c",
                    file_path=file_path,
                    message="source_map contains None value - skipping block",
                )
            return []

        if isinstance(source_data, tuple):
            # Validate tuple elements are not None
            if len(source_data) < 2 or source_data[0] is None:
                if _DEBUG_ENABLED:
                    self.logger.debug(
                        "semantic_ir_invalid_tuple",
                        phase="phase_2c",
                        file_path=file_path,
                        message="Invalid source_data tuple - skipping block",
                    )
                return [], file_path

            source_file, ast_tree = source_data
            # Pass both source_file and pre-parsed AST
            # SOTA: _defer_pyright=True for file-level batch enrichment
            block_exprs = self.expression_builder.build_from_block(
                block, source_file, ast_tree=ast_tree, _defer_pyright=_defer_pyright
            )
        else:
            source_file = source_data
            block_exprs = self.expression_builder.build_from_block(block, source_file, _defer_pyright=_defer_pyright)

        if _DEBUG_ENABLED:
            self.logger.debug(
                "semantic_ir_expressions_from_block",
                phase="phase_2c",
                expressions_count=len(block_exprs),
            )
        return block_exprs, file_path

    def _filter_unchanged_entities(self, existing_snapshot, changed_function_ids):
        """
        Filter out entities from changed functions.

        Args:
            existing_snapshot: Previous semantic snapshot
            changed_function_ids: Set of changed function IDs

        Returns:
            Dict with filtered entities: types, signatures, bfg/cfg data
        """

        # Types are not function-specific, copy as-is
        new_types = existing_snapshot.types.copy()

        # Filter out data for changed functions (single-pass comprehensions)
        new_signatures = [sig for sig in existing_snapshot.signatures if sig.owner_node_id not in changed_function_ids]
        new_bfg_graphs = [
            bfg for bfg in existing_snapshot.bfg_graphs if bfg.function_node_id not in changed_function_ids
        ]
        new_bfg_blocks = [
            block for block in existing_snapshot.bfg_blocks if block.function_node_id not in changed_function_ids
        ]
        new_cfg_graphs = [
            cfg for cfg in existing_snapshot.cfg_graphs if cfg.function_node_id not in changed_function_ids
        ]
        new_cfg_blocks = [
            block for block in existing_snapshot.cfg_blocks if block.function_node_id not in changed_function_ids
        ]

        # Filter edges by checking if source/target blocks still exist
        remaining_cfg_block_ids = {block.id for block in new_cfg_blocks}
        new_cfg_edges = [
            edge
            for edge in existing_snapshot.cfg_edges
            if edge.source_block_id in remaining_cfg_block_ids and edge.target_block_id in remaining_cfg_block_ids
        ]

        # Log filtering stats
        kept_sigs = len(new_signatures)
        total_sigs = len(existing_snapshot.signatures)
        if _DEBUG_ENABLED:
            self.logger.debug(
                "semantic_ir_filter_stats",
                stage="incremental",
                kept_signatures=kept_sigs,
                total_signatures=total_sigs,
                filtered_signatures=total_sigs - kept_sigs,
            )

        return {
            "types": new_types,
            "signatures": new_signatures,
            "bfg_graphs": new_bfg_graphs,
            "bfg_blocks": new_bfg_blocks,
            "cfg_graphs": new_cfg_graphs,
            "cfg_blocks": new_cfg_blocks,
            "cfg_edges": new_cfg_edges,
        }

    def _rebuild_single_function(
        self, func_node, ir_doc, ir_signatures_by_node_id, source_map, expressions_output, mode
    ):
        """
        Rebuild semantic IR for a single changed function.

        Args:
            func_node: IR function node to rebuild
            ir_doc: IR document
            ir_signatures_by_node_id: Mapping of node IDs to signatures
            source_map: Source file mapping
            expressions_output: List to append expressions to
            mode: Build mode (QUICK or FULL)

        Returns:
            Dict with rebuilt entities: signature, bfg/cfg data
        """

        if _DEBUG_ENABLED:
            self.logger.debug("semantic_ir_rebuild_function", function_id=func_node.id)

        result = {
            "signature": None,
            "bfg_graph": None,
            "bfg_blocks": [],
            "cfg_graphs": [],
            "cfg_blocks": [],
            "cfg_edges": [],
        }

        # Get signature from IR document
        sig = ir_signatures_by_node_id.get(func_node.id)
        if sig:
            # ⭐ SOTA: Add body hash from actual source (with caching)
            if source_map:
                body_hash, error = self._compute_function_body_hash_cached(func_node, source_map)
                if body_hash:
                    # Create new signature with body hash
                    from dataclasses import replace

                    sig = replace(sig, raw_body_hash=body_hash)
                elif error and _DEBUG_ENABLED:
                    self.logger.debug("body_hash_failed_rebuild", func_id=func_node.id, error=error)

            result["signature"] = sig

        # ⭐ SOTA: QUICK mode skips CFG/DFG/BFG (814x faster)
        if mode.is_full():
            # Rebuild BFG
            bfg_graph, bfg_blocks = self.bfg_builder._build_function_bfg(func_node, ir_doc, source_map)
            if bfg_graph:
                result["bfg_graph"] = bfg_graph
                result["bfg_blocks"] = bfg_blocks

                # Generate expressions for newly created blocks
                for block in bfg_blocks:
                    block_exprs = self._process_block_for_expression(block, source_map)
                    expressions_output.extend(block_exprs)

                # Rebuild CFG for this function
                cfg_graph, cfg_blocks, cfg_edges = self.cfg_builder.build_from_bfg([bfg_graph], bfg_blocks, source_map)
                result["cfg_graphs"] = cfg_graph
                result["cfg_blocks"] = cfg_blocks
                result["cfg_edges"] = cfg_edges

        return result

    def _sync_bfg_to_cfg_variables(self, new_bfg_blocks, new_cfg_blocks):
        """
        Copy variable tracking from BFG blocks to CFG blocks.

        Args:
            new_bfg_blocks: List of BFG blocks
            new_cfg_blocks: List of CFG blocks to update

        Returns:
            Number of synced blocks
        """

        bfg_blocks_by_id = {block.id: block for block in new_bfg_blocks}
        synced_count = 0

        for cfg_block in new_cfg_blocks:
            # Use safe ID conversion utility
            bfg_id = convert_cfg_id_to_bfg_id(cfg_block.id)
            bfg_block = bfg_blocks_by_id.get(bfg_id)
            if bfg_block:
                cfg_block.defined_variable_ids = bfg_block.defined_variable_ids.copy()
                cfg_block.used_variable_ids = bfg_block.used_variable_ids.copy()
                synced_count += 1
            else:
                self.logger.warning(
                    "semantic_ir_bfg_block_not_found",
                    stage="incremental",
                    cfg_block_id=cfg_block.id,
                )

        if _DEBUG_ENABLED:
            self.logger.debug(
                "semantic_ir_variable_sync_complete",
                stage="incremental",
                synced_blocks_count=synced_count,
            )
        return synced_count

    # ============================================================
    # Helper Methods for build_full (Long Method Refactoring #6)
    # ============================================================

    def _validate_ir_document(self, ir_doc: IRDocument) -> None:
        """
        Validate IR document input.

        Args:
            ir_doc: IR document to validate

        Raises:
            ValueError: If IR document is invalid
        """
        if not ir_doc:
            raise ValueError("IRDocument cannot be None")
        if not ir_doc.nodes:
            raise ValueError("IRDocument has no nodes. Cannot build semantic IR from empty document.")
        if _DEBUG_ENABLED:
            self.logger.debug("semantic_ir_validation_ir_document", phase="validation", nodes_count=len(ir_doc.nodes))

    def _build_phase1_types(self, ir_doc: IRDocument) -> tuple[list, dict]:
        """
        Phase 1a: Build type system.

        Args:
            ir_doc: IR document

        Returns:
            Tuple of (types, type_index)
        """
        if self._performance_monitor:
            with self._performance_monitor.stage("Phase 1a: Type System"):
                types, type_index = self.type_builder.build_full(ir_doc)
                self._performance_monitor.record_items(len(types))
        else:
            types, type_index = self.type_builder.build_full(ir_doc)
        if _DEBUG_ENABLED:
            self.logger.debug("semantic_ir_types_generated", phase="phase_1a_validation", types_count=len(types))
        return types, type_index

    def _build_phase1_signatures(
        self, ir_doc: IRDocument, source_map: dict[str, tuple["SourceFile", "AstTree"]] | None = None
    ) -> tuple[list, dict, list]:
        """
        Phase 1b: Build function signatures + SOTA body hash.

        Args:
            ir_doc: IR document
            source_map: Source files for body hash computation

        Returns:
            Tuple of (signatures, signature_index, function_nodes)
        """
        if self._performance_monitor:
            with self._performance_monitor.stage("Phase 1b: Signatures"):
                signatures, signature_index = self.signature_builder.build_full(ir_doc)

                # ⭐ SOTA: Add body hash for each signature (with caching)
                if source_map:
                    node_map = {n.id: n for n in ir_doc.nodes}
                    for sig in signatures:
                        func_node = node_map.get(sig.owner_node_id)
                        if func_node:
                            # ⭐ SOTA: Delegated to BodyHashService
                            self._body_hash_service.add_body_hash_to_signature(sig, func_node, source_map)

                self._performance_monitor.record_items(len(signatures))
        else:
            signatures, signature_index = self.signature_builder.build_full(ir_doc)

            # ⭐ SOTA: Add body hash for each signature (with caching)
            if source_map:
                node_map = {n.id: n for n in ir_doc.nodes}
                for sig in signatures:
                    func_node = node_map.get(sig.owner_node_id)
                    if func_node:
                        body_hash, error = self._compute_function_body_hash_cached(func_node, source_map)
                        if body_hash:
                            sig.raw_body_hash = body_hash
                        elif error and _DEBUG_ENABLED:
                            self.logger.debug("body_hash_failed", sig_id=sig.id, error=error)

        function_nodes = [n for n in ir_doc.nodes if n.kind.name in ("FUNCTION", "METHOD", "LAMBDA")]
        if _DEBUG_ENABLED:
            self.logger.debug(
                "semantic_ir_signatures_generated",
                phase="phase_1b_validation",
                function_nodes_count=len(function_nodes),
                signatures_count=len(signatures),
            )
        if function_nodes and not signatures:
            self.logger.warning(
                "semantic_ir_no_signatures_generated",
                phase="phase_1b_validation",
                message="Document has functions but no signatures generated",
            )

        return signatures, signature_index, function_nodes

    def _build_phase2a_bfg(self, ir_doc: IRDocument, source_map: dict, function_nodes: list) -> tuple[list, list]:
        """
        Phase 2a: Build BFG (Basic Block Flow Graph).

        Args:
            ir_doc: IR document
            source_map: Source file map
            function_nodes: List of function nodes

        Returns:
            Tuple of (bfg_graphs, bfg_blocks)

        Raises:
            ValueError: If BFG builder produces graphs but no blocks
        """
        if source_map is None:
            source_map = {}
        if self._performance_monitor:
            with self._performance_monitor.stage("Phase 2a: BFG (Basic Blocks)"):
                bfg_graphs, bfg_blocks = self.bfg_builder.build_full(ir_doc, source_map)
                self._performance_monitor.record_items(len(bfg_blocks))
                if hasattr(self.bfg_builder, "get_cache_stats"):
                    self._performance_monitor.record_cache_stats(self.bfg_builder.get_cache_stats())
        else:
            bfg_graphs, bfg_blocks = self.bfg_builder.build_full(ir_doc, source_map)

        if _DEBUG_ENABLED:
            self.logger.debug(
                "semantic_ir_bfg_generated",
                phase="phase_2a_validation",
                bfg_graphs_count=len(bfg_graphs),
                bfg_blocks_count=len(bfg_blocks),
            )
        if function_nodes and not bfg_graphs:
            self.logger.warning(
                "semantic_ir_no_bfg_graphs",
                phase="phase_2a_validation",
                message="Document has functions but no BFG graphs generated",
            )
        if bfg_graphs and not bfg_blocks:
            self.logger.error(
                "semantic_ir_bfg_integrity_error",
                phase="phase_2a_validation",
                message="BFG graphs exist but no blocks - critical builder error",
            )
            raise ValueError("BFG builder produced graphs but no blocks. Pipeline integrity compromised.")

        return bfg_graphs, bfg_blocks

    def _build_phase2b_cfg(self, bfg_graphs: list, bfg_blocks: list, source_map: dict) -> tuple[list, list, list]:
        """
        Phase 2b: Build CFG (Control Flow Graph) from BFG.

        Args:
            bfg_graphs: BFG graphs
            bfg_blocks: BFG blocks
            source_map: Source file map

        Returns:
            Tuple of (cfg_graphs, cfg_blocks, cfg_edges)
        """
        if self._performance_monitor:
            with self._performance_monitor.stage("Phase 2b: CFG (Control Flow)"):
                cfg_graphs, cfg_blocks, cfg_edges = self.cfg_builder.build_from_bfg(bfg_graphs, bfg_blocks, source_map)
                self._performance_monitor.record_items(len(cfg_edges))
        else:
            cfg_graphs, cfg_blocks, cfg_edges = self.cfg_builder.build_from_bfg(bfg_graphs, bfg_blocks, source_map)

        if _DEBUG_ENABLED:
            self.logger.debug(
                "semantic_ir_cfg_generated",
                phase="phase_2b_validation",
                cfg_graphs_count=len(cfg_graphs),
                cfg_blocks_count=len(cfg_blocks),
                cfg_edges_count=len(cfg_edges),
            )
        if bfg_graphs and not cfg_graphs:
            self.logger.warning(
                "semantic_ir_cfg_empty",
                phase="phase_2b_validation",
                bfg_graphs_count=len(bfg_graphs),
                message="BFG has graphs but CFG has 0 - check entry/exit blocks",
            )
        if cfg_graphs and not cfg_edges:
            self.logger.warning(
                "semantic_ir_cfg_no_edges",
                phase="phase_2b_validation",
                cfg_graphs_count=len(cfg_graphs),
                message="CFG has graphs but no edges",
            )

        return cfg_graphs, cfg_blocks, cfg_edges

    def _build_phase2c_expressions(self, ir_doc: IRDocument, bfg_blocks: list, source_map: dict) -> list:
        """
        Phase 2c: Build Expression IR from BFG blocks.

        Args:
            bfg_blocks: BFG blocks
            source_map: Source file map

        Returns:
            List of expressions
        """
        if self._performance_monitor:
            with self._performance_monitor.stage("Phase 2c: Expression IR"):
                expressions = self._build_expressions_from_blocks(ir_doc, bfg_blocks, source_map)
                self._performance_monitor.record_items(len(expressions))
                if hasattr(self.expression_builder, "get_cache_stats"):
                    self._performance_monitor.record_cache_stats(self.expression_builder.get_cache_stats())
        else:
            expressions = self._build_expressions_from_blocks(ir_doc, bfg_blocks, source_map)

        if _DEBUG_ENABLED:
            self.logger.debug(
                "semantic_ir_expressions_for_dfg",
                phase="phase_2c_validation",
                expressions_count=len(expressions),
            )
        if bfg_blocks and not expressions and source_map:
            self.logger.warning(
                "semantic_ir_no_expressions",
                phase="phase_2c_validation",
                message="BFG blocks exist and source_map provided, but no expressions generated",
            )

        return expressions

    def _link_types_to_expressions(self, expressions: list, types: list, ir_doc: IRDocument | None = None) -> int:
        """
        Phase 2d: Link expressions to TypeEntity objects.

        Enhanced with cross-file import resolution when ir_doc is provided.

        Args:
            expressions: List of expressions
            types: List of types
            ir_doc: Optional IR document for cross-file import resolution

        Returns:
            Number of linked expressions
        """
        linked_count = 0

        if self._performance_monitor:
            with self._performance_monitor.stage("Phase 2d: Type Linking"):
                if expressions and types:
                    type_linker = TypeLinker()
                    # Build import map for cross-file resolution
                    if ir_doc:
                        type_linker.build_import_map(ir_doc)
                    linked_count = type_linker.link_expressions_to_types(expressions, types)
                    stats = type_linker.get_stats()
                    if _DEBUG_ENABLED:
                        self.logger.debug(
                            f"[Validation] Type linking: {linked_count}/{len(expressions)} expressions linked "
                            f"(direct={stats['direct_matches']}, fqn={stats['fqn_matches']}, "
                            f"import={stats['import_resolved']}, unresolved={stats['unresolved']})"
                        )
                    self._performance_monitor.record_items(linked_count)
        else:
            if expressions and types:
                type_linker = TypeLinker()
                # Build import map for cross-file resolution
                if ir_doc:
                    type_linker.build_import_map(ir_doc)
                linked_count = type_linker.link_expressions_to_types(expressions, types)
                stats = type_linker.get_stats()
                if _DEBUG_ENABLED:
                    self.logger.debug(
                        "semantic_ir_type_linking_stats",
                        phase="phase_2d_validation",
                        linked_count=linked_count,
                        total_expressions=len(expressions),
                        direct_matches=stats["direct_matches"],
                        fqn_matches=stats["fqn_matches"],
                        import_resolved=stats["import_resolved"],
                        unresolved=stats["unresolved"],
                    )

        return linked_count

    def _build_phase3_dfg(self, ir_doc: IRDocument, bfg_blocks: list, expressions: list):
        """
        Phase 3: Build DFG (Data Flow Graph).

        Args:
            ir_doc: IR document
            bfg_blocks: BFG blocks
            expressions: List of expressions

        Returns:
            DFG snapshot
        """
        if self._performance_monitor:
            with self._performance_monitor.stage("Phase 3: DFG (Data Flow)"):
                dfg_snapshot = self.dfg_builder.build_full(ir_doc, bfg_blocks, expressions)
                if dfg_snapshot:
                    self._performance_monitor.record_items(len(dfg_snapshot.variables))

                # Record DFG-specific metrics
                dfg_metrics = self.dfg_builder.get_metrics()
                metrics_summary = dfg_metrics.get_summary()
                if _DEBUG_ENABLED:
                    self.logger.debug(
                        f"[DFG Detailed Metrics]\n"
                        f"  Expression grouping: {metrics_summary['expression_grouping_ms']:.2f}ms\n"
                        f"  Block grouping: {metrics_summary['block_grouping_ms']:.2f}ms\n"
                        f"  Parameter creation: {metrics_summary['parameter_creation_ms']:.2f}ms\n"
                        f"  Expression processing: {metrics_summary['expression_processing_ms']:.2f}ms\n"
                        f"  Edge generation: {metrics_summary['edge_generation_ms']:.2f}ms\n"
                        f"  Functions: {metrics_summary['total_functions']} "
                        f"({metrics_summary['failed_functions']} failed)\n"
                        f"  Output: {metrics_summary['total_variables']} vars, "
                        f"{metrics_summary['total_events']} events, {metrics_summary['total_edges']} edges"
                    )
        else:
            dfg_snapshot = self.dfg_builder.build_full(ir_doc, bfg_blocks, expressions)

        if dfg_snapshot:
            var_count = len(dfg_snapshot.variables)
            edge_count = len(dfg_snapshot.edges)
            if _DEBUG_ENABLED:
                self.logger.debug(
                    "semantic_ir_dfg_stats",
                    phase="phase_3_validation",
                    variables_count=var_count,
                    edges_count=edge_count,
                )
            if bfg_blocks and var_count == 0:
                self.logger.warning(
                    "semantic_ir_dfg_no_variables",
                    phase="phase_3_validation",
                    message="BFG blocks exist but DFG has no variables tracked",
                )
        else:
            self.logger.warning(
                "semantic_ir_dfg_empty",
                phase="phase_3_validation",
                message="DFG snapshot is None or empty",
            )

        return dfg_snapshot

    def _sync_variables_bfg_to_cfg(self, bfg_blocks: list, cfg_blocks: list) -> tuple[int, int]:
        """
        Sync variable tracking from BFG blocks to CFG blocks.

        Args:
            bfg_blocks: BFG blocks
            cfg_blocks: CFG blocks

        Returns:
            Tuple of (synced_count, failed_count)
        """
        if self._performance_monitor:
            with self._performance_monitor.stage("Variable Sync (BFG→CFG)"):
                synced_count, failed_count = self._do_variable_sync(bfg_blocks, cfg_blocks)
                self._performance_monitor.record_items(synced_count)
                self._performance_monitor.record_failed_items(failed_count)
        else:
            synced_count, failed_count = self._do_variable_sync(bfg_blocks, cfg_blocks)

        if _DEBUG_ENABLED:
            self.logger.debug(
                "semantic_ir_variable_sync_validation",
                phase="validation",
                synced_blocks_count=synced_count,
                failed_blocks_count=failed_count,
            )
        if failed_count > 0:
            self.logger.warning(
                "semantic_ir_sync_failures",
                phase="validation",
                failed_count=failed_count,
                total_cfg_blocks=len(cfg_blocks),
                message="CFG blocks failed to sync with BFG",
            )

        return synced_count, failed_count

    def _do_variable_sync(self, bfg_blocks: list, cfg_blocks: list) -> tuple[int, int]:
        """
        Internal helper for variable sync logic.

        Args:
            bfg_blocks: BFG blocks
            cfg_blocks: CFG blocks

        Returns:
            Tuple of (synced_count, failed_count)
        """
        bfg_blocks_by_id = {block.id: block for block in bfg_blocks}
        synced_count = 0
        failed_count = 0

        for cfg_block in cfg_blocks:
            # Use safe ID conversion utility
            bfg_id = convert_cfg_id_to_bfg_id(cfg_block.id)
            bfg_block = bfg_blocks_by_id.get(bfg_id)
            if bfg_block:
                cfg_block.defined_variable_ids = bfg_block.defined_variable_ids.copy()
                cfg_block.used_variable_ids = bfg_block.used_variable_ids.copy()
                synced_count += 1
            else:
                failed_count += 1
                self.logger.warning(
                    f"[Validation] Failed to find BFG block for CFG block: {cfg_block.id} (expected BFG ID: {bfg_id})"
                )
                if self._performance_monitor:
                    self._performance_monitor.record_error()

        return synced_count, failed_count

    def _validate_final_consistency(
        self, bfg_graphs: list, cfg_graphs: list, cfg_edges: list, function_nodes: list, signatures: list
    ) -> list[str]:
        """
        Validate final data consistency.

        Args:
            bfg_graphs: BFG graphs
            cfg_graphs: CFG graphs
            cfg_edges: CFG edges
            function_nodes: Function nodes
            signatures: Signatures

        Returns:
            List of validation errors
        """
        validation_errors = []

        # Check BFG-CFG consistency
        if len(bfg_graphs) != len(cfg_graphs):
            validation_errors.append(f"BFG-CFG graph count mismatch: {len(bfg_graphs)} BFG vs {len(cfg_graphs)} CFG")

        # Check signature consistency
        if len(function_nodes) > 0 and len(signatures) == 0:
            validation_errors.append(f"Found {len(function_nodes)} functions but 0 signatures")

        # Check block-edge consistency
        if len(cfg_graphs) > 0 and len(cfg_edges) == 0:
            validation_errors.append(f"Found {len(cfg_graphs)} CFG graphs but 0 edges")

        # Log validation errors and record in metrics
        if validation_errors:
            self.logger.error(
                "[Validation] FINAL CHECK FAILED - Data consistency issues detected:\n"
                + "\n".join(f"  - {err}" for err in validation_errors)
            )
            # Record validation errors in metrics
            if self._performance_monitor:
                for err in validation_errors:
                    self._performance_monitor.record_validation_error(err)
            # Don't raise, just log - partial results are better than nothing
        else:
            self.logger.info(
                "semantic_ir_validation_passed",
                phase="final_validation",
                message="Final consistency check passed",
            )

        return validation_errors

    def _generate_performance_report(
        self, ir_doc: IRDocument, cfg_blocks: list, cfg_edges: list, expressions: list, dfg_snapshot
    ) -> None:
        """
        Generate and log performance report.

        Args:
            ir_doc: IR document
            cfg_blocks: CFG blocks
            cfg_edges: CFG edges
            expressions: Expressions
            dfg_snapshot: DFG snapshot
        """
        if self._performance_monitor:
            var_count = len(dfg_snapshot.variables) if dfg_snapshot else 0

            metrics = self._performance_monitor.end_pipeline(
                total_nodes=len(ir_doc.nodes),
                total_blocks=len(cfg_blocks),
                total_edges=len(cfg_edges),
                total_expressions=len(expressions),
                total_variables=var_count,
            )

            # Log formatted performance report
            self.logger.info("\n" + metrics.format_report())

    # ================================================================
    # RFC-036: Tier-Aware DFG Building
    # ================================================================

    def _build_phase3_dfg_with_tier(
        self,
        ir_doc: IRDocument,
        bfg_blocks: list,
        expressions: list,
        build_config: "BuildConfig | None" = None,
    ):
        """
        RFC-036: Build DFG with tier-aware threshold.

        Tier behavior:
        - BASE: No DFG (returns None)
        - EXTENDED: DFG with function LOC threshold (skip huge functions)
        - FULL: DFG for all functions (no threshold)

        Args:
            ir_doc: IR document
            bfg_blocks: BFG blocks
            expressions: List of expressions
            build_config: Build configuration (optional, for threshold)

        Returns:
            DFG snapshot (or None if BASE tier)
        """
        # Import here to avoid circular dependency
        from codegraph_engine.code_foundation.infrastructure.ir.build_config import SemanticTier

        # Determine tier
        tier = build_config.semantic_tier if build_config else SemanticTier.FULL

        # BASE tier: No DFG
        if tier == SemanticTier.BASE:
            if _DEBUG_ENABLED:
                self.logger.debug("RFC-036: Skipping DFG (BASE tier)")
            return None

        # EXTENDED tier: DFG with threshold
        if tier == SemanticTier.EXTENDED:
            threshold = build_config.dfg_function_loc_threshold if build_config else 500
            return self._build_dfg_with_threshold(ir_doc, bfg_blocks, expressions, threshold)

        # FULL tier: DFG for all functions (no threshold)
        return self._build_phase3_dfg(ir_doc, bfg_blocks, expressions)

    def _build_dfg_with_threshold(
        self,
        ir_doc: IRDocument,
        bfg_blocks: list,  # Type: list[BfgBlock] but avoid circular import
        expressions: list,  # Type: list[Expression] but avoid circular import
        threshold: int,
    ):
        """
        RFC-036: Build DFG with function LOC threshold.

        Skips DFG for functions exceeding LOC threshold.

        Args:
            ir_doc: IR document
            bfg_blocks: BFG blocks (list of BfgBlock)
            expressions: List of expressions (list of Expression)
            threshold: Maximum LOC for DFG building (must be > 0)

        Returns:
            DFG snapshot with filtered functions (or None if no blocks)

        Raises:
            ValueError: If threshold <= 0
        """
        # SOTA: Validate inputs
        if threshold <= 0:
            raise ValueError(f"threshold must be > 0, got {threshold}")

        # SOTA: Handle empty input gracefully
        if not bfg_blocks:
            if _DEBUG_ENABLED:
                self.logger.debug("RFC-036: No BFG blocks, skipping DFG build")
            return None

        # Group BFG blocks by function
        # BFG block ID format: "bfg_block:function_id:block_num"
        # SOTA: Use constant for ID prefix (no magic strings)
        BFG_BLOCK_PREFIX = "bfg_block"

        function_blocks: dict[str, list] = {}
        unparseable_blocks = []

        for block in bfg_blocks:
            # Extract function ID from BFG block ID
            # Format: "bfg_block:function_id:block_num"
            parts = block.id.split(":")
            if len(parts) >= 3 and parts[0] == BFG_BLOCK_PREFIX:
                # Reconstruct function ID (may contain colons)
                func_id = ":".join(parts[1:-1])
                if func_id not in function_blocks:
                    function_blocks[func_id] = []
                function_blocks[func_id].append(block)
            else:
                # SOTA: Track unparseable blocks (potential data loss)
                unparseable_blocks.append(block)

        # SOTA: Warn about unparseable blocks
        if unparseable_blocks:
            self.logger.warning(
                f"RFC-036: {len(unparseable_blocks)} BFG blocks have unexpected ID format, "
                f"including them in DFG (safe default). "
                f"Sample IDs: {[b.id for b in unparseable_blocks[:3]]}"
            )

        # Filter functions by LOC
        filtered_blocks = []
        skipped_count = 0
        built_count = 0
        zero_loc_count = 0

        for func_id, blocks in function_blocks.items():
            # Get function node from IR
            func_node = next((n for n in ir_doc.nodes if n.id == func_id), None)
            if not func_node:
                # No node found, include blocks (safe default)
                # SOTA: Log warning for debugging
                if _DEBUG_ENABLED:
                    self.logger.warning(
                        f"RFC-036: Function node not found for {func_id}, including {len(blocks)} blocks (safe default)"
                    )
                filtered_blocks.extend(blocks)
                built_count += 1
                continue

            # Calculate function LOC
            func_loc = self._calculate_function_loc(func_node)

            # SOTA: Track zero-LOC functions (potential data quality issue)
            if func_loc == 0:
                zero_loc_count += 1
                if _DEBUG_ENABLED:
                    self.logger.debug(
                        f"RFC-036: Function {func_node.name} has 0 LOC (missing/invalid span), "
                        f"including in DFG (safe default)"
                    )

            # Check threshold (0 LOC functions are always included)
            if func_loc > threshold:
                if _DEBUG_ENABLED:
                    self.logger.debug(
                        f"RFC-036: Skipping DFG for {func_node.name} ({func_loc} LOC > {threshold} threshold)"
                    )
                skipped_count += 1
                continue

            # Include blocks
            filtered_blocks.extend(blocks)
            built_count += 1

        # SOTA: Include unparseable blocks (safe default to avoid data loss)
        if unparseable_blocks:
            filtered_blocks.extend(unparseable_blocks)

        # Log statistics
        total_functions = built_count + skipped_count
        self.logger.info(
            f"RFC-036: DFG built for {built_count}/{total_functions} functions, "
            f"skipped {skipped_count} (LOC threshold={threshold}), "
            f"zero-LOC: {zero_loc_count}, unparseable: {len(unparseable_blocks)}"
        )

        # SOTA: Comprehensive observability
        record_counter("rfc036_dfg_functions_built", value=built_count)
        record_counter("rfc036_dfg_functions_skipped", value=skipped_count)
        record_counter("rfc036_dfg_functions_zero_loc", value=zero_loc_count)
        record_counter("rfc036_dfg_blocks_unparseable", value=len(unparseable_blocks))
        record_histogram("rfc036_dfg_threshold_value", threshold)

        if total_functions > 0:
            skip_rate = skipped_count / total_functions
            record_histogram("rfc036_dfg_skip_rate_percent", int(skip_rate * 100))

        # SOTA: Handle case where all functions were skipped
        if not filtered_blocks:
            self.logger.info(f"RFC-036: All {total_functions} functions exceeded threshold, returning empty DFG")
            return None

        # Build DFG with filtered blocks
        if self._performance_monitor:
            with self._performance_monitor.stage("Phase 3: DFG (Data Flow, Threshold)"):
                dfg_snapshot = self.dfg_builder.build_full(ir_doc, filtered_blocks, expressions)
                if dfg_snapshot:
                    self._performance_monitor.record_items(len(dfg_snapshot.variables))
        else:
            dfg_snapshot = self.dfg_builder.build_full(ir_doc, filtered_blocks, expressions)

        return dfg_snapshot

    def _calculate_function_loc(self, func_node) -> int:
        """
        Calculate Lines of Code for a function node.

        Args:
            func_node: Function/Method node

        Returns:
            LOC count (0 if span is missing)
        """
        if not func_node.span:
            return 0

        return func_node.span.end_line - func_node.span.start_line + 1
