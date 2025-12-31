"""
EdgeIndex - Edge Indexing (SRP)

Single Responsibility: Edge 인덱싱 및 조회
- O(1) forward edge lookup (source → targets)
- O(1) backward edge lookup (target → sources)
- Type-specific edge filtering

SOLID:
- S: Edge 인덱싱만 담당
- O: Extensible for new edge types
- L: Substitutable with Port
- I: Minimal interface
- D: Depends on abstractions
"""

from collections import defaultdict
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.query.results import UnifiedEdge
from codegraph_engine.code_foundation.domain.query.types import EdgeType
from codegraph_engine.code_foundation.infrastructure.ir.models.core import InterproceduralEdgeKind

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument

logger = get_logger(__name__)


class EdgeIndex:
    """
    Edge indexing layer

    Responsibilities:
    1. Build bidirectional edge index
    2. O(1) forward edge lookup
    3. O(1) backward edge lookup
    4. Type-specific filtering

    Performance:
    - Build: O(E) where E = total edges
    - Lookup: O(k) where k = edge count for node
    - Memory: ~2E (forward + backward)
    """

    def __init__(self, ir_doc: "IRDocument"):
        """
        Initialize edge index

        Args:
            ir_doc: IR document
        """
        # Bidirectional indexes
        self._edges_from: dict[str, list[UnifiedEdge]] = defaultdict(list)
        self._edges_to: dict[str, list[UnifiedEdge]] = defaultdict(list)

        # Type-specific indexes (for fast filtering)
        self._dfg_edges: dict[str, list[UnifiedEdge]] = defaultdict(list)
        self._cfg_edges: dict[str, list[UnifiedEdge]] = defaultdict(list)
        self._call_edges: dict[str, list[UnifiedEdge]] = defaultdict(list)

        self._build(ir_doc)

        total_edges = sum(len(edges) for edges in self._edges_from.values())
        logger.info("edge_index_built", edge_count=total_edges)

    def _build(self, ir_doc: "IRDocument") -> None:
        """Build edge index from IR"""
        # 1. DFG edges
        if ir_doc.dfg_snapshot:
            for edge in ir_doc.dfg_snapshot.edges:
                unified = UnifiedEdge(
                    from_node=edge.from_variable_id,
                    to_node=edge.to_variable_id,
                    edge_type=EdgeType.DFG,
                    attrs={"kind": edge.kind, **edge.attrs},
                )
                self._add_edge(unified, EdgeType.DFG)

        # 2. CFG edges
        for edge in ir_doc.cfg_edges:
            unified = UnifiedEdge(
                from_node=edge.source_block_id,
                to_node=edge.target_block_id,
                edge_type=EdgeType.CFG,
                attrs={"kind": edge.kind.value},
            )
            self._add_edge(unified, EdgeType.CFG)

        # 3. Expression → Variable edges (DFG) 🔥 FIXED
        # Note: expr.reads_vars/defines_var contain variable NAMES (not IDs!)
        # We need to map names → IDs for proper edge creation
        if ir_doc.dfg_snapshot:
            # Build name → IDs mapping (one name can have multiple variable versions)
            var_name_to_ids: dict[str, list[str]] = {}
            for var in ir_doc.dfg_snapshot.variables:
                if var.name not in var_name_to_ids:
                    var_name_to_ids[var.name] = []
                var_name_to_ids[var.name].append(var.id)

            for expr in ir_doc.expressions:
                # Expression reads variables (reads_vars = list of variable NAMES)
                for var_name in expr.reads_vars:
                    var_ids = var_name_to_ids.get(var_name, [])
                    for var_id in var_ids:
                        # Variable → Expression (read)
                        unified = UnifiedEdge(
                            from_node=var_id,
                            to_node=expr.id,
                            edge_type=EdgeType.DFG,
                            attrs={"kind": "read", "expr_to_var": True},
                        )
                        self._add_edge(unified, EdgeType.DFG)

                # Expression defines variable (defines_var = variable NAME)
                if expr.defines_var:
                    var_ids = var_name_to_ids.get(expr.defines_var, [])
                    for var_id in var_ids:
                        # Expression → Variable (define)
                        unified = UnifiedEdge(
                            from_node=expr.id,
                            to_node=var_id,
                            edge_type=EdgeType.DFG,
                            attrs={"kind": "define", "expr_to_var": True},
                        )
                        self._add_edge(unified, EdgeType.DFG)

        # 4. Call edges
        from codegraph_engine.code_foundation.infrastructure.ir.models import EdgeKind

        for edge in ir_doc.edges:
            if edge.kind == EdgeKind.CALLS:
                unified = UnifiedEdge(
                    from_node=edge.source_id,
                    to_node=edge.target_id,
                    edge_type=EdgeType.CALL,
                    attrs={},
                )
                self._add_edge(unified, EdgeType.CALL)

        # 5. Expression Parent-Child edges (DFG) 🔥 NEW
        # This connects child expressions (e.g., arguments) to parent expressions (e.g., CALL)
        # Critical for taint propagation: NAME_LOAD(e) → CALL(conn.execute)
        for expr in ir_doc.expressions:
            if expr.parent_expr_id:
                # Child → Parent (data flows from argument to call)
                unified = UnifiedEdge(
                    from_node=expr.id,
                    to_node=expr.parent_expr_id,
                    edge_type=EdgeType.DFG,
                    attrs={"kind": "arg_to_call", "expr_tree": True},
                )
                self._add_edge(unified, EdgeType.DFG)

        # 6. Interprocedural edges (from builder) - includes collection edges
        if hasattr(ir_doc, "interprocedural_edges"):
            for edge in ir_doc.interprocedural_edges:
                unified = UnifiedEdge(
                    from_node=edge.from_var_id,
                    to_node=edge.to_var_id,
                    edge_type=EdgeType.DFG,
                    attrs={
                        "id": edge.id,
                        "interproc_kind": edge.kind,
                        "call_site_id": edge.call_site_id,
                        "caller_func": edge.caller_func_fqn,
                        "callee_func": edge.callee_func_fqn,
                        "arg_position": edge.arg_position,
                        "confidence": edge.confidence,
                        # Collection-specific attrs
                        "collection_var_id": getattr(edge, "collection_var_id", None),
                        "element_key": getattr(edge, "element_key", None),
                    },
                )
                self._add_edge(unified, EdgeType.DFG)

                # 🔥 For collection_load edges, also create reverse lookup
                # This helps traversal find collection[*] → iterator edges
                if edge.kind == InterproceduralEdgeKind.COLLECTION_LOAD and edge.collection_var_id:
                    # Also add edge from collection_var_id to element[*]
                    # This connects: collection variable → collection element → iterator
                    element_id = f"{edge.collection_var_id}[*]"
                    if edge.from_var_id == element_id:
                        # Create: collection_var → element[*]
                        bridge = UnifiedEdge(
                            from_node=edge.collection_var_id,
                            to_node=element_id,
                            edge_type=EdgeType.DFG,
                            attrs={
                                "kind": "collection_element",
                                "collection_var_id": edge.collection_var_id,
                            },
                        )
                        self._add_edge(bridge, EdgeType.DFG)

        # 7. 🔥 CRITICAL: Return-to-Caller edges (Inter-procedural)
        # Connects callee function's internal expressions to caller's call site
        # Example: get_data() calls input() → main() calls get_data() and assigns to `data`
        # We need: input() CALL → get_data() CALL (which defines `data`)
        self._build_return_to_caller_edges(ir_doc)

        # 8. 🔥 SOTA FIX: Callee Target → Expression edges
        # DFG edges use `callee:name:param:N` as targets, but NodeMatcher returns `expr:...`
        # This bridges the gap: connect callee targets back to their CALL expressions
        self._build_callee_to_expr_edges(ir_doc)

        # 9. 🔥 SOTA FIX: Expression → Variable edges (for SOURCE matching)
        # Q.Call('input') returns `expr:...`, but DFG starts from `var:...` nodes
        # This bridges the gap: connect source expressions to their output variables
        self._build_expr_to_var_edges(ir_doc)

        # 10. 🔥 SOTA: Lambda/Local function call edges (Inter-procedural)
        # Connects call arguments to lambda/function parameters
        # Example: execute(cmd) where execute = lambda x: os.system(x)
        # Creates: cmd → x (lambda parameter)
        self._build_lambda_call_edges(ir_doc)

    def _add_edge(self, edge: UnifiedEdge, edge_type: EdgeType) -> None:
        """Add edge to indexes"""
        # Bidirectional indexes
        self._edges_from[edge.from_node].append(edge)
        self._edges_to[edge.to_node].append(edge)

        # Type-specific indexes
        if edge_type == EdgeType.DFG:
            self._dfg_edges[edge.from_node].append(edge)
        elif edge_type == EdgeType.CFG:
            self._cfg_edges[edge.from_node].append(edge)
        elif edge_type == EdgeType.CALL:
            self._call_edges[edge.from_node].append(edge)

    def get_outgoing(self, node_id: str, edge_type: EdgeType | None = None) -> list[UnifiedEdge]:
        """
        Get outgoing edges from node (O(1) or O(k))

        Args:
            node_id: Source node ID
            edge_type: Filter by edge type (None = all)

        Returns:
            List of outgoing edges
        """
        if edge_type is None or edge_type == EdgeType.ALL:
            return self._edges_from.get(node_id, [])

        # Type-specific lookup (optimized)
        if edge_type == EdgeType.DFG:
            return self._dfg_edges.get(node_id, [])
        elif edge_type == EdgeType.CFG:
            return self._cfg_edges.get(node_id, [])
        elif edge_type == EdgeType.CALL:
            return self._call_edges.get(node_id, [])

        # Fallback: filter manually
        edges = self._edges_from.get(node_id, [])
        return [e for e in edges if e.edge_type == edge_type]

    def get_incoming(self, node_id: str, edge_type: EdgeType | None = None) -> list[UnifiedEdge]:
        """
        Get incoming edges to node (O(1) or O(k))

        Args:
            node_id: Target node ID
            edge_type: Filter by edge type (None = all)

        Returns:
            List of incoming edges
        """
        edges = self._edges_to.get(node_id, [])

        if edge_type is None or edge_type == EdgeType.ALL:
            return edges

        # Type-specific filtering
        return [e for e in edges if e.edge_type == edge_type]

    def _build_return_to_caller_edges(self, ir_doc: "IRDocument") -> None:
        """
        🔥 Build Return-to-Caller edges for inter-procedural analysis.

        This connects:
        1. Expressions INSIDE a callee function → Call site in caller that assigns result

        Algorithm:
        1. Index: function_fqn → [expression_ids inside that function]
        2. For each CALL expression with defines_var:
           a. Find callee function by callee_name
           b. Get all expressions inside callee function
           c. Create edge: callee_expr → call_site_expr (for taint propagation)

        Example:
            def get_data():
                return input()  # expr1: CALL input()

            def main():
                data = get_data()  # expr2: CALL get_data(), defines_var=data
                conn.execute(data)  # expr3: CALL execute

            Creates edge: expr1 (input) → expr2 (get_data call)
            So taint flows: input() → data → execute()
        """
        # Step 1: Index function_fqn → expressions inside
        func_to_exprs: dict[str, list[str]] = {}
        for expr in ir_doc.expressions:
            if expr.function_fqn:
                func_to_exprs.setdefault(expr.function_fqn, []).append(expr.id)

        # Step 2: Index function simple name → function_fqn (for lookup)
        # Extract simple name from FQN: "module.get_data" → "get_data"
        simple_name_to_fqn: dict[str, list[str]] = {}
        for fqn in func_to_exprs.keys():
            simple_name = fqn.split(".")[-1] if "." in fqn else fqn
            simple_name_to_fqn.setdefault(simple_name, []).append(fqn)

        # Step 3: Process each CALL expression with defines_var
        interproc_edge_count = 0
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import ExprKind

        for expr in ir_doc.expressions:
            if expr.kind != ExprKind.CALL:
                continue

            # Only process calls that assign to a variable
            if not expr.defines_var:
                continue

            callee_name = expr.attrs.get("callee_name")
            if not callee_name:
                continue

            # Extract simple function name from callee_name
            # "obj.method" → "method", "func" → "func"
            simple_callee = callee_name.split(".")[-1] if "." in callee_name else callee_name

            # Find matching callee FQNs
            callee_fqns = simple_name_to_fqn.get(simple_callee, [])
            if not callee_fqns:
                continue

            # For each callee function, connect its expressions to this call site
            for callee_fqn in callee_fqns:
                callee_expr_ids = func_to_exprs.get(callee_fqn, [])

                for callee_expr_id in callee_expr_ids:
                    # Create edge: callee_expr → caller_call_site
                    # This propagates taint from callee to caller via return value
                    unified = UnifiedEdge(
                        from_node=callee_expr_id,
                        to_node=expr.id,
                        edge_type=EdgeType.DFG,
                        attrs={
                            "kind": "return_to_caller",
                            "interproc": True,
                            "callee_fqn": callee_fqn,
                            "caller_call_site": expr.id,
                        },
                    )
                    self._add_edge(unified, EdgeType.DFG)
                    interproc_edge_count += 1

        if interproc_edge_count > 0:
            logger.info(
                "return_to_caller_edges_built",
                count=interproc_edge_count,
            )

    def _build_callee_to_expr_edges(self, ir_doc: "IRDocument") -> None:
        """
        🔥 SOTA FIX: Build callee target → CALL expression edges.

        Problem:
            DFG edges use `callee:name:param:N` as targets (e.g., `callee:os.system:param:0`)
            But NodeMatcher.match(Q.Call('os.system')) returns `expr:...` IDs
            Path finding fails because these IDs don't connect!

        Solution:
            Create edges: `callee:name:param:N` → `expr:...` (the CALL expression)
            This allows path finding to reach the target expression.

        Algorithm:
            1. For each CALL expression with callee_name (e.g., 'os.system')
            2. Generate callee target IDs: `callee:{callee_name}:param:0`, `:param:1`, etc.
            3. Create edge: callee_target → expression
        """
        callee_edge_count = 0

        for expr in ir_doc.expressions:
            if expr.kind.name == "CALL":
                callee_name = expr.attrs.get("callee_name")
                if not callee_name:
                    continue

                # Get number of arguments from call_args
                call_args = expr.attrs.get("call_args", [])
                num_args = len(call_args) if call_args else 1  # At least 1 for general cases

                # Create edges for each parameter position
                for arg_idx in range(num_args):
                    callee_target_id = f"callee:{callee_name}:param:{arg_idx}"

                    # Callee target → CALL expression (reverse direction for path finding)
                    unified = UnifiedEdge(
                        from_node=callee_target_id,
                        to_node=expr.id,
                        edge_type=EdgeType.DFG,
                        attrs={"kind": "callee_to_expr", "param_idx": arg_idx},
                    )
                    self._add_edge(unified, EdgeType.DFG)
                    callee_edge_count += 1

        if callee_edge_count > 0:
            logger.debug("callee_to_expr_edges_built", count=callee_edge_count)

    def _build_expr_to_var_edges(self, ir_doc: "IRDocument") -> None:
        """
        🔥 SOTA FIX: Build CALL expression → output variable edges.

        Problem:
            Q.Call('input') returns `expr:...` nodes, but DFG starts from `var:...` nodes.
            Path finding fails because source expression doesn't connect to DFG!

        Solution:
            For CALL expressions that define a variable (e.g., `user_input = input()`):
            Create edge: `expr:input()` → `var:user_input`
            This allows path finding to start from source expression.

        Algorithm:
            1. For each CALL expression with defines_var attribute
            2. Find corresponding DFG variable node
            3. Create edge: expression → variable

        Collection Fix:
            Also connect CALL expressions to `<call>` variables which represent
            nested call results (e.g., `queries.append(input())` where `input()`
            result is stored in a `<call>` variable).
        """
        expr_to_var_count = 0

        # Build a mapping of line → <call> variable IDs
        # This helps connect source expressions to their result variables
        line_to_call_vars: dict[int, list[str]] = {}
        if ir_doc.dfg_snapshot:
            for var in ir_doc.dfg_snapshot.variables:
                if var.name == "<call>" and var.decl_span:
                    line = var.decl_span.start_line
                    line_to_call_vars.setdefault(line, []).append(var.id)

        for expr in ir_doc.expressions:
            if expr.kind.name == "CALL":
                callee_name = expr.attrs.get("callee_name", "")

                # Pattern 1: CALL with explicit defines_var
                if expr.defines_var:
                    target_var_name = expr.defines_var

                    # Search in DFG variables for matching variable
                    if ir_doc.dfg_snapshot:
                        for dfg_var in ir_doc.dfg_snapshot.variables:
                            # Match variable name
                            if dfg_var.name == target_var_name:
                                to_var = dfg_var.id
                                unified = UnifiedEdge(
                                    from_node=expr.id,
                                    to_node=to_var,
                                    edge_type=EdgeType.DFG,
                                    attrs={"kind": "expr_to_var", "defines_var": target_var_name},
                                )
                                self._add_edge(unified, EdgeType.DFG)
                                expr_to_var_count += 1
                                break

                # Pattern 2: CALL without defines_var but has <call> result variable
                # This handles nested calls like queries.append(input())
                # where input() result goes to a <call> temp variable
                else:
                    expr_line = expr.span.start_line if expr.span else 0
                    call_vars = line_to_call_vars.get(expr_line, [])

                    for call_var_id in call_vars:
                        # Connect expression to its <call> result variable
                        unified = UnifiedEdge(
                            from_node=expr.id,
                            to_node=call_var_id,
                            edge_type=EdgeType.DFG,
                            attrs={"kind": "expr_to_call_var", "callee": callee_name},
                        )
                        self._add_edge(unified, EdgeType.DFG)
                        expr_to_var_count += 1

        if expr_to_var_count > 0:
            logger.debug("expr_to_var_edges_built", count=expr_to_var_count)

    def _build_lambda_call_edges(self, ir_doc: "IRDocument") -> None:
        """
        🔥 SOTA: Build edges for lambda/local function calls.

        Problem:
            When a lambda is called: `execute(cmd)` where `execute = lambda x: os.system(x)`
            The DFG has:
              - cmd → callee:execute:param:0
              - x → callee:os.system:param:0
            But there's NO edge: callee:execute:param:0 → x

        Solution:
            Connect callee:lambda_name:param:N → lambda's parameter variable
            This bridges the gap between caller argument and lambda parameter.
        """
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import ExprKind

        lambda_edge_count = 0

        if not ir_doc.dfg_snapshot:
            return

        # Step 1: Find lambda definitions and their internal parameter usages
        # lambda_name -> list of (param_index, param_var_id)
        lambda_param_vars: dict[str, list[tuple[int, str]]] = {}

        for expr in ir_doc.expressions:
            if expr.kind == ExprKind.LAMBDA and expr.defines_var:
                lambda_name = expr.defines_var

                # Find parameter variables used in lambda body
                # They appear as reads_vars in nested expressions
                # Look for variables that are:
                # 1. Read in lambda body (not defined elsewhere)
                # 2. Flow to callee targets

                # Find edges from param-like vars in lambda's scope
                param_candidates = []
                for dfg_edge in ir_doc.dfg_snapshot.edges:
                    # Look for edges TO callee targets from within lambda
                    if dfg_edge.to_variable_id.startswith("callee:"):
                        # Check if from_variable looks like a lambda param
                        # Lambda params usually appear as single-letter or short names
                        from_var = dfg_edge.from_variable_id
                        if f":{lambda_name}@" not in from_var:  # Not the lambda itself
                            # Extract var name from ID
                            parts = from_var.split(":")
                            for part in parts:
                                if "@" in part:
                                    var_name = part.split("@")[0]
                                    if var_name and len(var_name) <= 3:  # Short param names
                                        param_candidates.append((0, from_var, var_name))
                                    break

                if param_candidates:
                    lambda_param_vars[lambda_name] = param_candidates

        # Step 2: Create edges from callee:lambda:param:N to param variables
        for lambda_name, param_infos in lambda_param_vars.items():
            for param_idx, param_var_id, param_name in param_infos:
                callee_target = f"callee:{lambda_name}:param:{param_idx}"

                # Create edge: callee:execute:param:0 → var:x
                unified = UnifiedEdge(
                    from_node=callee_target,
                    to_node=param_var_id,
                    edge_type=EdgeType.DFG,
                    attrs={
                        "kind": "lambda_param_bind",
                        "lambda_name": lambda_name,
                        "param_name": param_name,
                    },
                )
                self._add_edge(unified, EdgeType.DFG)
                lambda_edge_count += 1

        if lambda_edge_count > 0:
            logger.info("lambda_call_edges_built", count=lambda_edge_count)

    def get_stats(self) -> dict:
        """Get edge statistics"""
        return {
            "total_edges": sum(len(edges) for edges in self._edges_from.values()),
            "dfg_edges": sum(len(edges) for edges in self._dfg_edges.values()),
            "cfg_edges": sum(len(edges) for edges in self._cfg_edges.values()),
            "call_edges": sum(len(edges) for edges in self._call_edges.values()),
        }
