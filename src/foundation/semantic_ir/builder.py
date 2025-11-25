"""
Semantic IR Builder

Orchestrates all semantic IR builders (Type, Signature, BFG, CFG, DFG).

Phase 1: Type + Signature
Phase 2: + BFG (Basic Blocks) + CFG (Control Flow Edges)
Phase 3: + DFG
"""

from typing import TYPE_CHECKING, Protocol

from ..dfg.analyzers import PythonStatementAnalyzer
from ..dfg.builder import DfgBuilder
from ..dfg.statement_analyzer import AnalyzerRegistry
from ..ir.models import IRDocument
from .bfg.builder import BfgBuilder
from .cfg.builder import CfgBuilder
from .context import (
    SemanticIndex,
    SemanticIrSnapshot,
)
from .signature.builder import SignatureIrBuilder
from .typing.builder import TypeIrBuilder

if TYPE_CHECKING:
    from ..parsing import SourceFile


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
        dfg_builder: DfgBuilder | None = None,  # Phase 3 ✅
    ):
        """
        Initialize with sub-builders.

        Args:
            type_builder: Type system builder
            signature_builder: Signature builder
            bfg_builder: BFG builder (basic blocks)
            cfg_builder: CFG builder (control flow edges)
            dfg_builder: DFG builder
        """
        self.type_builder = type_builder or TypeIrBuilder()
        self.signature_builder = signature_builder or SignatureIrBuilder()
        self.bfg_builder = bfg_builder or BfgBuilder()
        self.cfg_builder = cfg_builder or CfgBuilder()

        # Initialize DFG builder with analyzer registry
        if dfg_builder is None:
            analyzer_registry = AnalyzerRegistry()
            analyzer_registry.register("python", PythonStatementAnalyzer())
            dfg_builder = DfgBuilder(analyzer_registry)
        self.dfg_builder = dfg_builder

    def build_full(
        self, ir_doc: IRDocument, source_map: dict[str, "SourceFile"] | None = None
    ) -> tuple[SemanticIrSnapshot, SemanticIndex]:
        """
        Build complete semantic IR from structural IR.

        Phase 1: Type + Signature
        Phase 2: + BFG + CFG
        Phase 3: + DFG

        Args:
            ir_doc: Structural IR document
            source_map: Optional mapping of file_path -> SourceFile for enhanced analysis

        Returns:
            (semantic_snapshot, semantic_index)
        """
        # Phase 1: Type System
        types, type_index = self.type_builder.build_full(ir_doc)

        # Phase 1: Signatures
        signatures, signature_index = self.signature_builder.build_full(ir_doc)

        # Phase 2a: BFG (Basic Block Extraction)
        # If source_map provided, use enhanced BFG with AST analysis
        # Otherwise, generate simplified BFG (Entry -> Body -> Exit)
        if source_map is None:
            source_map = {}
        bfg_graphs, bfg_blocks = self.bfg_builder.build_full(ir_doc, source_map)

        # Phase 2b: CFG (Control Flow Edges)
        # Build CFG from BFG blocks
        cfg_graphs, cfg_blocks, cfg_edges = self.cfg_builder.build_from_bfg(bfg_graphs, bfg_blocks, source_map)

        # Phase 3: DFG (Data Flow Graph)
        # Use BFG blocks for data flow analysis
        dfg_snapshot = self.dfg_builder.build_full(ir_doc, bfg_blocks, cfg_edges, source_map)

        # Build semantic snapshot
        semantic_snapshot = SemanticIrSnapshot(
            types=types,
            signatures=signatures,
            # Phase 2
            bfg_graphs=bfg_graphs,
            bfg_blocks=bfg_blocks,
            cfg_graphs=cfg_graphs,
            cfg_blocks=cfg_blocks,
            cfg_edges=cfg_edges,
            # Phase 3
            dfg_snapshot=dfg_snapshot,
        )

        # Build semantic index
        semantic_index = SemanticIndex(
            type_index=type_index,
            signature_index=signature_index,
        )

        return semantic_snapshot, semantic_index

    def apply_delta(
        self,
        ir_doc: IRDocument,
        existing_snapshot: SemanticIrSnapshot,
        existing_index: SemanticIndex,
        source_map: dict[str, "SourceFile"] | None = None,
    ) -> tuple[SemanticIrSnapshot, SemanticIndex]:
        """
        Apply incremental changes (simplified - full rebuild for now).

        Future: Implement proper delta logic
        - Detect changed functions
        - Only rebuild affected semantic entities
        - Reuse unchanged entities

        Args:
            ir_doc: Updated structural IR
            existing_snapshot: Previous snapshot
            existing_index: Previous index
            source_map: Optional source file map

        Returns:
            (new_snapshot, new_index)
        """
        # For now, just rebuild everything
        # TODO: Implement proper delta logic
        return self.build_full(ir_doc, source_map)
