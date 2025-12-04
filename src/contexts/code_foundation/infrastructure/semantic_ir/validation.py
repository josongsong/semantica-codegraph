"""
Pipeline Validation System

Provides:
- Stage output validation
- Data consistency checks
- Completeness verification
- Performance sanity checks

SOTA Features:
- Comprehensive validation rules
- Clear error messages
- Performance impact detection
- Automatic data repair suggestions
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.dfg.models import DfgSnapshot
    from src.contexts.code_foundation.infrastructure.ir.models import IRDocument
    from src.contexts.code_foundation.infrastructure.semantic_ir.bfg.models import BasicFlowBlock, BasicFlowGraph
    from src.contexts.code_foundation.infrastructure.semantic_ir.cfg.models import (
        ControlFlowBlock,
        ControlFlowEdge,
        ControlFlowGraph,
    )
    from src.contexts.code_foundation.infrastructure.semantic_ir.context import SemanticIrSnapshot


# ============================================================
# Validation Result
# ============================================================


@dataclass
class ValidationIssue:
    """Single validation issue"""

    severity: str  # "error", "warning", "info"
    stage: str
    message: str
    details: dict = field(default_factory=dict)
    suggestion: str | None = None

    def __str__(self) -> str:
        parts = [f"[{self.severity.upper()}]", f"{self.stage}:", self.message]
        if self.suggestion:
            parts.append(f"→ {self.suggestion}")
        return " ".join(parts)


@dataclass
class ValidationResult:
    """Validation result with all issues"""

    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no errors)"""
        return not self.has_errors

    @property
    def has_errors(self) -> bool:
        """Check if any errors found"""
        return any(issue.severity == "error" for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        """Check if any warnings found"""
        return any(issue.severity == "warning" for issue in self.issues)

    @property
    def error_count(self) -> int:
        """Count errors"""
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        """Count warnings"""
        return sum(1 for issue in self.issues if issue.severity == "warning")

    def add_error(self, stage: str, message: str, **kwargs) -> None:
        """Add error issue"""
        self.issues.append(ValidationIssue(severity="error", stage=stage, message=message, **kwargs))

    def add_warning(self, stage: str, message: str, **kwargs) -> None:
        """Add warning issue"""
        self.issues.append(ValidationIssue(severity="warning", stage=stage, message=message, **kwargs))

    def add_info(self, stage: str, message: str, **kwargs) -> None:
        """Add info issue"""
        self.issues.append(ValidationIssue(severity="info", stage=stage, message=message, **kwargs))

    def merge(self, other: "ValidationResult") -> None:
        """Merge another validation result"""
        self.issues.extend(other.issues)

    def __str__(self) -> str:
        if self.is_valid:
            return "Validation passed"
        return f"Validation failed: {self.error_count} errors, {self.warning_count} warnings\n" + "\n".join(
            str(issue) for issue in self.issues
        )


# ============================================================
# Stage Validators
# ============================================================


class IRValidator:
    """Validate IR document"""

    @staticmethod
    def validate(ir_doc: "IRDocument") -> ValidationResult:
        """
        Validate IR document.

        Checks:
        - Non-empty
        - Has nodes
        - Nodes have required fields
        - Edge integrity
        """
        result = ValidationResult()

        if not ir_doc:
            result.add_error(
                "IR",
                "IRDocument is None",
                suggestion="Check parser and IR builder",
            )
            return result

        # Check nodes exist
        if not ir_doc.nodes:
            result.add_error(
                "IR",
                "IRDocument has no nodes",
                details={"repo_id": ir_doc.repo_id, "snapshot_id": ir_doc.snapshot_id},
                suggestion="Check if files were parsed correctly",
            )
            return result

        # Check node integrity
        node_ids = set()
        for i, node in enumerate(ir_doc.nodes):
            # Check required fields
            if not node.id:
                result.add_error("IR", f"Node {i} has no ID")
            if not node.kind:
                result.add_error("IR", f"Node {node.id} has no kind")
            if not node.name:
                result.add_warning("IR", f"Node {node.id} has no name")

            node_ids.add(node.id)

        # Check edge integrity
        for edge in ir_doc.edges:
            if edge.source_id not in node_ids:
                result.add_error(
                    "IR",
                    f"Edge references non-existent source: {edge.source_id}",
                    suggestion="Check IR edge generation",
                )
            if edge.target_id not in node_ids:
                result.add_error(
                    "IR",
                    f"Edge references non-existent target: {edge.target_id}",
                    suggestion="Check IR edge generation",
                )

        # Info: Statistics
        result.add_info(
            "IR",
            f"IR validation complete: {len(ir_doc.nodes)} nodes, {len(ir_doc.edges)} edges",
        )

        return result


class BFGValidator:
    """Validate BFG (Basic Flow Graph)"""

    @staticmethod
    def validate(bfg_graphs: list["BasicFlowGraph"], bfg_blocks: list["BasicFlowBlock"]) -> ValidationResult:
        """
        Validate BFG output.

        Checks:
        - Graphs and blocks exist
        - Each graph has entry and exit blocks
        - Block integrity
        - No orphaned blocks
        """
        result = ValidationResult()

        # Check graphs exist
        if not bfg_graphs and bfg_blocks:
            result.add_error(
                "BFG",
                f"BFG builder produced {len(bfg_blocks)} blocks but no graphs",
                details={"blocks": len(bfg_blocks)},
                suggestion="Check BFG graph generation logic",
            )
            return result

        # Build block index
        blocks_by_id = {block.id: block for block in bfg_blocks}
        blocks_by_function = {}
        for block in bfg_blocks:
            func_id = block.function_node_id
            if func_id not in blocks_by_function:
                blocks_by_function[func_id] = []
            blocks_by_function[func_id].append(block)

        # Validate each graph
        for graph in bfg_graphs:
            # Check entry/exit blocks
            if not graph.entry_block_id:
                result.add_error(
                    "BFG",
                    f"Graph {graph.id} has no entry block",
                    details={"function": graph.function_node_id},
                    suggestion="Ensure entry block is created",
                )

            if not graph.exit_block_id:
                result.add_error(
                    "BFG",
                    f"Graph {graph.id} has no exit block",
                    details={"function": graph.function_node_id},
                    suggestion="Ensure exit block is created",
                )

            # Check blocks reference
            if graph.entry_block_id and graph.entry_block_id not in blocks_by_id:
                result.add_error(
                    "BFG",
                    f"Graph {graph.id} references non-existent entry block: {graph.entry_block_id}",
                )

            if graph.exit_block_id and graph.exit_block_id not in blocks_by_id:
                result.add_error(
                    "BFG",
                    f"Graph {graph.id} references non-existent exit block: {graph.exit_block_id}",
                )

            # Check function has blocks
            func_blocks = blocks_by_function.get(graph.function_node_id, [])
            if len(func_blocks) < 2:  # At least entry + exit
                result.add_warning(
                    "BFG",
                    f"Function {graph.function_node_id} has only {len(func_blocks)} blocks",
                    suggestion="Check if function body was parsed correctly",
                )

        # Check for orphaned blocks
        graphed_functions = {g.function_node_id for g in bfg_graphs}
        orphaned_blocks = [b for b in bfg_blocks if b.function_node_id not in graphed_functions]
        if orphaned_blocks:
            result.add_warning(
                "BFG",
                f"{len(orphaned_blocks)} orphaned blocks without graphs",
                details={"orphaned": len(orphaned_blocks)},
            )

        # Info: Statistics
        result.add_info(
            "BFG",
            f"BFG validation complete: {len(bfg_graphs)} graphs, {len(bfg_blocks)} blocks",
        )

        return result


class CFGValidator:
    """Validate CFG (Control Flow Graph)"""

    @staticmethod
    def validate(
        cfg_graphs: list["ControlFlowGraph"],
        cfg_blocks: list["ControlFlowBlock"],
        cfg_edges: list["ControlFlowEdge"],
        bfg_graphs: list["BasicFlowGraph"] | None = None,
    ) -> ValidationResult:
        """
        Validate CFG output.

        Checks:
        - Graphs and blocks exist
        - Entry/exit blocks present
        - Edge integrity
        - Consistency with BFG (if provided)
        """
        result = ValidationResult()

        # Check graphs exist
        if not cfg_graphs and cfg_blocks:
            result.add_error(
                "CFG",
                f"CFG produced {len(cfg_blocks)} blocks but no graphs",
                details={"blocks": len(cfg_blocks)},
                suggestion="Check CFG graph generation",
            )
            return result

        # Build indexes
        blocks_by_id = {block.id: block for block in cfg_blocks}
        blocks_by_function = {}
        for block in cfg_blocks:
            func_id = block.function_node_id
            if func_id not in blocks_by_function:
                blocks_by_function[func_id] = []
            blocks_by_function[func_id].append(block)

        # Validate each graph
        for graph in cfg_graphs:
            # Check entry/exit blocks
            if not graph.entry_block_id or graph.entry_block_id not in blocks_by_id:
                result.add_error(
                    "CFG",
                    f"Graph {graph.id} missing or invalid entry block",
                    details={"entry_id": graph.entry_block_id},
                    suggestion="Check CFG entry block generation",
                )

            if not graph.exit_block_id or graph.exit_block_id not in blocks_by_id:
                result.add_error(
                    "CFG",
                    f"Graph {graph.id} missing or invalid exit block",
                    details={"exit_id": graph.exit_block_id},
                    suggestion="Check CFG exit block generation",
                )

        # Validate edges
        for edge in cfg_edges:
            if edge.source_id not in blocks_by_id:
                result.add_error(
                    "CFG",
                    f"Edge references non-existent source block: {edge.source_id}",
                )
            if edge.target_id not in blocks_by_id:
                result.add_error(
                    "CFG",
                    f"Edge references non-existent target block: {edge.target_id}",
                )

        # Check BFG-CFG consistency
        if bfg_graphs is not None:
            if len(bfg_graphs) != len(cfg_graphs):
                result.add_warning(
                    "CFG",
                    f"BFG-CFG count mismatch: {len(bfg_graphs)} BFG → {len(cfg_graphs)} CFG",
                    suggestion="Some functions may have failed CFG conversion",
                )

        # Info: Statistics
        result.add_info(
            "CFG",
            f"CFG validation complete: {len(cfg_graphs)} graphs, {len(cfg_blocks)} blocks, {len(cfg_edges)} edges",
        )

        return result


class DFGValidator:
    """Validate DFG (Data Flow Graph)"""

    @staticmethod
    def validate(dfg_snapshot: "DfgSnapshot") -> ValidationResult:
        """
        Validate DFG snapshot.

        Checks:
        - Variables exist
        - Events reference valid variables
        - Edges reference valid variables
        """
        result = ValidationResult()

        if not dfg_snapshot:
            result.add_warning("DFG", "DFG snapshot is None or empty")
            return result

        # Build variable index
        var_ids = {var.id for var in dfg_snapshot.variables}

        # Validate events
        for event in dfg_snapshot.events:
            if event.variable_id not in var_ids:
                result.add_error(
                    "DFG",
                    f"Event references non-existent variable: {event.variable_id}",
                )

        # Validate edges
        for edge in dfg_snapshot.edges:
            if edge.source_id not in var_ids:
                result.add_warning(
                    "DFG",
                    f"Edge references non-existent source variable: {edge.source_id}",
                )
            if edge.target_id not in var_ids:
                result.add_warning(
                    "DFG",
                    f"Edge references non-existent target variable: {edge.target_id}",
                )

        # Info: Statistics
        result.add_info(
            "DFG",
            f"DFG validation complete: {len(dfg_snapshot.variables)} vars, "
            f"{len(dfg_snapshot.events)} events, {len(dfg_snapshot.edges)} edges",
        )

        return result


class SemanticIRValidator:
    """Validate complete Semantic IR snapshot"""

    @staticmethod
    def validate(snapshot: "SemanticIrSnapshot") -> ValidationResult:
        """
        Validate complete semantic IR snapshot.

        Runs all sub-validators and aggregates results.
        """
        result = ValidationResult()

        # Validate BFG
        bfg_result = BFGValidator.validate(snapshot.bfg_graphs, snapshot.bfg_blocks)
        result.merge(bfg_result)

        # Validate CFG
        cfg_result = CFGValidator.validate(
            snapshot.cfg_graphs,
            snapshot.cfg_blocks,
            snapshot.cfg_edges,
            bfg_graphs=snapshot.bfg_graphs,
        )
        result.merge(cfg_result)

        # Validate DFG
        if snapshot.dfg_snapshot:
            dfg_result = DFGValidator.validate(snapshot.dfg_snapshot)
            result.merge(dfg_result)

        # Overall consistency checks
        if snapshot.types and snapshot.signatures:
            result.add_info(
                "SemanticIR",
                f"Semantic IR complete: {len(snapshot.types)} types, {len(snapshot.signatures)} signatures",
            )

        return result


# ============================================================
# Pipeline Validator (Complete)
# ============================================================


class PipelineValidator:
    """
    Complete pipeline validator.

    Validates entire pipeline from IR to Semantic IR.
    """

    @staticmethod
    def validate_full_pipeline(
        ir_doc: "IRDocument",
        semantic_snapshot: "SemanticIrSnapshot",
    ) -> ValidationResult:
        """
        Validate full pipeline output.

        Args:
            ir_doc: IR document
            semantic_snapshot: Semantic IR snapshot

        Returns:
            Aggregated validation result
        """
        result = ValidationResult()

        # Validate IR
        ir_result = IRValidator.validate(ir_doc)
        result.merge(ir_result)

        # If IR validation failed, abort
        if ir_result.has_errors:
            result.add_error(
                "Pipeline",
                "IR validation failed, aborting further validation",
                suggestion="Fix IR issues first",
            )
            return result

        # Validate Semantic IR
        semantic_result = SemanticIRValidator.validate(semantic_snapshot)
        result.merge(semantic_result)

        return result
