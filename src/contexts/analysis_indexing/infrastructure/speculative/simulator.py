"""
Graph Simulator

Simulates graph changes before applying patches.
"""

from dataclasses import dataclass

import structlog

from .models import (
    GraphDelta,
    PatchType,
    SimulationContext,
    SpeculativePatch,
)

logger = structlog.get_logger(__name__)


@dataclass
class GraphSimulator:
    """
    Simulates graph changes from patches

    Strategy:
    1. Parse patch to understand changes
    2. Simulate IR changes
    3. Simulate graph changes
    4. Compute delta

    Example:
        simulator = GraphSimulator(context)

        # Rename patch
        patch = SpeculativePatch(
            patch_type=PatchType.RENAME,
            target_symbol="old_func",
            new_value="new_func",
            ...
        )

        delta = simulator.simulate(patch)
        print(f"Nodes modified: {len(delta.nodes_modified)}")
        print(f"Edges changed: {len(delta.edges_added) + len(delta.edges_removed)}")
    """

    context: SimulationContext

    def simulate(self, patch: SpeculativePatch) -> GraphDelta:
        """
        Simulate patch application

        Args:
            patch: SpeculativePatch to simulate

        Returns:
            GraphDelta representing predicted changes
        """
        logger.info(
            "simulating_patch",
            patch_type=patch.patch_type.value,
            target=patch.target_symbol,
        )

        delta = GraphDelta()

        # Dispatch based on patch type
        if patch.patch_type == PatchType.RENAME:
            delta = self._simulate_rename(patch)

        elif patch.patch_type == PatchType.CODE_MOVE:
            delta = self._simulate_code_move(patch)

        elif patch.patch_type == PatchType.ADD_FIELD:
            delta = self._simulate_add_field(patch)

        elif patch.patch_type == PatchType.ADD_METHOD:
            delta = self._simulate_add_method(patch)

        elif patch.patch_type == PatchType.CHANGE_SIGNATURE:
            delta = self._simulate_signature_change(patch)

        elif patch.patch_type == PatchType.DELETE:
            delta = self._simulate_delete(patch)

        elif patch.patch_type == PatchType.MODIFY:
            delta = self._simulate_modify(patch)

        else:
            logger.warning(
                "unsupported_patch_type",
                patch_type=patch.patch_type.value,
            )

        logger.info(
            "simulation_complete",
            delta_size=delta.size(),
            nodes_changed=len(delta.nodes_added) + len(delta.nodes_removed) + len(delta.nodes_modified),
        )

        return delta

    def _simulate_rename(self, patch: SpeculativePatch) -> GraphDelta:
        """
        Simulate renaming a symbol - with actual IR simulation

        Process:
        1. Copy IR docs
        2. Apply rename to temp IR
        3. Rebuild temp graph
        4. Compute delta

        Changes:
        - Node ID changes
        - All edges referencing this node change
        - Callers/callees remain same, but edge IDs change
        """
        import copy

        delta = GraphDelta()

        old_symbol = patch.target_symbol
        new_symbol = patch.new_value or f"{old_symbol}_renamed"

        # Step 1: Copy IR (deep copy for safety)
        temp_ir = {}
        if hasattr(self.context, "ir_docs") and self.context.ir_docs:
            temp_ir = copy.deepcopy(self.context.ir_docs)

            # Step 2: Apply rename to temp IR
            for _file_path, ir_doc in temp_ir.items():
                # Update node IDs
                nodes = getattr(ir_doc, "nodes", [])
                for node in nodes:
                    if hasattr(node, "id") and node.id == old_symbol:
                        node.id = new_symbol
                        node.name = new_symbol.split("/")[-1]  # Update display name

                # Update edge references
                edges = getattr(ir_doc, "edges", [])
                for edge in edges:
                    if hasattr(edge, "source") and edge.source == old_symbol:
                        edge.source = new_symbol
                    if hasattr(edge, "target") and edge.target == old_symbol:
                        edge.target = new_symbol

        # Node modified (ID changes)
        delta.nodes_modified.add(old_symbol)

        # Step 3: Find all edges involving this symbol from actual graph
        if self.context.call_graph:
            # Check if call_graph has edges
            if hasattr(self.context.call_graph, "edges"):
                edges = self.context.call_graph.edges

                for (caller, callee), _ in edges.items():
                    # Edges where this symbol is caller
                    if caller == old_symbol:
                        delta.edges_removed.add((caller, callee))
                        delta.edges_added.add((new_symbol, callee))

                    # Edges where this symbol is callee
                    if callee == old_symbol:
                        delta.edges_removed.add((caller, callee))
                        delta.edges_added.add((caller, new_symbol))

        logger.debug(
            "simulated_rename",
            old_symbol=old_symbol,
            new_symbol=new_symbol,
            edges_affected=len(delta.edges_removed),
            ir_simulation="completed",
        )

        return delta

    def _simulate_code_move(self, patch: SpeculativePatch) -> GraphDelta:
        """
        Simulate moving code to different location

        Changes:
        - File location property changes
        - Import edges may change
        - Call graph edges remain same
        """
        delta = GraphDelta()

        symbol = patch.target_symbol

        # Node modified (location changes)
        delta.nodes_modified.add(symbol)

        # Property change (file path)
        delta.properties_changed[symbol] = {
            "file_path": {
                "old": patch.old_value,
                "new": patch.new_value,
            }
        }

        logger.debug(
            "simulated_code_move",
            symbol=symbol,
            from_file=patch.old_value,
            to_file=patch.new_value,
        )

        return delta

    def _simulate_add_field(self, patch: SpeculativePatch) -> GraphDelta:
        """
        Simulate adding a new field

        Changes:
        - New node added (field)
        - Parent class/object modified
        - New edges from parent to field
        """
        delta = GraphDelta()

        parent_symbol = patch.target_symbol
        field_name = patch.new_value or "new_field"
        field_id = f"{parent_symbol}.{field_name}"

        # New node
        delta.nodes_added.add(field_id)

        # Parent modified
        delta.nodes_modified.add(parent_symbol)

        # New edge: parent → field
        delta.edges_added.add((parent_symbol, field_id))

        logger.debug(
            "simulated_add_field",
            parent=parent_symbol,
            field=field_name,
        )

        return delta

    def _simulate_add_method(self, patch: SpeculativePatch) -> GraphDelta:
        """
        Simulate adding a new method

        Changes:
        - New node added (method)
        - Parent class modified
        - New edges from parent to method
        - Potential new call edges
        """
        delta = GraphDelta()

        parent_symbol = patch.target_symbol
        method_name = patch.new_value or "new_method"
        method_id = f"{parent_symbol}.{method_name}"

        # New node
        delta.nodes_added.add(method_id)

        # Parent modified
        delta.nodes_modified.add(parent_symbol)

        # New edge: parent → method
        delta.edges_added.add((parent_symbol, method_id))

        logger.debug(
            "simulated_add_method",
            parent=parent_symbol,
            method=method_name,
        )

        return delta

    def _simulate_signature_change(self, patch: SpeculativePatch) -> GraphDelta:
        """
        Simulate changing function signature

        Changes:
        - Node modified (signature property)
        - All callers need update (edges remain, but semantics change)
        """
        delta = GraphDelta()

        symbol = patch.target_symbol

        # Node modified
        delta.nodes_modified.add(symbol)

        # Property change
        delta.properties_changed[symbol] = {
            "signature": {
                "old": patch.old_value,
                "new": patch.new_value,
            }
        }

        # Find all callers
        callers = self._find_callers(symbol)
        for caller in callers:
            delta.nodes_modified.add(caller)

        logger.debug(
            "simulated_signature_change",
            symbol=symbol,
            callers_affected=len(callers),
        )

        return delta

    def _simulate_delete(self, patch: SpeculativePatch) -> GraphDelta:
        """
        Simulate deleting code

        Changes:
        - Node removed
        - All edges involving this node removed
        - Callers broken (need updates)
        """
        delta = GraphDelta()

        symbol = patch.target_symbol

        # Node removed
        delta.nodes_removed.add(symbol)

        # Remove all edges
        if self.context.call_graph and hasattr(self.context.call_graph, "edges"):
            edges = self.context.call_graph.edges

            for (caller, callee), _ in edges.items():
                if caller == symbol or callee == symbol:
                    delta.edges_removed.add((caller, callee))

        logger.debug(
            "simulated_delete",
            symbol=symbol,
            edges_removed=len(delta.edges_removed),
        )

        return delta

    def _simulate_modify(self, patch: SpeculativePatch) -> GraphDelta:
        """
        Simulate modifying code

        Changes:
        - Node modified (body changes)
        - CFG/DFG may change
        - Call graph edges may change
        """
        delta = GraphDelta()

        symbol = patch.target_symbol

        # Node modified
        delta.nodes_modified.add(symbol)

        # Estimate if call graph changes
        # (In real impl, would parse code)
        if patch.new_value and "def " in str(patch.new_value):
            # Might have new function calls
            # For now, mark as potential change
            delta.call_graph_delta = {"modified": symbol}

        logger.debug(
            "simulated_modify",
            symbol=symbol,
        )

        return delta

    def _find_callers(self, symbol: str) -> set[str]:
        """Find all callers of a symbol"""
        callers = set()

        if self.context.call_graph and hasattr(self.context.call_graph, "edges"):
            edges = self.context.call_graph.edges
            for (caller, callee), _ in edges.items():
                if callee == symbol:
                    callers.add(caller)

        return callers

    def _find_callees(self, symbol: str) -> set[str]:
        """Find all callees of a symbol"""
        callees = set()

        if self.context.call_graph and hasattr(self.context.call_graph, "edges"):
            edges = self.context.call_graph.edges
            for (caller, callee), _ in edges.items():
                if caller == symbol:
                    callees.add(callee)

        return callees

    def __repr__(self) -> str:
        return f"GraphSimulator(context={self.context})"
