"""
Semantic IR Builder

Orchestrates all semantic IR builders (Type, Signature, CFG, DFG).

Phase 1: Type + Signature
Phase 2: + CFG
Phase 3: + DFG
"""

from typing import TYPE_CHECKING, Protocol

from ..ir.models import IRDocument
from .cfg.builder import CfgIrBuilder
from .context import (
    SemanticIndex,
    SemanticIrSnapshot,
    SignatureIndex,
    TypeIndex,
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

    def build_full(
        self, ir_doc: IRDocument
    ) -> tuple[SemanticIrSnapshot, SemanticIndex]:
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

    Orchestrates type, signature, CFG, and DFG builders.

    Phase 1: Type + Signature only
    Phase 2: + CFG
    Phase 3: + DFG
    """

    def __init__(
        self,
        type_builder: TypeIrBuilder | None = None,
        signature_builder: SignatureIrBuilder | None = None,
        cfg_builder: CfgIrBuilder | None = None,  # Phase 2 ✅
        # dfg_builder: DfgIrBuilder | None = None,  # Phase 3
    ):
        """
        Initialize with sub-builders.

        Args:
            type_builder: Type system builder
            signature_builder: Signature builder
            cfg_builder: CFG builder
        """
        self.type_builder = type_builder or TypeIrBuilder()
        self.signature_builder = signature_builder or SignatureIrBuilder()
        self.cfg_builder = cfg_builder or CfgIrBuilder()

    def build_full(
        self, ir_doc: IRDocument, source_map: dict[str, "SourceFile"] | None = None
    ) -> tuple[SemanticIrSnapshot, SemanticIndex]:
        """
        Build complete semantic IR from structural IR.

        Phase 1: Type + Signature
        Phase 2: + CFG
        Phase 3: + DFG

        Args:
            ir_doc: Structural IR document
            source_map: Optional mapping of file_path -> SourceFile for enhanced CFG

        Returns:
            (semantic_snapshot, semantic_index)
        """
        # Phase 1: Type System
        types, type_index = self.type_builder.build_full(ir_doc)

        # Phase 1: Signatures
        signatures, signature_index = self.signature_builder.build_full(ir_doc)

        # Phase 2: CFG
        # If source_map provided, use enhanced CFG with AST analysis
        # Otherwise, generate simplified CFG (Entry -> Body -> Exit)
        if source_map is None:
            source_map = {}
        cfg_graphs, cfg_blocks, cfg_edges = self.cfg_builder.build_full(
            ir_doc, source_map
        )

        # Phase 3: DFG (TODO)
        # variables, events, dfg_edges, var_index = self.dfg_builder.build_full(...)

        # Build semantic snapshot
        semantic_snapshot = SemanticIrSnapshot(
            types=types,
            signatures=signatures,
            # Phase 2
            cfg_graphs=cfg_graphs,
            cfg_blocks=cfg_blocks,
            cfg_edges=cfg_edges,
            # Phase 3
            # variables=variables,
            # read_write_events=events,
            # dataflow_edges=dfg_edges,
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
