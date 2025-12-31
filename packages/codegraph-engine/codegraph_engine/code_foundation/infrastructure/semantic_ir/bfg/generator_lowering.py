"""
Generator Lowering to State Machine

Transforms Python generators (functions with yield) into explicit state machines.

Strategy (SOTA - CPython compatible):
1. Detect all yield points
2. Split function into states (each state = code between yields)
3. Create DISPATCHER block (routes to states based on __generator_state)
4. Lift ALL locals (no liveness analysis - CPython f_locals strategy)

Scope (Phase 1):
- Python yield (NOT yield from)
- Loops and conditionals containing yield
- NOT: try-finally with yield (warning only)

Author: Phase 1 Implementation
Date: 2025-12-09
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.models import (
    BasicFlowBlock,
    BFGBlockKind,
)

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode

    from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span
    from codegraph_engine.code_foundation.infrastructure.parsing import AstTree

logger = get_logger(__name__)


@dataclass
class YieldPoint:
    """
    Metadata for a single yield statement

    Attributes:
        state_id: State number (0 = initial, 1+ = after yield)
        ast_node: Tree-sitter AST node for yield
        yield_value: Expression being yielded (or None)
        span: Source location
        in_try_finally: True if inside try-finally (unsupported)
    """

    state_id: int
    ast_node: "TSNode"
    yield_value: str | None
    span: "Span"
    in_try_finally: bool = False


@dataclass
class StateContext:
    """
    Context while traversing AST (for tracking loops/branches)

    Attributes:
        scope_id: Unique ID for this scope
        loop_header_block_id: Current loop header (for continue/break)
        in_try_finally: True if inside try-finally block
    """

    scope_id: str
    loop_header_block_id: str | None = None
    in_try_finally: bool = False


class GeneratorLowering:
    """
    Lower Python generator to State Machine BFG

    Algorithm:
    1. Find all yield points (DFS traversal)
    2. Collect ALL local variables (CPython strategy)
    3. Create DISPATCHER → State 0 → YIELD 0 → RESUME 1 → ... → EXIT
    4. Handle loops: RESUME blocks connect back to loop headers

    CRITICAL: This does NOT generate IR instructions.
    It only creates BFG structure with metadata.
    CFG Builder will create actual edges.
    """

    def __init__(self):
        self.logger = get_logger(f"{__name__}.GeneratorLowering")
        self._blocks: list[BasicFlowBlock] = []
        self._block_counter = 0
        self._yield_points: list[YieldPoint] = []
        self._all_locals: set[str] = set()

    def lower(
        self,
        func_ast: "TSNode",
        ast_tree: "AstTree",
        bfg_id: str,
        function_node_id: str,
    ) -> tuple[list[BasicFlowBlock], int]:
        """
        Transform generator function to state machine

        Args:
            func_ast: Function AST node (must contain yield)
            ast_tree: AST tree (for text extraction)
            bfg_id: BFG ID (e.g., "bfg:my_func")
            function_node_id: IR function node ID

        Returns:
            (blocks, yield_count)
            blocks: List of BFG blocks representing state machine
            yield_count: Number of yield statements found

        Raises:
            ValueError: If function has no yield (not a generator)

        CRITICAL: Caller MUST verify this is a generator first

        Updated 2025-12-09: Phase 1.1 - Now creates actual code blocks
        """
        # Reset state
        self._blocks = []
        self._block_counter = 0
        self._yield_points = []
        self._all_locals = set()
        self._func_ast = func_ast  # Store for splitting

        # Step 1: Find all yield points
        self._find_yield_points(func_ast, ast_tree)

        if not self._yield_points:
            raise ValueError(
                f"Function {function_node_id} has no yield statements. "
                "Not a generator. Caller must check is_generator first."
            )

        # Step 2: Collect ALL locals (SOTA: CPython f_locals strategy)
        # No liveness analysis - just lift everything
        self._collect_all_locals(func_ast, ast_tree)

        self.logger.info(
            "generator_lowering_start",
            function_id=function_node_id,
            yield_count=len(self._yield_points),
            locals_count=len(self._all_locals),
        )

        # Step 3: Validate (check for unsupported patterns)
        self._validate_yield_points()

        # Step 4: Split AST at yield points (Phase 1.1)
        code_segments = self._split_ast_at_yields(func_ast, ast_tree)

        # Step 5: Create state machine blocks with actual code
        blocks = self._create_state_machine_with_code(bfg_id, function_node_id, ast_tree, code_segments)

        self.logger.info(
            "generator_lowering_complete",
            function_id=function_node_id,
            block_count=len(blocks),
        )

        return blocks, len(self._yield_points)

    def _find_yield_points(self, node: "TSNode", ast_tree: "AstTree"):
        """
        DFS traversal to find all yield statements

        CRITICAL: This assigns state IDs sequentially (0, 1, 2, ...)
        State 0 = before first yield
        State 1 = after first yield, before second yield
        ...

        CRITICAL FIX (2025-12-09): Python yield has 2-level structure

        AST Structure:
            yield [3:4] 'yield x'         <- Parent (expression)
              yield [3:4] 'yield'         <- Child (keyword token)
              identifier [3:10] 'x'

        We only want to count the PARENT node (has children).
        The child "yield" token should be skipped.

        Args:
            node: Current AST node
            ast_tree: AST tree for span extraction
        """
        # Python yield - only process parent node (not keyword token)
        if node.type == "yield":
            # AST Structure:
            #   Parent: yield [3:4] 'yield x' (has children: keyword + value)
            #   Child:  yield [3:4] 'yield'   (keyword token, NO children or only whitespace)

            # Strategy: Only process if first child is "yield" keyword
            # This means we're at the parent expression level
            first_child = node.children[0] if node.child_count > 0 else None

            if first_child and first_child.type == "yield":
                # This is the PARENT expression node - process it
                self._add_yield_point(node, ast_tree)
                return
            # else: This is keyword token - skip (parent will process)

        # ⭐ P2-1: JavaScript/TypeScript yield support
        # JS/TS uses "yield_expression" node type
        elif node.type == "yield_expression":
            # JS/TS AST Structure:
            #   yield_expression [3:4] 'yield x'
            #     └─ identifier/expression (the yielded value)
            # or
            #   yield_expression [3:4] 'yield* iter'
            #     └─ yield* (delegated yield)
            self._add_yield_point(node, ast_tree, is_js_ts=True)
            return

        # Recurse (DFS) - visit ALL nodes
        for child in node.children:
            self._find_yield_points(child, ast_tree)

    def _add_yield_point(
        self,
        node: "TSNode",
        ast_tree: "AstTree",
        is_js_ts: bool = False,
    ) -> None:
        """
        ⭐ P2-1: Unified yield point extraction for Python and JS/TS

        Handles both:
        - Python: yield expr
        - JavaScript/TypeScript: yield expr, yield* expr

        Args:
            node: AST node for yield expression
            ast_tree: AST tree for text/span extraction
            is_js_ts: True if processing JS/TS yield_expression
        """
        state_id = len(self._yield_points)

        # Extract yielded value based on language
        value_expr: str | None = None

        if is_js_ts:
            # JS/TS: yield_expression may have children [yield, expression]
            # or [yield, *, expression] for yield*
            for child in node.children:
                # Skip yield keyword and * operator
                if child.type not in ("yield", "*"):
                    value_expr = ast_tree.get_text(child)
                    break
        else:
            # Python: Skip first child (keyword token)
            for child in node.children:
                if child.type != "yield":
                    value_expr = ast_tree.get_text(child)
                    break

        # Check if inside try-finally (unsupported)
        in_try_finally = self._is_inside_try_finally(node)

        yield_point = YieldPoint(
            state_id=state_id,
            ast_node=node,
            yield_value=value_expr,
            span=ast_tree.get_span(node),
            in_try_finally=in_try_finally,
        )
        self._yield_points.append(yield_point)

        self.logger.debug(
            "yield_point_found",
            state_id=state_id,
            value=value_expr,
            language="js/ts" if is_js_ts else "python",
            line=yield_point.span.start_line if yield_point.span else "?",
        )

    def _collect_all_locals(self, func_ast: "TSNode", ast_tree: "AstTree"):
        """
        Collect ALL local variables in function scope

        SOTA Strategy (CPython f_locals):
        - Find all assignment targets (x = ...)
        - Find all for-loop variables (for x in ...)
        - Find all function parameters
        - NO filtering (lift everything)

        Why? Python's dynamic nature makes precise liveness analysis impossible.
        CPython's PyFrameObject.f_locals does the same.

        Args:
            func_ast: Function AST node
            ast_tree: AST tree for text extraction

        CRITICAL: Error handling added to prevent crash on malformed AST
        """
        try:
            # Find all identifiers on LHS of assignments
            def traverse(node: "TSNode"):
                try:
                    # Assignment: x = ...
                    if node.type == "assignment":
                        left = node.child_by_field_name("left")
                        if left and left.type == "identifier":
                            var_name = ast_tree.get_text(left)
                            self._all_locals.add(var_name)

                    # For loop: for x in ...
                    elif node.type == "for_statement":
                        left = node.child_by_field_name("left")
                        if left and left.type == "identifier":
                            var_name = ast_tree.get_text(left)
                            self._all_locals.add(var_name)

                    # With statement: with ... as x
                    elif node.type == "with_statement":
                        # Handle: with_clause -> as_pattern -> as_pattern_target
                        for child in node.children:
                            if child.type == "with_clause":
                                alias = child.child_by_field_name("alias")
                                if alias and alias.type == "as_pattern_target":
                                    var_name = ast_tree.get_text(alias)
                                    self._all_locals.add(var_name)

                    # Recurse
                    for child in node.children:
                        traverse(child)

                except Exception as e:
                    # Malformed node - skip
                    self.logger.debug(f"Skipping malformed node: {e}")

            # Find function parameters
            params_node = func_ast.child_by_field_name("parameters")
            if params_node:
                for child in params_node.children:
                    if child.type == "identifier":
                        param_name = ast_tree.get_text(child)
                        self._all_locals.add(param_name)

            # Find assignments in body
            body_node = func_ast.child_by_field_name("body")
            if body_node:
                traverse(body_node)

            self.logger.debug(
                "locals_collected",
                count=len(self._all_locals),
                locals=sorted(self._all_locals),
            )

        except Exception as e:
            # Critical error in locals collection
            self.logger.error(
                "locals_collection_failed",
                error=str(e),
                message="Using empty locals set (conservative fallback)",
            )
            # Conservative: empty set (may cause runtime errors, but safe for analysis)
            self._all_locals = set()

    def _validate_yield_points(self):
        """
        Validate yield points for unsupported patterns

        Phase 1 Exclusions:
        - yield inside try-finally (ERROR - not warning)
        - yield from (will be caught earlier)

        Raises:
            ValueError: If unsupported pattern detected
        """
        for yp in self._yield_points:
            if yp.in_try_finally:
                error_msg = (
                    f"Yield inside try-finally is NOT supported in Phase 1. "
                    f"Line {yp.span.start_line if yp.span else '?'}. "
                    "State machine cannot preserve exception handlers correctly."
                )
                self.logger.error(
                    "yield_in_try_finally_unsupported",
                    state_id=yp.state_id,
                    line=yp.span.start_line if yp.span else "?",
                )
                raise ValueError(error_msg)

    def _is_inside_try_finally(self, node: "TSNode") -> bool:
        """
        Check if node is inside try-finally block

        CRITICAL FIX (2025-12-09):
        AST Structure:
            try_statement
              ├─ block (yield is here)
              └─ finally_clause (sibling, not parent!)

        Need to check if parent try_statement has finally_clause sibling.

        Args:
            node: AST node to check

        Returns:
            True if inside try block with finally clause
        """
        current = node.parent
        while current:
            if current.type == "try_statement":
                # Check if this try has a finally_clause sibling
                for child in current.children:
                    if child.type == "finally_clause":
                        return True
            current = current.parent
        return False

    def _split_ast_at_yields(
        self,
        func_ast: "TSNode",
        ast_tree: "AstTree",
    ) -> list[tuple[int, list["TSNode"]]]:
        """
        Split function body into segments at yield points

        Algorithm:
        1. Get all statements in function body
        2. For each yield, find containing statement
        3. Split statements into segments: [before_yield_0, before_yield_1, ...]

        Args:
            func_ast: Function AST node
            ast_tree: AST tree

        Returns:
            List of (state_id, statements) tuples
            Example: [(0, [stmt1, stmt2]), (1, [stmt3, stmt4]), ...]

        Phase 1.1 Implementation
        """
        # Get function body
        body_node = func_ast.child_by_field_name("body")
        if not body_node:
            return []

        # Collect all statements in body
        all_statements = []
        for child in body_node.children:
            if child.is_named and child.type != "comment":
                all_statements.append(child)

        # Build statement → state mapping
        # Each yield point splits the code
        stmt_to_state = {}
        current_state = 0

        for stmt in all_statements:
            # Check if this statement contains a yield
            contains_yield = self._contains_yield(stmt)

            if contains_yield:
                # This statement has yield - belongs to current state
                stmt_to_state[id(stmt)] = current_state
                # Next statements belong to next state
                current_state += 1
            else:
                # No yield - belongs to current state
                stmt_to_state[id(stmt)] = current_state

        # Group statements by state
        segments = []
        for state_id in range(len(self._yield_points) + 1):
            state_stmts = [stmt for stmt in all_statements if stmt_to_state.get(id(stmt)) == state_id]
            if state_stmts:  # Only add non-empty segments
                segments.append((state_id, state_stmts))

        return segments

    def _contains_yield(self, node: "TSNode") -> bool:
        """Check if node contains yield (DFS) - supports Python and JS/TS"""
        # Python yield
        if node.type == "yield":
            return True
        # ⭐ P2-1: JavaScript/TypeScript yield
        if node.type == "yield_expression":
            return True
        for child in node.children:
            if self._contains_yield(child):
                return True
        return False

    def _create_state_machine_with_code(
        self,
        bfg_id: str,
        function_node_id: str,
        ast_tree: "AstTree",
        code_segments: list[tuple[int, list["TSNode"]]],
    ) -> list[BasicFlowBlock]:
        """
        Create state machine BFG blocks WITH actual code

        Structure (SOTA - Phase 1.1):
        =============================
        DISPATCHER (state router)
        ├─> State 0: [stmt1, stmt2, yield x]
        │   └─> YIELD 0 (suspend)
        │       └─> RESUME_YIELD 1 (resume)
        │           └─> State 1: [stmt3, stmt4, yield y]
        │               └─> YIELD 1
        │                   └─> ...

        Args:
            bfg_id: BFG ID
            function_node_id: Function node ID
            ast_tree: AST tree
            code_segments: List of (state_id, statements) from splitting

        Returns:
            Complete list of blocks (DISPATCHER + STATE + YIELD + RESUME)

        Phase 1.1 Complete Implementation
        """
        blocks = []

        # 1. Create DISPATCHER block
        dispatcher = self._create_dispatcher_block(bfg_id, function_node_id)
        blocks.append(dispatcher)

        # 2. Create blocks for each state
        for state_id, statements in code_segments:
            # Create STATE block (code before/including yield)
            state_block = self._create_state_block(
                bfg_id,
                function_node_id,
                state_id,
                statements,
                ast_tree,
            )
            blocks.append(state_block)

            # If this segment contains yield, add YIELD block
            if state_id < len(self._yield_points):
                yp = self._yield_points[state_id]

                yield_block = self._create_yield_block(
                    bfg_id,
                    function_node_id,
                    yp,
                    ast_tree,
                )
                blocks.append(yield_block)

                # Add RESUME block (for next state)
                if state_id < len(self._yield_points) - 1:
                    resume_block = self._create_resume_block(
                        bfg_id,
                        function_node_id,
                        state_id=state_id + 1,
                    )
                    blocks.append(resume_block)

        return blocks

    def _create_dispatcher_block(
        self,
        bfg_id: str,
        function_node_id: str,
    ) -> BasicFlowBlock:
        """
        Create DISPATCHER block

        Metadata:
            generator_dispatch_table: {0: "bfg:func:state:0", 1: "bfg:func:state:1", ...}

        CFG Builder will use this to create conditional edges:
            if __generator_state == 0: goto state_0
            elif __generator_state == 1: goto state_1
            ...

        Phase 1.1: Uses actual block ID patterns (not placeholders)
        """
        block_id = f"{bfg_id}:dispatcher"

        # Build dispatch table with actual block ID patterns
        # State N → "bfg:func:state:N"
        dispatch_table = {}
        for i in range(len(self._yield_points) + 1):
            # State 0 = initial (before first yield)
            # State 1, 2, ... = after yield 0, 1, ...
            dispatch_table[i] = f"{bfg_id}:state:{i}"

        block = BasicFlowBlock(
            id=block_id,
            kind=BFGBlockKind.DISPATCHER,
            function_node_id=function_node_id,
            statement_count=0,
            generator_dispatch_table=dispatch_table,
            generator_all_locals=list(self._all_locals),
        )

        return block

    def _create_yield_block(
        self,
        bfg_id: str,
        function_node_id: str,
        yield_point: YieldPoint,
        ast_tree: "AstTree",
    ) -> BasicFlowBlock:
        """
        Create YIELD block

        Metadata:
            generator_state_id: Current state
            generator_next_state: Next state (after resume)
            generator_yield_value: Expression to yield
        """
        block_id = f"{bfg_id}:yield:{yield_point.state_id}"

        block = BasicFlowBlock(
            id=block_id,
            kind=BFGBlockKind.YIELD,
            function_node_id=function_node_id,
            span=yield_point.span,
            statement_count=1,  # yield itself
            generator_state_id=yield_point.state_id,
            generator_next_state=yield_point.state_id + 1,
            generator_yield_value=yield_point.yield_value,
            generator_all_locals=list(self._all_locals),
        )

        return block

    def _create_resume_block(
        self,
        bfg_id: str,
        function_node_id: str,
        state_id: int,
    ) -> BasicFlowBlock:
        """
        Create RESUME_YIELD block

        Metadata:
            generator_resume_from_state: Which state we're resuming from
        """
        block_id = f"{bfg_id}:resume:{state_id}"

        block = BasicFlowBlock(
            id=block_id,
            kind=BFGBlockKind.RESUME_YIELD,
            function_node_id=function_node_id,
            statement_count=0,  # Resume point (no actual statements)
            generator_resume_from_state=state_id - 1,
            generator_all_locals=list(self._all_locals),
        )

        return block

    def _create_state_block(
        self,
        bfg_id: str,
        function_node_id: str,
        state_id: int,
        statements: list["TSNode"],
        ast_tree: "AstTree",
    ) -> BasicFlowBlock:
        """
        Create STATE block (actual code between yields)

        This block contains the real Python statements:
        - Assignments (x = 1)
        - Function calls (print(x))
        - Control flow (if/while - simplified for Phase 1)

        Args:
            bfg_id: BFG ID
            function_node_id: Function node ID
            state_id: State number
            statements: AST nodes for this state's code
            ast_tree: AST tree for span extraction

        Returns:
            STATEMENT block with actual code

        Phase 1.1 Implementation
        """
        block_id = f"{bfg_id}:state:{state_id}"

        # Calculate span (from first to last statement)
        if statements:
            first_stmt = statements[0]
            last_stmt = statements[-1]

            from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span

            span = Span(
                start_line=first_stmt.start_point[0] + 1,  # Tree-sitter is 0-based
                start_col=first_stmt.start_point[1],
                end_line=last_stmt.end_point[0] + 1,
                end_col=last_stmt.end_point[1],
            )
        else:
            span = None

        # Count statements (exclude yield itself for cleaner count)
        stmt_count = sum(1 for stmt in statements if not self._contains_yield(stmt))

        block = BasicFlowBlock(
            id=block_id,
            kind=BFGBlockKind.STATEMENT,
            function_node_id=function_node_id,
            span=span,
            statement_count=max(1, stmt_count),  # At least 1
            generator_all_locals=list(self._all_locals),
        )

        return block
