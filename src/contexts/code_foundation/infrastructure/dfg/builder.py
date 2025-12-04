"""
DFG Builder

Builds Data Flow Graph from Expression IR (NO AST ACCESS).

IMPORTANT: This builder does NOT access AST directly.
It only consumes Expression IR which already contains type information from Pyright.
"""

import time
from typing import TYPE_CHECKING, Literal

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.dfg.models import DataFlowEdge, DfgSnapshot, VariableEvent
from src.contexts.code_foundation.infrastructure.dfg.resolver import (
    DfgContext,
    VarResolverState,
    resolve_or_create_variable,
)

logger = get_logger(__name__)

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.ir.models import IRDocument, Node
    from src.contexts.code_foundation.infrastructure.semantic_ir.bfg.models import BasicFlowBlock
    from src.contexts.code_foundation.infrastructure.semantic_ir.expression.models import Expression


class DfgMetrics:
    """Performance metrics for DFG building"""

    def __init__(self):
        self.expression_grouping_ms: float = 0.0
        self.block_grouping_ms: float = 0.0
        self.parameter_creation_ms: float = 0.0
        self.expression_processing_ms: float = 0.0
        self.edge_generation_ms: float = 0.0
        self.total_functions: int = 0
        self.total_variables: int = 0
        self.total_events: int = 0
        self.total_edges: int = 0
        self.failed_functions: int = 0

    def get_summary(self) -> dict[str, float | int]:
        """Get summary dictionary"""
        return {
            "expression_grouping_ms": self.expression_grouping_ms,
            "block_grouping_ms": self.block_grouping_ms,
            "parameter_creation_ms": self.parameter_creation_ms,
            "expression_processing_ms": self.expression_processing_ms,
            "edge_generation_ms": self.edge_generation_ms,
            "total_functions": self.total_functions,
            "total_variables": self.total_variables,
            "total_events": self.total_events,
            "total_edges": self.total_edges,
            "failed_functions": self.failed_functions,
        }


