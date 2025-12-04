"""
Semantic IR Builder

Orchestrates all semantic IR builders (Type, Signature, BFG, CFG, DFG).

Phase 1: Type + Signature
Phase 2: + BFG (Basic Blocks) + CFG (Control Flow Edges)
Phase 3: + DFG
"""

from typing import TYPE_CHECKING, Protocol

from src.common.observability import get_logger, record_counter, record_histogram
from src.contexts.code_foundation.infrastructure.dfg.builder import DfgBuilder
from src.contexts.code_foundation.infrastructure.ir.models import IRDocument
from src.contexts.code_foundation.infrastructure.semantic_ir.bfg.builder import BfgBuilder
from src.contexts.code_foundation.infrastructure.semantic_ir.cfg.builder import CfgBuilder
from src.contexts.code_foundation.infrastructure.semantic_ir.context import (
    SemanticIndex,
    SemanticIrSnapshot,
)
from src.contexts.code_foundation.infrastructure.semantic_ir.expression.builder import ExpressionBuilder
from src.contexts.code_foundation.infrastructure.semantic_ir.id_utils import convert_cfg_id_to_bfg_id, extract_file_path
from src.contexts.code_foundation.infrastructure.semantic_ir.performance_monitor import PerformanceMonitor
from src.contexts.code_foundation.infrastructure.semantic_ir.signature.builder import SignatureIrBuilder
from src.contexts.code_foundation.infrastructure.semantic_ir.type_linker import TypeLinker
from src.contexts.code_foundation.infrastructure.semantic_ir.typing.builder import TypeIrBuilder

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile


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
        bfg_builder: BfgBuilder | None = None,  # Phase 2 ✅
        cfg_builder: CfgBuilder | None = None,  # Phase 2 ✅
        expression_builder: ExpressionBuilder | None = None,  # Phase 3 ✅
        dfg_builder: DfgBuilder | None = None,  # Phase 3 ✅
        enable_performance_monitoring: bool = False,
    ):
        """
        Initialize with sub-builders.

        Args:
            type_builder: Type system builder
            signature_builder: Signature builder
            bfg_builder: BFG builder (basic blocks)
            cfg_builder: CFG builder (control flow edges)
            expression_builder: Expression builder (for DFG)
            dfg_builder: DFG builder
            enable_performance_monitoring: Enable detailed performance tracking
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

        # Initialize performance monitor
        self.enable_performance_monitoring = enable_performance_monitoring
        self._performance_monitor = (
            PerformanceMonitor(enable_memory_tracking=True) if enable_performance_monitoring else None
        )

        self.logger.debug(
            "semantic_ir_builder_initialized",
            enable_performance_monitoring=enable_performance_monitoring,
            has_type_builder=type_builder is not None,
            has_signature_builder=signature_builder is not None,
            has_bfg_builder=bfg_builder is not None,
            has_cfg_builder=cfg_builder is not None,
            has_expression_builder=expression_builder is not None,
            has_dfg_builder=dfg_builder is not None,
        )
        record_counter("semantic_ir_builder_initialized_total")

    def build_full(
        self, ir_doc: IRDocument, source_map: dict[str, tuple["SourceFile", "AstTree"]] | None = None
    ) -> tuple[SemanticIrSnapshot, SemanticIndex]:
        """
        Build complete semantic IR from structural IR.

        Refactored to use phase-specific helper methods for better maintainability.
        Reduced from 275 lines → ~70 lines (75% reduction).

        Phase 1: Type + Signature
        Phase 2: + BFG + CFG + Expressions + Type Linking
        Phase 3: + DFG + Variable Sync

        Args:
            ir_doc: Structural IR document
            source_map: Optional mapping of file_path -> (SourceFile, AstTree) for enhanced analysis
                       Pre-parsed AST prevents duplicate parsing (60-70% performance improvement)

        Returns:
            (semantic_snapshot, semantic_index)

        Raises:
            ValueError: If IR document is invalid or pipeline validation fails
        """
        self.logger.info(
            "semantic_ir_build_full_started",
            ir_nodes_count=len(ir_doc.nodes) if ir_doc else 0,
            has_source_map=source_map is not None,
            source_files_count=len(source_map) if source_map else 0,
        )
        record_counter("semantic_ir_build_full_total", labels={"type": "full"})

        # Start performance monitoring if enabled
        if self._performance_monitor:
            self._performance_monitor.start_pipeline()

        # Ensure source_map is not None
        if source_map is None:
            source_map = {}

        # === Input Validation ===
        self._validate_ir_document(ir_doc)

        # === Phase 1: Type System & Signatures ===
        types, type_index = self._build_phase1_types(ir_doc)
        signatures, signature_index, function_nodes = self._build_phase1_signatures(ir_doc)

        # === Phase 2: Control Flow & Data Flow ===
        bfg_graphs, bfg_blocks = self._build_phase2a_bfg(ir_doc, source_map, function_nodes)
        cfg_graphs, cfg_blocks, cfg_edges = self._build_phase2b_cfg(bfg_graphs, bfg_blocks, source_map)
        expressions = self._build_phase2c_expressions(bfg_blocks, source_map)
        self._link_types_to_expressions(expressions, types, ir_doc)  # Pass ir_doc for cross-file linking

        # === Phase 3: Data Flow Graph ===
        dfg_snapshot = self._build_phase3_dfg(ir_doc, bfg_blocks, expressions)

        # === Variable Sync (BFG → CFG) ===
        self._sync_variables_bfg_to_cfg(bfg_blocks, cfg_blocks)

        # === Build Results ===
        semantic_snapshot = SemanticIrSnapshot(
            types=types,
            signatures=signatures,
            bfg_graphs=bfg_graphs,
            bfg_blocks=bfg_blocks,
            cfg_graphs=cfg_graphs,
            cfg_blocks=cfg_blocks,
            cfg_edges=cfg_edges,
            dfg_snapshot=dfg_snapshot,
        )

        semantic_index = SemanticIndex(
            type_index=type_index,
            signature_index=signature_index,
        )

        # === Final Validation ===
        self._validate_final_consistency(bfg_graphs, cfg_graphs, cfg_edges, function_nodes, signatures)

        # === Performance Report ===
        self._generate_performance_report(ir_doc, cfg_blocks, cfg_edges, expressions, dfg_snapshot)

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
        )
        record_counter("semantic_ir_build_full_completed_total", labels={"status": "success"})
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

        Returns:
            (new_snapshot, new_index)
        """
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

        # Detect changed functions
        if self._performance_monitor:
            with self._performance_monitor.stage("Detect Changed Functions"):
                changed_function_ids = self._detect_changed_functions(ir_doc, existing_snapshot)
                self._performance_monitor.record_items(len(changed_function_ids))
        else:
            changed_function_ids = self._detect_changed_functions(ir_doc, existing_snapshot)

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
            ir_doc, existing_snapshot, changed_function_ids, source_map or {}
        )

        # Index remains the same for now (could be incrementally updated too)
        # For simplicity, we rebuild type/signature indexes
        if self._performance_monitor:
            with self._performance_monitor.stage("Rebuild Indexes"):
                new_index = SemanticIndex(
                    type_index=self.type_builder._build_index(new_snapshot.types),
                    signature_index=self.signature_builder._build_index(new_snapshot.signatures),
                )
                self._performance_monitor.record_items(len(new_snapshot.signatures))
        else:
            new_index = SemanticIndex(
                type_index=self.type_builder._build_index(new_snapshot.types),
                signature_index=self.signature_builder._build_index(new_snapshot.signatures),
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

    def _detect_changed_functions(self, ir_doc: IRDocument, existing_snapshot: SemanticIrSnapshot) -> set[str]:
        """
        Detect which functions have changed by comparing IR documents.

        Args:
            ir_doc: New IR document
            existing_snapshot: Previous semantic snapshot

        Returns:
            Set of changed function IDs
        """
        changed_function_ids = set()

        # Build existing function map
        existing_functions = {}
        for sig in existing_snapshot.signatures:
            existing_functions[sig.owner_node_id] = sig

        # Check new functions
        new_function_nodes = [n for n in ir_doc.nodes if n.kind.name in ("FUNCTION", "METHOD")]

        new_functions_count = 0
        modified_functions_count = 0

        for func_node in new_function_nodes:
            func_id = func_node.id
            existing_sig = existing_functions.get(func_id)

            if not existing_sig:
                # New function
                self.logger.debug("semantic_ir_new_function_detected", function_id=func_id)
                changed_function_ids.add(func_id)
                new_functions_count += 1
            else:
                # Compare function signature/body
                # Simple heuristic: compare span and name
                if self._function_has_changed(func_node, existing_sig):
                    self.logger.debug("semantic_ir_changed_function_detected", function_id=func_id)
                    changed_function_ids.add(func_id)
                    modified_functions_count += 1

        # Check deleted functions
        new_function_ids = {n.id for n in new_function_nodes}
        deleted_functions_count = 0
        for existing_func_id in existing_functions.keys():
            if existing_func_id not in new_function_ids:
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

        Uses simple heuristics for change detection:
        - Function name: If renamed, function changed
        - Signature raw string: If signature changed, function changed

        Args:
            func_node: New function node from IR
            existing_sig: Existing SignatureEntity

        Returns:
            True if function has changed, False otherwise
        """
        # Compare name - if renamed, function changed
        if func_node.name != existing_sig.name:
            return True

        # Compare signature ID if available (signature ID encodes the full signature)
        # If signature_id changed, the signature changed
        if hasattr(func_node, "signature_id") and func_node.signature_id:
            if func_node.signature_id != existing_sig.id:
                return True

        # If no signature ID to compare, conservatively assume changed
        # This ensures we don't miss changes, at the cost of some redundant rebuilds
        if not hasattr(func_node, "signature_id") or not func_node.signature_id:
            return True

        # If all checks pass, function hasn't changed
        return False

    def _rebuild_changed_functions(
        self,
        ir_doc: IRDocument,
        existing_snapshot: SemanticIrSnapshot,
        changed_function_ids: set[str],
        source_map: dict[str, "SourceFile"],
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
                        func_node, ir_doc, ir_signatures_by_node_id, source_map, expressions
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
                    func_node, ir_doc, ir_signatures_by_node_id, source_map, expressions
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
        if self._performance_monitor:
            with self._performance_monitor.stage("Rebuild DFG"):
                dfg_snapshot = self.dfg_builder.build_full(ir_doc, new_bfg_blocks, expressions)
                if dfg_snapshot:
                    self._performance_monitor.record_items(len(dfg_snapshot.variables))
        else:
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

    def _build_expressions_from_blocks(self, bfg_blocks, source_map):
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

        self.logger.debug(
            "semantic_ir_build_expressions_started",
            phase="phase_2c",
            source_files_count=len(source_map),
            bfg_blocks_count=len(bfg_blocks),
            source_map_keys=list(source_map.keys())[:5],  # Log first 5 keys
        )

        for block in bfg_blocks:
            block_exprs = self._process_block_for_expression(block, source_map)
            expressions.extend(block_exprs)

        self.logger.debug("semantic_ir_expressions_generated", phase="phase_2c", total_expressions=len(expressions))
        record_histogram("semantic_ir_expressions_generated_count", len(expressions))
        return expressions

    def _process_block_for_expression(self, block, source_map):
        """
        Process a single BFG block to extract expressions.

        Uses early-return pattern to reduce nesting:
        - Check if file_path can be extracted (if not, warn and return)
        - Check if file_path exists in source_map (if not, skip and return)
        - Build expressions from block

        Args:
            block: BFG block to process
            source_map: Dict mapping file_path -> (SourceFile, AstTree) or file_path -> SourceFile

        Returns:
            List of expressions extracted from this block
        """

        self.logger.debug(
            "semantic_ir_process_block",
            phase="phase_2c",
            function_node_id=block.function_node_id,
        )

        # Extract file_path using safe parsing utility
        file_path = extract_file_path(block.function_node_id)
        self.logger.debug("semantic_ir_file_path_extracted", phase="phase_2c", file_path=file_path)

        # Early return: file_path extraction failed
        if not file_path:
            self.logger.warning(
                "semantic_ir_file_path_extraction_failed",
                phase="phase_2c",
                function_node_id=block.function_node_id,
            )
            return []

        # Early return: file_path not in source_map
        if file_path not in source_map:
            self.logger.debug(
                "semantic_ir_file_path_not_in_source_map",
                phase="phase_2c",
                file_path=file_path,
                message="Skipping block",
            )
            return []

        # Happy path: build expressions
        # Handle both tuple (SourceFile, AstTree) and plain SourceFile
        source_data = source_map[file_path]
        if isinstance(source_data, tuple):
            source_file, ast_tree = source_data
            # Pass both source_file and pre-parsed AST
            block_exprs = self.expression_builder.build_from_block(block, source_file, ast_tree=ast_tree)
        else:
            source_file = source_data
            block_exprs = self.expression_builder.build_from_block(block, source_file)

        self.logger.debug(
            "semantic_ir_expressions_from_block",
            phase="phase_2c",
            expressions_count=len(block_exprs),
        )
        return block_exprs

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

    def _rebuild_single_function(self, func_node, ir_doc, ir_signatures_by_node_id, source_map, expressions_output):
        """
        Rebuild semantic IR for a single changed function.

        Args:
            func_node: IR function node to rebuild
            ir_doc: IR document
            ir_signatures_by_node_id: Mapping of node IDs to signatures
            source_map: Source file mapping
            expressions_output: List to append expressions to

        Returns:
            Dict with rebuilt entities: signature, bfg/cfg data
        """

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
            result["signature"] = sig

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
        self.logger.debug("semantic_ir_types_generated", phase="phase_1a_validation", types_count=len(types))
        return types, type_index

    def _build_phase1_signatures(self, ir_doc: IRDocument) -> tuple[list, dict, list]:
        """
        Phase 1b: Build function signatures.

        Args:
            ir_doc: IR document

        Returns:
            Tuple of (signatures, signature_index, function_nodes)
        """
        if self._performance_monitor:
            with self._performance_monitor.stage("Phase 1b: Signatures"):
                signatures, signature_index = self.signature_builder.build_full(ir_doc)
                self._performance_monitor.record_items(len(signatures))
        else:
            signatures, signature_index = self.signature_builder.build_full(ir_doc)

        function_nodes = [n for n in ir_doc.nodes if n.kind.name in ("FUNCTION", "METHOD", "LAMBDA")]
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

    def _build_phase2c_expressions(self, bfg_blocks: list, source_map: dict) -> list:
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
                expressions = self._build_expressions_from_blocks(bfg_blocks, source_map)
                self._performance_monitor.record_items(len(expressions))
                if hasattr(self.expression_builder, "get_cache_stats"):
                    self._performance_monitor.record_cache_stats(self.expression_builder.get_cache_stats())
        else:
            expressions = self._build_expressions_from_blocks(bfg_blocks, source_map)

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
