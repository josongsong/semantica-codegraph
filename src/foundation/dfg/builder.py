"""
DFG Builder

Builds Data Flow Graph from Expression IR (NO AST ACCESS).

IMPORTANT: This builder does NOT access AST directly.
It only consumes Expression IR which already contains type information from Pyright.
"""

from typing import TYPE_CHECKING

from .models import DataFlowEdge, DfgSnapshot, VariableEvent
from .resolver import DfgContext, VarResolverState, resolve_or_create_variable

if TYPE_CHECKING:
    from ..ir.models import IRDocument, Node
    from ..semantic_ir.bfg.models import BasicFlowBlock
    from ..semantic_ir.expression.models import Expression


class DfgBuilder:
    """
    Builds DFG (Data Flow Graph) from Expression IR.

    Extracts:
    - VariableEntity (params + locals)
    - VariableEvent (read/write)
    - DataFlowEdge (alias, assign, return_value)

    DOES NOT:
    - Access AST (AST parsing is done by ExpressionBuilder)
    - Call Pyright (Pyright is called by ExpressionBuilder)
    """

    def __init__(self):
        """Initialize DFG builder (no dependencies)"""
        pass

    def build_full(
        self,
        ir_doc: "IRDocument",
        bfg_blocks: list["BasicFlowBlock"],
        expressions: list["Expression"],  # ← Expression IR input
    ) -> DfgSnapshot:
        """
        Build complete DFG from Expression IR.

        Args:
            ir_doc: IR document
            bfg_blocks: BFG blocks
            expressions: Expression IR (already contains types from Pyright)

        Returns:
            DfgSnapshot with all variables, events, and edges
        """
        snapshot = DfgSnapshot()

        # Group expressions by block
        exprs_by_block = self._group_expressions_by_block(expressions)

        # Group blocks by function
        blocks_by_function = self._group_blocks_by_function(bfg_blocks)

        # Process each function
        for function_node_id, func_blocks in blocks_by_function.items():
            # Find function node
            func_node = self._find_function_node(ir_doc, function_node_id)
            if func_node is None:
                continue

            # Build DFG for this function
            func_snapshot = self._build_function_dfg(func_node, func_blocks, exprs_by_block, ir_doc)

            # Merge into global snapshot
            snapshot.variables.extend(func_snapshot.variables)
            snapshot.events.extend(func_snapshot.events)
            snapshot.edges.extend(func_snapshot.edges)

        return snapshot

    def _build_function_dfg(
        self,
        func_node: "Node",
        bfg_blocks: list["BasicFlowBlock"],
        exprs_by_block: dict[str, list["Expression"]],
        ir_doc: "IRDocument",
    ) -> DfgSnapshot:
        """
        Build DFG for a single function from Expression IR.

        Steps:
        1. Create context and resolver state
        2. Build parameter variables
        3. Process each block's expressions
        4. Generate data flow edges

        Args:
            func_node: Function IR node
            bfg_blocks: BFG blocks for this function
            exprs_by_block: Expressions grouped by block ID
            ir_doc: IR document

        Returns:
            DfgSnapshot for this function
        """
        # Create context
        ctx = DfgContext(
            repo_id=ir_doc.repo_id,
            file_path=func_node.file_path,
            function_fqn=func_node.fqn,
            language=func_node.language,
        )

        # Create resolver state
        state = VarResolverState()

        # Track events by variable
        events_by_var: dict[str, list[VariableEvent]] = {}

        # 1. Build parameter variables from function children
        self._create_parameter_variables(func_node, ir_doc, state, ctx)

        # 2. Process each BFG block's expressions
        for i, block in enumerate(bfg_blocks):
            block_exprs = exprs_by_block.get(block.id, [])
            self._process_block_expressions(block, i, block_exprs, state, ctx, events_by_var)

        # 3. Generate data flow edges
        edges = self._build_dataflow_edges(exprs_by_block, ctx)

        # 4. Build snapshot
        snapshot = DfgSnapshot(
            variables=list(ctx.variable_index.values()),
            events=[evt for evts in events_by_var.values() for evt in evts],
            edges=edges,
        )

        return snapshot

    def _create_parameter_variables(
        self,
        func_node: "Node",
        ir_doc: "IRDocument",
        state: VarResolverState,
        ctx: DfgContext,
    ):
        """
        Create VariableEntity for function parameters.

        Args:
            func_node: Function IR node
            ir_doc: IR document
            state: Resolver state
            ctx: DFG context
        """
        from ..ir.models import NodeKind

        # Find parameter nodes (children of function with kind VARIABLE and var_kind=parameter)
        for node in ir_doc.nodes:
            if node.parent_id == func_node.id and node.kind == NodeKind.VARIABLE:
                var_kind = node.attrs.get("var_kind", "local")
                if var_kind == "parameter":
                    # Create parameter variable at block 0 (entry)
                    param_name = node.name
                    if param_name:  # Skip if name is None
                        var_id = resolve_or_create_variable(param_name, 0, "param", state, ctx)

                        # If node has declared_type_id, link it
                        if node.declared_type_id:
                            var_entity = ctx.variable_index[var_id]
                            var_entity.type_id = node.declared_type_id
                            var_entity.type_source = "annotation"

    def _process_block_expressions(
        self,
        block: "BasicFlowBlock",
        block_idx: int,
        expressions: list["Expression"],
        state: VarResolverState,
        ctx: DfgContext,
        events_by_var: dict[str, list[VariableEvent]],
    ):
        """
        Process expressions in a block to extract variable usage.

        Args:
            block: BFG block
            block_idx: Block index
            expressions: Expressions in this block
            state: Resolver state
            ctx: DFG context
            events_by_var: Events tracking
        """

        for expr in expressions:
            # Process reads (expr.reads_vars)
            for var_name in expr.reads_vars:
                # Resolve or create variable
                var_entity = resolve_or_create_variable(var_name, block_idx, "local", state, ctx)

                # If expression has inferred type, update variable
                if expr.inferred_type and var_entity.type_source == "unknown":
                    var_entity.inferred_type = expr.inferred_type
                    var_entity.inferred_type_id = expr.inferred_type_id
                    var_entity.type_source = "inferred"

                # Create read event
                event = VariableEvent(
                    id=f"evt:{var_entity.id}:{expr.id}",
                    repo_id=ctx.repo_id,
                    file_path=ctx.file_path,
                    function_fqn=ctx.function_fqn,
                    variable_id=var_entity.id,
                    block_id=block.id,
                    ir_node_id=expr.id,
                    op_kind="read",
                    start_line=expr.span.start_line if expr.span else None,
                    end_line=expr.span.end_line if expr.span else None,
                )
                events_by_var.setdefault(var_entity.id, []).append(event)
                block.used_variable_ids.append(var_entity.id)

            # Process write (expr.defines_var)
            if expr.defines_var:
                var_name = expr.defines_var

                # Resolve or create variable
                var_entity = resolve_or_create_variable(var_name, block_idx, "local", state, ctx)

                # If expression has inferred type, update variable
                if expr.inferred_type:
                    var_entity.inferred_type = expr.inferred_type
                    var_entity.inferred_type_id = expr.inferred_type_id
                    var_entity.type_source = "inferred"

                # Create write event
                event = VariableEvent(
                    id=f"evt:{var_entity.id}:{expr.id}",
                    repo_id=ctx.repo_id,
                    file_path=ctx.file_path,
                    function_fqn=ctx.function_fqn,
                    variable_id=var_entity.id,
                    block_id=block.id,
                    ir_node_id=expr.id,
                    op_kind="write",
                    start_line=expr.span.start_line if expr.span else None,
                    end_line=expr.span.end_line if expr.span else None,
                )
                events_by_var.setdefault(var_entity.id, []).append(event)
                block.defined_variable_ids.append(var_entity.id)

    def _build_dataflow_edges(
        self,
        exprs_by_block: dict[str, list["Expression"]],
        ctx: DfgContext,
    ) -> list[DataFlowEdge]:
        """
        Build data flow edges from Expression IR.

        Creates edges:
        - alias: a = b (direct assignment)
        - assign: a = fn(b) (function call result)
        - return_value: return a

        Args:
            exprs_by_block: Expressions grouped by block
            ctx: DFG context

        Returns:
            List of data flow edges
        """
        from ..semantic_ir.expression.models import ExprKind

        edges: list[DataFlowEdge] = []
        edge_counter = 0

        for _, expressions in exprs_by_block.items():
            for expr in expressions:
                # Assignment: defines_var + reads_vars
                if expr.defines_var and expr.reads_vars:
                    target_var_name = expr.defines_var

                    # Find target variable
                    target_var_id = None
                    for var_id, var_entity in ctx.variable_index.items():
                        if var_entity.name == target_var_name:
                            target_var_id = var_id
                            break

                    if target_var_id is None:
                        continue

                    # Determine edge kind
                    is_call = expr.kind == ExprKind.CALL
                    edge_kind: str = "assign" if is_call else "alias"

                    # Create edges from source variables
                    for source_var_name in expr.reads_vars:
                        # Find source variable
                        source_var_id = None
                        for var_id, var_entity in ctx.variable_index.items():
                            if var_entity.name == source_var_name:
                                source_var_id = var_id
                                break

                        if source_var_id is None:
                            continue

                        # Create edge
                        edge = DataFlowEdge(
                            id=f"edge:{edge_kind}:{edge_counter}",
                            from_variable_id=source_var_id,
                            to_variable_id=target_var_id,
                            kind=edge_kind,  # type: ignore
                            repo_id=ctx.repo_id,
                            file_path=ctx.file_path,
                            function_fqn=ctx.function_fqn,
                        )
                        edges.append(edge)
                        edge_counter += 1

                # Return statement: reads_vars → special "return"
                # (attrs contain return info from ExpressionBuilder)
                if expr.kind == ExprKind.NAME_LOAD and expr.attrs.get("is_return"):
                    for var_name in expr.reads_vars:
                        # Find variable
                        var_id = None
                        for vid, var_entity in ctx.variable_index.items():
                            if var_entity.name == var_name:
                                var_id = vid
                                break

                        if var_id is None:
                            continue

                        # Create return_value edge
                        edge = DataFlowEdge(
                            id=f"edge:return_value:{edge_counter}",
                            from_variable_id=var_id,
                            to_variable_id="return",  # Special target
                            kind="return_value",
                            repo_id=ctx.repo_id,
                            file_path=ctx.file_path,
                            function_fqn=ctx.function_fqn,
                        )
                        edges.append(edge)
                        edge_counter += 1

        return edges

    # Helper methods

    def _group_expressions_by_block(self, expressions: list["Expression"]) -> dict[str, list["Expression"]]:
        """Group expressions by block ID"""
        exprs_by_block: dict[str, list[Expression]] = {}

        for expr in expressions:
            if expr.block_id:
                exprs_by_block.setdefault(expr.block_id, []).append(expr)

        return exprs_by_block

    def _group_blocks_by_function(self, bfg_blocks: list["BasicFlowBlock"]) -> dict[str, list["BasicFlowBlock"]]:
        """Group BFG blocks by function node ID"""
        from ..semantic_ir.bfg.models import BasicFlowBlock

        blocks_by_func: dict[str, list[BasicFlowBlock]] = {}

        for block in bfg_blocks:
            func_id = block.function_node_id
            blocks_by_func.setdefault(func_id, []).append(block)

        return blocks_by_func

    def _find_function_node(self, ir_doc: "IRDocument", function_node_id: str) -> "Node | None":
        """Find function node by ID"""
        from ..ir.models import NodeKind

        for node in ir_doc.nodes:
            if node.id == function_node_id and node.kind in (
                NodeKind.FUNCTION,
                NodeKind.METHOD,
            ):
                return node

        return None
