"""
Occurrence Generator

Generates SCIP-compatible occurrences from IRDocument.

Strategy:
1. Scan all nodes → create DEFINITION occurrences
2. Scan all edges → create REFERENCE/WRITE occurrences
3. Calculate importance scores (ranking signals)
4. Build indexes for fast lookup

Generated occurrences power retrieval queries:
- Find all references to symbol X
- Find all definitions in file Y
- Find all write accesses to variable Z
"""

from typing import TYPE_CHECKING

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.ir.models.core import EdgeKind, NodeKind
from src.contexts.code_foundation.infrastructure.ir.models.occurrence import (
    Occurrence,
    OccurrenceIndex,
    SymbolRole,
    create_definition_occurrence,
)

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.ir.models.core import Edge, Node
    from src.contexts.code_foundation.infrastructure.ir.models.document import IRDocument

logger = get_logger(__name__)


class OccurrenceGenerator:
    """
    Generate SCIP-compatible occurrences from IR.

    Maps:
    - Node (symbol definition) → DEFINITION occurrence
    - Edge (relationship) → REFERENCE/WRITE occurrence

    Also calculates importance scores for ranking.

    Example usage:
        generator = OccurrenceGenerator()
        occurrences, index = generator.generate(ir_doc)

        # Now can query
        refs = index.get_references("class:Calculator")
        defs = index.get_definitions_in_file("src/calc.py")
    """

    def __init__(self):
        self.logger = logger

    def generate(
        self,
        ir_doc: "IRDocument",
    ) -> tuple[list[Occurrence], OccurrenceIndex]:
        """
        Generate all occurrences from IRDocument.

        Args:
            ir_doc: IR document to extract occurrences from

        Returns:
            (occurrences, occurrence_index)
        """
        self.logger.debug(f"Generating occurrences for {len(ir_doc.nodes)} nodes, {len(ir_doc.edges)} edges")

        occurrences: list[Occurrence] = []

        # ============================================================
        # Step 1: Definitions from nodes
        # ============================================================
        for node in ir_doc.nodes:
            if self._is_symbol_node(node):
                occ = self._create_definition_occurrence(node)
                occurrences.append(occ)

        # ============================================================
        # Step 2: References from edges
        # ============================================================
        for edge in ir_doc.edges:
            occ = self._create_reference_occurrence(edge, ir_doc)
            if occ:
                occurrences.append(occ)

        # ============================================================
        # Step 3: Calculate importance scores
        # ============================================================
        self._calculate_importance_scores(occurrences, ir_doc)

        # ============================================================
        # Step 4: Build indexes
        # ============================================================
        index = OccurrenceIndex()
        for occ in occurrences:
            index.add(occ)

        self.logger.info(
            f"Generated {len(occurrences)} occurrences "
            f"({index.definitions_count} definitions, {index.references_count} references)"
        )

        return occurrences, index

    def _is_symbol_node(self, node: "Node") -> bool:
        """
        Check if node represents a symbol (should have definition occurrence).

        Symbol nodes:
        - CLASS, FUNCTION, METHOD, VARIABLE, PARAMETER, etc.

        Not symbol nodes:
        - FILE, MODULE (containers, not symbols themselves)
        - TRY_CATCH, IF_STATEMENT (control flow, not symbols)

        Args:
            node: Node to check

        Returns:
            True if node is a symbol
        """
        symbol_kinds = {
            NodeKind.CLASS,
            NodeKind.FUNCTION,
            NodeKind.METHOD,
            NodeKind.VARIABLE,
            NodeKind.VARIABLE,
            NodeKind.FIELD,
            NodeKind.FIELD,
            NodeKind.METHOD,
            NodeKind.CLASS,
            NodeKind.FIELD,
            NodeKind.INTERFACE,
            NodeKind.CLASS,
            NodeKind.VARIABLE,
        }

        return node.kind in symbol_kinds

    def _create_definition_occurrence(self, node: "Node") -> Occurrence:
        """
        Create DEFINITION occurrence from node.

        Args:
            node: Symbol definition node

        Returns:
            Definition occurrence
        """
        roles = SymbolRole.DEFINITION

        # Add metadata roles based on node attributes
        if node.attrs.get("is_test", False):
            roles |= SymbolRole.TEST

        if node.attrs.get("is_generated", False):
            roles |= SymbolRole.GENERATED

        return create_definition_occurrence(
            symbol_id=node.id,
            span=node.span,
            file_path=node.file_path,
            enclosing_range=node.body_span,
            parent_symbol_id=node.parent_id,
            importance_score=self._estimate_importance(node),
            syntax_kind=str(node.kind),
            attrs={
                "node_kind": str(node.kind),
                "fqn": node.fqn,
                "name": node.name,
            },
        )

    def _create_reference_occurrence(
        self,
        edge: "Edge",
        ir_doc: "IRDocument",
    ) -> Occurrence | None:
        """
        Create REFERENCE/WRITE occurrence from edge.

        Maps edge kind → symbol role:
        - CALLS → READ_ACCESS
        - READS → READ_ACCESS
        - WRITES → WRITE_ACCESS
        - IMPORTS → IMPORT
        - etc.

        Args:
            edge: Relationship edge
            ir_doc: IR document (for node lookup)

        Returns:
            Reference occurrence, or None if edge doesn't represent symbol usage
        """
        # Determine role from edge kind
        roles = self._edge_kind_to_role(edge.kind)
        if roles == SymbolRole.NONE:
            return None

        # Get source node for context
        source_node = ir_doc.get_node(edge.source_id)
        if not source_node:
            return None

        # Use edge span if available, else source node span
        span = edge.span or source_node.span

        # Generate unique occurrence ID
        ref_type = "import" if roles & SymbolRole.IMPORT else "write" if roles & SymbolRole.WRITE_ACCESS else "ref"
        occ_id = f"occ:{ref_type}:{edge.id}"

        return Occurrence(
            id=occ_id,
            symbol_id=edge.target_id,  # Reference TO target
            span=span,
            roles=roles,
            file_path=source_node.file_path,
            parent_symbol_id=edge.source_id,
            importance_score=0.5,  # References have lower base importance
            syntax_kind=str(edge.kind),
            attrs={
                "edge_kind": str(edge.kind),
                "edge_id": edge.id,
                "source_id": edge.source_id,
            },
        )

    def _edge_kind_to_role(self, kind: EdgeKind) -> SymbolRole:
        """
        Map EdgeKind → SymbolRole.

        Args:
            kind: Edge kind

        Returns:
            Corresponding symbol role
        """
        role_map = {
            EdgeKind.CALLS: SymbolRole.READ_ACCESS,
            EdgeKind.READS: SymbolRole.READ_ACCESS,
            EdgeKind.WRITES: SymbolRole.WRITE_ACCESS,
            EdgeKind.REFERENCES: SymbolRole.READ_ACCESS,
            EdgeKind.IMPORTS: SymbolRole.IMPORT,
            EdgeKind.INHERITS: SymbolRole.READ_ACCESS,
            EdgeKind.IMPLEMENTS: SymbolRole.READ_ACCESS,
            EdgeKind.DECORATES: SymbolRole.READ_ACCESS,
            EdgeKind.INSTANTIATES: SymbolRole.READ_ACCESS,
            EdgeKind.OVERRIDES: SymbolRole.READ_ACCESS,
            EdgeKind.USES: SymbolRole.READ_ACCESS,
            EdgeKind.THROWS: SymbolRole.READ_ACCESS,
            EdgeKind.ROUTE_TO: SymbolRole.READ_ACCESS,
            EdgeKind.USES_REPO: SymbolRole.READ_ACCESS,
            # CONTAINS doesn't represent symbol usage (structural only)
        }

        return role_map.get(kind, SymbolRole.NONE)

    def _estimate_importance(self, node: "Node") -> float:
        """
        Estimate initial importance score for a symbol.

        Factors (will be refined in _calculate_importance_scores):
        - Public vs private
        - Top-level vs nested
        - Has documentation
        - Symbol kind (class > function > variable)

        Args:
            node: Symbol node

        Returns:
            Initial importance score (0.0-1.0)
        """
        score = 0.5  # Base score

        # Public API bonus (+0.2)
        if self._is_public_api(node):
            score += 0.2

        # Documentation bonus (+0.1)
        if node.docstring:
            score += 0.1

        # Top-level bonus (+0.1)
        if not node.parent_id or self._is_top_level_parent(node, None):
            score += 0.1

        # Kind bonus
        kind_bonus = {
            NodeKind.CLASS: 0.1,
            NodeKind.INTERFACE: 0.1,
            NodeKind.CLASS: 0.05,
            NodeKind.FUNCTION: 0.05,
        }.get(node.kind, 0.0)
        score += kind_bonus

        return min(score, 1.0)

    def _is_public_api(self, node: "Node") -> bool:
        """
        Check if node is a public API.

        Public if:
        - Not starting with _ (Python convention)
        - Not marked as private in attrs
        - Exported (if applicable)

        Args:
            node: Node to check

        Returns:
            True if public API
        """
        if not node.name:
            return False

        # Private if starts with _ (but __ are special/dunder methods, which are public)
        if node.name.startswith("_") and not node.name.startswith("__"):
            return False

        # Check explicit private marker
        if node.attrs.get("is_private", False):
            return False

        # Check export status
        if node.attrs.get("is_exported") is False:
            return False

        return True

    def _is_top_level_parent(self, node: "Node", ir_doc: "IRDocument | None") -> bool:
        """
        Check if node's parent is top-level (FILE or MODULE).

        Args:
            node: Node to check
            ir_doc: IR document (for parent lookup, optional)

        Returns:
            True if parent is top-level
        """
        if not node.parent_id:
            return True

        if not ir_doc:
            return False

        parent = ir_doc.get_node(node.parent_id)
        if not parent:
            return False

        return parent.kind in {NodeKind.FILE, NodeKind.MODULE}

    def _calculate_importance_scores(
        self,
        occurrences: list[Occurrence],
        ir_doc: "IRDocument",
    ) -> None:
        """
        Calculate final importance scores based on usage patterns.

        Factors:
        - Reference count (popular symbols are more important)
        - Public API status
        - Documentation presence
        - Depth in hierarchy
        - Test vs production code

        Updates importance_score in-place.

        Args:
            occurrences: All occurrences
            ir_doc: IR document (for node lookup)
        """
        # Count references per symbol
        ref_counts: dict[str, int] = {}
        for occ in occurrences:
            if occ.is_reference() or occ.is_write():
                ref_counts[occ.symbol_id] = ref_counts.get(occ.symbol_id, 0) + 1

        # Update importance scores
        for occ in occurrences:
            node = ir_doc.get_node(occ.symbol_id)
            if not node:
                continue

            score = occ.importance_score  # Start with estimated score

            # Reference count bonus (up to +0.2)
            # Popular symbols (many references) are more important
            ref_count = ref_counts.get(node.id, 0)
            if ref_count > 0:
                # Logarithmic scale: 1 ref = 0.01, 10 refs = 0.05, 100 refs = 0.1, 1000+ refs = 0.2
                import math

                ref_bonus = min(math.log10(ref_count + 1) * 0.1, 0.2)
                score += ref_bonus

            # Test code penalty (-0.2)
            # Test symbols are less important for general queries
            if occ.has_role(SymbolRole.TEST):
                score -= 0.2

            # Generated code penalty (-0.1)
            # Generated code is usually less interesting
            if occ.has_role(SymbolRole.GENERATED):
                score -= 0.1

            # Clamp to [0.0, 1.0]
            occ.importance_score = max(0.0, min(score, 1.0))

    def generate_incremental(
        self,
        ir_doc: "IRDocument",
        changed_symbol_ids: set[str],
        existing_index: OccurrenceIndex,
    ) -> tuple[list[Occurrence], OccurrenceIndex]:
        """
        Generate occurrences incrementally for changed symbols.

        Strategy:
        1. Remove old occurrences for changed symbols
        2. Generate new occurrences for changed symbols
        3. Update index incrementally

        Args:
            ir_doc: Updated IR document
            changed_symbol_ids: IDs of symbols that changed
            existing_index: Existing occurrence index

        Returns:
            (new_occurrences, updated_index)
        """
        self.logger.debug(f"Generating occurrences incrementally for {len(changed_symbol_ids)} changed symbols")

        # Remove old occurrences
        occurrences_to_remove: list[str] = []
        for symbol_id in changed_symbol_ids:
            old_occs = existing_index.get_references(symbol_id)
            occurrences_to_remove.extend([o.id for o in old_occs])

        # Remove from indexes
        for occ_id in occurrences_to_remove:
            if occ_id in existing_index.by_id:
                del existing_index.by_id[occ_id]

        # Rebuild indexes (TODO: optimize to remove selectively)
        existing_index.by_symbol.clear()
        existing_index.by_file.clear()
        existing_index.by_role.clear()

        for occ in existing_index.by_id.values():
            existing_index.add(occ)

        # Generate new occurrences for changed symbols
        new_occurrences: list[Occurrence] = []

        for node in ir_doc.nodes:
            if node.id in changed_symbol_ids and self._is_symbol_node(node):
                occ = self._create_definition_occurrence(node)
                new_occurrences.append(occ)

        for edge in ir_doc.edges:
            if edge.source_id in changed_symbol_ids or edge.target_id in changed_symbol_ids:
                occ = self._create_reference_occurrence(edge, ir_doc)
                if occ:
                    new_occurrences.append(occ)

        # Calculate importance for new occurrences
        self._calculate_importance_scores(new_occurrences, ir_doc)

        # Add to index
        for occ in new_occurrences:
            existing_index.add(occ)

        self.logger.info(
            f"Generated {len(new_occurrences)} new occurrences, removed {len(occurrences_to_remove)} old occurrences"
        )

        return new_occurrences, existing_index
