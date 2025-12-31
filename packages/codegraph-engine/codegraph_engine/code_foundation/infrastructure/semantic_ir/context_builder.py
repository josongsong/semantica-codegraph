"""
Context Builder for Context-Sensitive Analysis

Generates call-string contexts (k=1) for functions and variables.

Phase 1: Call-string context (k=1)
- Each function invocation gets unique context = call_site_id
- Variables inherit context from containing function

Example:
    def f(x):
        return x + 1

    def g():
        f(10)  # x gets context = call_site_1

    def h():
        f(20)  # x gets context = call_site_2
"""

from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.dfg.models import VariableEntity
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression


class ContextBuilder:
    """
    Generates call-string contexts (k=1)

    Algorithm:
    1. Find all CALL expressions
    2. For each call:
       - Create context = call_site_id
       - Map callee function → context
    3. For top-level functions:
       - context = None
    """

    def __init__(self):
        self.logger = get_logger(__name__)

    def build(
        self,
        variables: list["VariableEntity"],
        expressions: list["Expression"],
        repo_id: str = "",
    ) -> dict[str, str]:
        """
        Build context map: function_fqn → context

        Args:
            variables: All variables from DFG
            expressions: All expressions (for CALL sites)
            repo_id: Repository ID

        Returns:
            Dict mapping function_fqn to context (call_site_id)
        """
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import ExprKind

        context_map: dict[str, str] = {}

        # Step 1: Find all call sites
        call_sites: list[tuple[str, str]] = []  # (callee_fqn, call_site_id)

        for expr in expressions:
            if expr.kind != ExprKind.CALL:
                continue

            callee_name = expr.attrs.get("callee_name")
            if not callee_name:
                continue

            call_site_id = expr.id

            # Resolve callee FQN (simple for now)
            callee_fqn = self._resolve_callee_fqn(callee_name, expr, variables)
            if callee_fqn:
                call_sites.append((callee_fqn, call_site_id))

        # Step 2: Build context map
        for callee_fqn, call_site_id in call_sites:
            # For k=1, use call_site_id as context
            # Multiple calls → last call wins (simple for now)
            # TODO: Support multiple contexts (k > 1)
            context_map[callee_fqn] = call_site_id

        self.logger.debug(
            "context_map_built",
            contexts=len(context_map),
            call_sites=len(call_sites),
        )

        return context_map

    def apply_contexts(
        self,
        variables: list["VariableEntity"],
        context_map: dict[str, str],
    ) -> None:
        """
        Apply contexts to variables (in-place)

        Args:
            variables: Variables to update
            context_map: function_fqn → context
        """
        updated = 0
        for var in variables:
            func_fqn = var.function_fqn
            if func_fqn in context_map:
                var.context = context_map[func_fqn]
                updated += 1

        self.logger.debug(
            "contexts_applied",
            updated=updated,
            total=len(variables),
        )

    def _resolve_callee_fqn(
        self,
        callee_name: str,
        call_expr: "Expression",
        variables: list["VariableEntity"],
    ) -> str | None:
        """
        Resolve callee FQN from call expression

        Strategy:
        1. Try exact match with function_fqn from variables
        2. Try fuzzy match (endswith)
        3. Fall back to callee_name

        Args:
            callee_name: Simple function name from call
            call_expr: Call expression
            variables: All variables (for FQN lookup)

        Returns:
            Callee FQN or None
        """
        # Get all unique function FQNs
        func_fqns = {var.function_fqn for var in variables}

        # Try exact match
        if callee_name in func_fqns:
            return callee_name

        # Try fuzzy match (endswith)
        candidates = [fqn for fqn in func_fqns if fqn.endswith(f".{callee_name}")]
        if candidates:
            return candidates[0]  # First match

        # Try contains
        candidates = [fqn for fqn in func_fqns if callee_name in fqn]
        if candidates:
            return candidates[0]

        # Fall back to callee_name as-is
        return callee_name
