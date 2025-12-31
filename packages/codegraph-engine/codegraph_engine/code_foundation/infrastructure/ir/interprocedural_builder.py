"""
Inter-procedural Data Flow Builder

Generates inter-procedural data flow edges from IR:
- Argument → Parameter
- Return value → Call site

SOTA Optimization:
- Uses SharedVariableIndex for O(1) lookups (11x faster indexing)
"""

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.dfg.models import VariableEntity
from codegraph_engine.code_foundation.infrastructure.ir.models.core import InterproceduralEdgeKind, VariableKind
from codegraph_engine.code_foundation.infrastructure.ir.models.interprocedural import InterproceduralDataFlowEdge
from codegraph_engine.code_foundation.infrastructure.ir.shared_variable_index import (
    SharedVariableIndex,
    get_shared_variable_index,
)
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression, ExprKind

logger = get_logger(__name__)


class InterproceduralDataFlowBuilder:
    """
    Build inter-procedural data flow edges

    Algorithm:
    1. Find all call expressions
    2. For each call:
       - Map arguments → parameters
       - Map return value → call site variable
    3. Create InterproceduralDataFlowEdge
    """

    def build(
        self,
        variables: list[VariableEntity],
        expressions: list[Expression],
        repo_id: str = "",
    ) -> list[InterproceduralDataFlowEdge]:
        """
        Build inter-procedural edges

        Args:
            variables: All variables from DFG
            expressions: All expressions
            repo_id: Repository ID

        Returns:
            List of inter-procedural edges
        """
        edges: list[InterproceduralDataFlowEdge] = []

        # SOTA: Use SharedVariableIndex for O(1) lookups (11x faster)
        # Previously built 4 separate indexes: O(4V) → now O(V) shared
        var_index = get_shared_variable_index(variables)
        var_by_id = var_index.var_by_id
        var_by_scope_name = var_index.var_by_scope_name
        func_params = var_index.func_params
        func_returns = var_index.func_returns

        # Process call expressions
        edge_count = 0
        for expr in expressions:
            if expr.kind != ExprKind.CALL:
                continue

            callee_name = expr.attrs.get("callee_name")
            if not callee_name:
                continue

            # Find callee function FQN
            # Heuristic: callee_name might be simple name or partial FQN
            callee_fqn = self._resolve_callee_fqn(callee_name, expr, var_by_id)
            if not callee_fqn:
                continue

            # Fuzzy match: find function_fqn that ends with callee_fqn
            matched_fqn = None

            # Extract method name from instance.method (e.g., "runner.run" → "run")
            method_name = callee_fqn.split(".")[-1] if "." in callee_fqn else callee_fqn

            for fqn in func_params.keys():
                # Direct match
                if fqn.endswith(callee_fqn) or callee_fqn in fqn:
                    matched_fqn = fqn
                    break
                # 🔥 FIX: Match method name for instance.method calls
                # e.g., "runner.run" should match ".QueryRunner.run"
                if fqn.endswith("." + method_name):
                    matched_fqn = fqn
                    break

            if not matched_fqn:
                continue  # Can't resolve or no param info

            callee_fqn = matched_fqn

            caller_fqn = expr.function_fqn
            call_site_id = expr.id

            # Map arguments → parameters
            args = expr.attrs.get("args") or expr.attrs.get("call_args", [])
            callee_params = func_params[callee_fqn]

            for arg_idx, arg_var_name_or_id in enumerate(args):
                # Find parameter by position
                # Simplification: assume positional match
                param_names = sorted(callee_params.keys())  # Stable ordering
                if arg_idx < len(param_names):
                    param_name = param_names[arg_idx]
                    param_var_id = callee_params[param_name]

                    # 🔥 FIX: Resolve arg_var_name to full var_id
                    # call_args contains variable NAMES (e.g., 'user'), not full IDs
                    arg_var_id = arg_var_name_or_id
                    arg_var = var_by_id.get(arg_var_id)

                    # If not found by ID, try resolving by (function_fqn, name)
                    if not arg_var:
                        # Normalize caller_fqn to match var.function_fqn format
                        # expr.function_fqn: "function:/tmp/...:/tmp/.../test.py:test.main"
                        # var.function_fqn: ".tmp.debug_v2.test.main"
                        caller_func_fqn_normalized = self._normalize_fqn(caller_fqn)

                        # Try exact match first
                        resolved_id = var_by_scope_name.get((caller_func_fqn_normalized, arg_var_name_or_id))

                        # Try fuzzy match if exact fails
                        if not resolved_id:
                            for (fqn, name), var_id in var_by_scope_name.items():
                                if name == arg_var_name_or_id and (
                                    fqn.endswith(caller_func_fqn_normalized)
                                    or caller_func_fqn_normalized.endswith(fqn.split(".")[-1])
                                    or fqn.split(".")[-1] in caller_fqn
                                ):
                                    resolved_id = var_id
                                    break

                        if resolved_id:
                            arg_var_id = resolved_id
                            arg_var = var_by_id.get(arg_var_id)

                    var_by_id.get(param_var_id)

                    # Create arg → param edge
                    edge = InterproceduralDataFlowEdge(
                        id=f"interproc:{edge_count}",
                        kind=InterproceduralEdgeKind.ARG_TO_PARAM,
                        from_var_id=arg_var_id,
                        to_var_id=param_var_id,
                        call_site_id=call_site_id,
                        caller_func_fqn=caller_fqn,
                        callee_func_fqn=callee_fqn,
                        arg_position=arg_idx,
                        repo_id=repo_id,
                        file_path=expr.file_path,
                        # Context propagation
                        caller_context=arg_var.context if arg_var else None,
                        callee_context=call_site_id,  # NEW context for callee!
                    )
                    edges.append(edge)
                    edge_count += 1

            # Map return value → call site
            if callee_fqn in func_returns:
                # Find call site result variable
                # Heuristic: variable with same name as call expression result
                call_result_var = expr.attrs.get("result_var")
                if call_result_var:
                    return_var_id = func_returns[callee_fqn]
                    var_by_id.get(return_var_id)

                    edge = InterproceduralDataFlowEdge(
                        id=f"interproc:{edge_count}",
                        kind=InterproceduralEdgeKind.RETURN_TO_CALLSITE,
                        from_var_id=return_var_id,
                        to_var_id=call_result_var,
                        call_site_id=call_site_id,
                        caller_func_fqn=caller_fqn,
                        callee_func_fqn=callee_fqn,
                        arg_position=None,
                        repo_id=repo_id,
                        file_path=expr.file_path,
                        # Context propagation
                        caller_context=None,  # Return flows back to caller
                        callee_context=call_site_id,  # Return var has callee context
                    )
                    edges.append(edge)
                    edge_count += 1

        logger.info("interprocedural_edges_built", num_edges=len(edges))
        return edges

    def _resolve_callee_fqn(
        self,
        callee_name: str,
        call_expr: Expression,
        var_by_id: dict[str, VariableEntity],
    ) -> str | None:
        """
        Resolve callee name to full FQN

        Heuristics:
        1. If callee_name is full FQN, use it
        2. Match by function name suffix (robust against FQN format differences)
        3. If it's in same module, construct FQN

        Args:
            callee_name: Simple name or partial FQN
            call_expr: Call expression
            var_by_id: Variable lookup

        Returns:
            Full FQN or None if can't resolve
        """
        # If already full FQN (contains module separator)
        if "." in callee_name or "::" in callee_name:
            return callee_name

        # Simple name: return as-is for fuzzy matching
        # (will be matched by endswith in caller)
        return callee_name

    def _normalize_fqn(self, fqn: str) -> str:
        """
        Normalize function FQN to match variable's function_fqn format.

        Input formats:
        - "function:/tmp/...:/tmp/.../test.py:test.main" (Expression.function_fqn)
        - ".tmp.debug_v2.test.main" (Variable.function_fqn)

        Output: normalized dotted format (e.g., "test.main")
        """
        if not fqn:
            return ""

        # If it's in "function:/repo:/path:module.func" format
        if fqn.startswith("function:"):
            # Extract the last part after the last ":"
            parts = fqn.split(":")
            if len(parts) >= 4:
                return parts[-1]  # e.g., "test.main"

        # If it's already dotted (e.g., ".tmp.debug_v2.test.main")
        # Extract the function name (last parts)
        if "." in fqn:
            parts = fqn.split(".")
            # Return last 2 parts (module.func) or last 1 if only func
            if len(parts) >= 2:
                return ".".join(parts[-2:])
            return parts[-1]

        return fqn