class DfgBuilder:
    """
    Builds DFG (Data Flow Graph) from Expression IR.

    Extracts:
    - VariableEntity (params + locals + captured)
    - VariableEvent (read/write)
    - DataFlowEdge (alias, assign, return_value)

    Enhanced with:
    - Closure/captured variable detection for nested functions
    - Nested function scope tracking via FQN hierarchy

    DOES NOT:
    - Access AST (AST parsing is done by ExpressionBuilder)
    - Call Pyright (Pyright is called by ExpressionBuilder)
    """

    def __init__(self):
        """Initialize DFG builder (no dependencies)"""
        self._metrics = DfgMetrics()
        # Track variables by function FQN for closure detection
        # fqn -> {name -> var_id}
        self._function_variables: dict[str, dict[str, str]] = {}

    def get_metrics(self) -> DfgMetrics:
        """Get performance metrics for last build"""
        return self._metrics

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
        # Reset metrics and function variable tracking
        self._metrics = DfgMetrics()
        self._function_variables = {}

        snapshot = DfgSnapshot()

        # Group expressions by block (with timing)
        start_time = time.perf_counter()
        exprs_by_block = self._group_expressions_by_block(expressions)
        self._metrics.expression_grouping_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(
            f"[DFG Metrics] Expression grouping: {self._metrics.expression_grouping_ms:.2f}ms "
            f"({len(expressions)} expressions → {len(exprs_by_block)} blocks)"
        )

        # Group blocks by function (with timing)
        start_time = time.perf_counter()
        blocks_by_function = self._group_blocks_by_function(bfg_blocks)
        self._metrics.block_grouping_ms = (time.perf_counter() - start_time) * 1000
        logger.debug(
            f"[DFG Metrics] Block grouping: {self._metrics.block_grouping_ms:.2f}ms "
            f"({len(bfg_blocks)} blocks → {len(blocks_by_function)} functions)"
        )

        self._metrics.total_functions = len(blocks_by_function)
        failed_function_list = []  # Track failed function IDs

        # Sort functions by FQN depth (process outer functions first for closure detection)
        sorted_function_ids = sorted(blocks_by_function.keys(), key=lambda fid: fid.count(".") if fid else 0)

        # Process each function (outer functions first)
        for function_node_id in sorted_function_ids:
            func_blocks = blocks_by_function[function_node_id]
            try:
                # Find function node
                func_node = self._find_function_node(ir_doc, function_node_id)
                if func_node is None:
                    logger.warning(f"[DfgBuilder] Function node not found: {function_node_id}")
                    self._metrics.failed_functions += 1
                    failed_function_list.append(function_node_id)
                    continue

                # Build DFG for this function
                func_snapshot = self._build_function_dfg(func_node, func_blocks, exprs_by_block, ir_doc)

                # Merge into global snapshot
                snapshot.variables.extend(func_snapshot.variables)
                snapshot.events.extend(func_snapshot.events)
                snapshot.edges.extend(func_snapshot.edges)

            except Exception as e:
                # Log error but continue with other functions
                self._metrics.failed_functions += 1
                failed_function_list.append(function_node_id)
                logger.error(
                    f"[DfgBuilder] FAILED to build DFG for function {function_node_id}: {e}\n"
                    f"  Context:\n"
                    f"    - Blocks: {len(func_blocks)}\n"
                    f"    - Expressions: {sum(len(exprs_by_block.get(b.id, [])) for b in func_blocks)}\n"
                    f"  Continuing with other functions...",
                    exc_info=True,
                )
                continue

        # Record totals
        self._metrics.total_variables = len(snapshot.variables)
        self._metrics.total_events = len(snapshot.events)
        self._metrics.total_edges = len(snapshot.edges)

        logger.info(
            f"[DFG Metrics] Complete: {self._metrics.total_variables} vars, "
            f"{self._metrics.total_events} events, {self._metrics.total_edges} edges, "
            f"{self._metrics.failed_functions} failed functions"
        )

        # Log failed functions summary if any
        if failed_function_list:
            logger.error(
                "[DfgBuilder] Failed Functions Summary: "
                f"{len(failed_function_list)} function(s) failed DFG generation.\n"
                f"  First 10 failed: {failed_function_list[:10]}\n"
                "  These functions will have incomplete variable flow analysis."
            )

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
        2. Collect outer scope variables for closure detection
        3. Build parameter variables
        4. Process each block's expressions
        5. Generate data flow edges
        6. Track function variables for nested functions

        Args:
            func_node: Function IR node
            bfg_blocks: BFG blocks for this function
            exprs_by_block: Expressions grouped by block ID
            ir_doc: IR document

        Returns:
            DfgSnapshot for this function
        """
        from collections import defaultdict

        # Collect outer scope variables for closure detection
        outer_scope_vars = self._collect_outer_scope_vars(func_node.fqn)

        # Create context with outer scope info
        ctx = DfgContext(
            repo_id=ir_doc.repo_id,
            file_path=func_node.file_path,
            function_fqn=func_node.fqn,
            language=func_node.language,
            outer_scope_vars=outer_scope_vars,
        )

        # Create resolver state
        state = VarResolverState()

        # OPTIMIZATION Phase 2.5: Use defaultdict to avoid setdefault overhead (3-5% improvement)
        events_by_var: dict[str, list[VariableEvent]] = defaultdict(list)

        # 1. Build parameter variables from function children (with timing)
        start_time = time.perf_counter()
        self._create_parameter_variables(func_node, ir_doc, state, ctx)
        self._metrics.parameter_creation_ms += (time.perf_counter() - start_time) * 1000

        # 2. Process each BFG block's expressions (with timing)
        start_time = time.perf_counter()
        for i, block in enumerate(bfg_blocks):
            block_exprs = exprs_by_block.get(block.id, [])
            self._process_block_expressions(block, i, block_exprs, state, ctx, events_by_var)
        self._metrics.expression_processing_ms += (time.perf_counter() - start_time) * 1000

        # 3. Generate data flow edges (with timing)
        start_time = time.perf_counter()
        edges = self._build_dataflow_edges(exprs_by_block, ctx)
        self._metrics.edge_generation_ms += (time.perf_counter() - start_time) * 1000

        # 4. Track this function's variables for nested function closure detection
        self._track_function_variables(func_node.fqn, ctx)

        # 5. Build snapshot
        snapshot = DfgSnapshot(
            variables=list(ctx.variable_index.values()),
            events=[evt for evts in events_by_var.values() for evt in evts],
            edges=edges,
        )

        return snapshot

    def _collect_outer_scope_vars(self, function_fqn: str) -> dict[str, tuple[str, str]]:
        """
        Collect variables from enclosing scopes for closure detection.

        Args:
            function_fqn: Current function's fully qualified name

        Returns:
            Dict of {var_name: (var_id, scope_fqn)}
        """
        outer_vars: dict[str, tuple[str, str]] = {}

        if not function_fqn:
            return outer_vars

        # Find all enclosing scopes by FQN prefix
        # e.g., "module.outer.inner" has enclosing scopes "module.outer" and "module"
        parts = function_fqn.split(".")
        for i in range(len(parts) - 1, 0, -1):
            enclosing_fqn = ".".join(parts[:i])
            if enclosing_fqn in self._function_variables:
                for var_name, var_id in self._function_variables[enclosing_fqn].items():
                    # Don't override if already found in a more immediate scope
                    if var_name not in outer_vars:
                        outer_vars[var_name] = (var_id, enclosing_fqn)

        return outer_vars

    def _track_function_variables(self, function_fqn: str, ctx: DfgContext):
        """
        Track function's variables for nested function closure detection.

        Args:
            function_fqn: Function's fully qualified name
            ctx: DFG context with variable index
        """
        if not function_fqn:
            return

        self._function_variables[function_fqn] = {}
        for var_name, var_ids in ctx.name_to_ids.items():
            if var_ids:
                # Store the first (primary) variable ID
                self._function_variables[function_fqn][var_name] = var_ids[0]

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
        from src.contexts.code_foundation.infrastructure.ir.models import NodeKind

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
        # OPTIMIZATION: Cache variable ID lookups to avoid repeated resolve calls
        # Key: (var_name, is_write) -> var_id
        # is_write matters because writes may create new variables
        var_id_cache: dict[tuple[str, bool], str] = {}

        # OPTIMIZATION Phase 2.5: Cache ctx fields to reduce attribute access overhead
        # These fields are accessed in every event creation (2-3% improvement)
        ctx_repo_id = ctx.repo_id
        ctx_file_path = ctx.file_path
        ctx_function_fqn = ctx.function_fqn
        block_id = block.id

        for expr in expressions:
            # OPTIMIZATION: Cache expr attributes to reduce repeated lookups
            expr_id = expr.id
            expr_span = expr.span
            expr_inferred_type = expr.inferred_type
            expr_inferred_type_id = expr.inferred_type_id

            # Process reads (expr.reads_vars)
            for var_name in expr.reads_vars:
                # OPTIMIZATION: Check cache before resolving
                cache_key = (var_name, False)  # False = read
                if cache_key in var_id_cache:
                    var_id = var_id_cache[cache_key]
                else:
                    # Resolve or create variable
                    var_id = resolve_or_create_variable(var_name, block_idx, "local", state, ctx)
                    var_id_cache[cache_key] = var_id

                var_entity = ctx.variable_index[var_id]

                # If expression has inferred type, update variable
                if expr_inferred_type and var_entity.type_source == "unknown":
                    var_entity.inferred_type = expr_inferred_type
                    var_entity.inferred_type_id = expr_inferred_type_id
                    var_entity.type_source = "inferred"

                # OPTIMIZATION: Pre-compute event ID and span values
                event_id = f"evt:{var_id}:{expr_id}"
                start_line = expr_span.start_line if expr_span else None
                end_line = expr_span.end_line if expr_span else None

                # Create read event (using cached ctx fields)
                event = VariableEvent(
                    id=event_id,
                    repo_id=ctx_repo_id,
                    file_path=ctx_file_path,
                    function_fqn=ctx_function_fqn,
                    variable_id=var_id,
                    block_id=block_id,
                    ir_node_id=expr_id,
                    op_kind="read",
                    start_line=start_line,
                    end_line=end_line,
                )
                # OPTIMIZATION Phase 2.5: Direct append (defaultdict eliminates setdefault)
                events_by_var[var_id].append(event)
                block.used_variable_ids.append(var_id)

            # Process write (expr.defines_var)
            if expr.defines_var:
                var_name = expr.defines_var

                # OPTIMIZATION: Check cache before resolving
                # Note: Writes may create new variables, so we still need to call resolve
                # But we can avoid repeated calls for the same variable in the same block
                cache_key = (var_name, True)  # True = write
                if cache_key in var_id_cache:
                    var_id = var_id_cache[cache_key]
                else:
                    # Resolve or create variable
                    var_id = resolve_or_create_variable(var_name, block_idx, "local", state, ctx)
                    var_id_cache[cache_key] = var_id

                var_entity = ctx.variable_index[var_id]

                # If expression has inferred type, update variable
                if expr_inferred_type:
                    var_entity.inferred_type = expr_inferred_type
                    var_entity.inferred_type_id = expr_inferred_type_id
                    var_entity.type_source = "inferred"

                # OPTIMIZATION: Pre-compute event ID and span values (reuse from above)
                event_id = f"evt:{var_id}:{expr_id}"
                start_line = expr_span.start_line if expr_span else None
                end_line = expr_span.end_line if expr_span else None

                # Create write event (using cached ctx fields)
                event = VariableEvent(
                    id=event_id,
                    repo_id=ctx_repo_id,
                    file_path=ctx_file_path,
                    function_fqn=ctx_function_fqn,
                    variable_id=var_id,
                    block_id=block_id,
                    ir_node_id=expr_id,
                    op_kind="write",
                    start_line=start_line,
                    end_line=end_line,
                )
                # OPTIMIZATION Phase 2.5: Direct append (defaultdict eliminates setdefault)
                events_by_var[var_id].append(event)
                block.defined_variable_ids.append(var_id)

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
        from src.contexts.code_foundation.infrastructure.semantic_ir.expression.models import ExprKind

        # OPTIMIZATION: Pre-build name→ID lookup table to avoid repeated function calls
        # This converts O(n) function calls to O(1) dict lookups
        name_to_id: dict[str, str] = {}
        for var_name, var_ids in ctx.name_to_ids.items():
            if var_ids:
                name_to_id[var_name] = var_ids[0]  # Use first ID (same as find_variable_id_by_name)

        # OPTIMIZATION Phase 2.5: Cache ctx fields for edge creation (2-3% improvement)
        ctx_repo_id = ctx.repo_id
        ctx_file_path = ctx.file_path
        ctx_function_fqn = ctx.function_fqn

        edges: list[DataFlowEdge] = []
        edge_counter = 0

        for _, expressions in exprs_by_block.items():
            for expr in expressions:
                # OPTIMIZATION: Cache expression attributes to reduce repeated lookups
                expr_defines_var = expr.defines_var
                expr_reads_vars = expr.reads_vars
                expr_kind = expr.kind
                expr_attrs = expr.attrs

                # Assignment: defines_var + reads_vars
                if expr_defines_var and expr_reads_vars:
                    target_var_name = expr_defines_var

                    # OPTIMIZATION: Use pre-built lookup table instead of function call
                    target_var_id = name_to_id.get(target_var_name)
                    if target_var_id is None:
                        continue

                    # Determine edge kind
                    # Check if expression is a CALL or if it's an assignment with a call on the right side
                    is_call = expr_kind == ExprKind.CALL or expr_attrs.get("has_call_rhs", False)
                    edge_kind: Literal["assign", "alias"] = "assign" if is_call else "alias"

                    # OPTIMIZATION: Pre-format edge ID base to reduce string formatting overhead
                    edge_id_prefix = f"edge:{edge_kind}:"

                    # Create edges from source variables
                    for source_var_name in expr_reads_vars:
                        # OPTIMIZATION: Use pre-built lookup table instead of function call
                        source_var_id = name_to_id.get(source_var_name)
                        if source_var_id is None:
                            continue

                        # OPTIMIZATION: Use string concatenation instead of f-string for ID
                        edge_id = edge_id_prefix + str(edge_counter)

                        # Create edge (using cached ctx fields)
                        edge = DataFlowEdge(
                            id=edge_id,
                            from_variable_id=source_var_id,
                            to_variable_id=target_var_id,
                            kind=edge_kind,
                            repo_id=ctx_repo_id,
                            file_path=ctx_file_path,
                            function_fqn=ctx_function_fqn,
                        )
                        edges.append(edge)
                        edge_counter += 1

                # Return statement: reads_vars → special "return"
                # (attrs contain return info from ExpressionBuilder)
                if expr_kind == ExprKind.NAME_LOAD and expr_attrs.get("is_return"):
                    # OPTIMIZATION: Pre-format edge ID base for return edges
                    return_edge_prefix = "edge:return_value:"

                    for var_name in expr_reads_vars:
                        # OPTIMIZATION: Use pre-built lookup table instead of function call
                        var_id = name_to_id.get(var_name)
                        if var_id is None:
                            continue

                        # OPTIMIZATION: Use string concatenation instead of f-string for ID
                        edge_id = return_edge_prefix + str(edge_counter)

                        # Create return_value edge (using cached ctx fields)
                        edge = DataFlowEdge(
                            id=edge_id,
                            from_variable_id=var_id,
                            to_variable_id="return",  # Special target
                            kind="return_value",
                            repo_id=ctx_repo_id,
                            file_path=ctx_file_path,
                            function_fqn=ctx_function_fqn,
                        )
                        edges.append(edge)
                        edge_counter += 1

                # Function call: param_to_arg edges
                # Track data flow from argument variables to callee parameters
                # This enables inter-function data flow analysis
                if expr_kind == ExprKind.CALL:
                    call_args = expr_attrs.get("call_args", [])
                    callee_name = expr_attrs.get("callee_name", "")

                    if call_args and callee_name:
                        # Create param_to_arg edges for each argument
                        param_to_arg_prefix = "edge:param_to_arg:"

                        for arg_idx, arg_var_name in enumerate(call_args):
                            arg_var_id = name_to_id.get(arg_var_name)
                            if arg_var_id is None:
                                continue

                            edge_id = param_to_arg_prefix + str(edge_counter)

                            # Target: callee:param:{index} (symbolic target for cross-function linking)
                            # This allows retriever to link to actual parameter when callee is resolved
                            param_target = f"callee:{callee_name}:param:{arg_idx}"

                            edge = DataFlowEdge(
                                id=edge_id,
                                from_variable_id=arg_var_id,
                                to_variable_id=param_target,
                                kind="param_to_arg",
                                repo_id=ctx_repo_id,
                                file_path=ctx_file_path,
                                function_fqn=ctx_function_fqn,
                                attrs={"callee_name": callee_name, "arg_index": arg_idx},
                            )
                            edges.append(edge)
                            edge_counter += 1

        return edges

    # Helper methods

    def _group_expressions_by_block(self, expressions: list["Expression"]) -> dict[str, list["Expression"]]:
        """Group expressions by block ID"""
        from collections import defaultdict

        exprs_by_block: dict[str, list[Expression]] = defaultdict(list)

        for expr in expressions:
            if expr.block_id:
                exprs_by_block[expr.block_id].append(expr)

        return exprs_by_block

    def _group_blocks_by_function(self, bfg_blocks: list["BasicFlowBlock"]) -> dict[str, list["BasicFlowBlock"]]:
        """Group BFG blocks by function node ID"""
        from collections import defaultdict

        from src.contexts.code_foundation.infrastructure.semantic_ir.bfg.models import BasicFlowBlock

        blocks_by_func: dict[str, list[BasicFlowBlock]] = defaultdict(list)

        for block in bfg_blocks:
            func_id = block.function_node_id
            blocks_by_func[func_id].append(block)

        return blocks_by_func

    def _find_function_node(self, ir_doc: "IRDocument", function_node_id: str) -> "Node | None":
        """Find function node by ID"""
        from src.contexts.code_foundation.infrastructure.ir.models import NodeKind

        for node in ir_doc.nodes:
            if node.id == function_node_id and node.kind in (
                NodeKind.FUNCTION,
                NodeKind.METHOD,
            ):
                return node

        return None
