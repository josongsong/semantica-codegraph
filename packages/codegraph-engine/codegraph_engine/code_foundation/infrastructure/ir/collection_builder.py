"""
Collection Data Flow Builder (Heap-Sensitive Analysis)

Generates data flow edges through collections:
- list.append(x) → list element tainted
- dict[key] = x → dict element tainted
- for item in list → item receives taint from list elements
- dict[key] / dict.get(key) → value receives taint

RFC-030: Advanced Taint Analysis - Heap-Sensitive Collection Tracking

SOTA Optimization:
- Uses SharedVariableIndex for O(1) lookups (11x faster indexing)
"""

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.dfg.models import VariableEntity
from codegraph_engine.code_foundation.infrastructure.ir.models.core import InterproceduralEdgeKind
from codegraph_engine.code_foundation.infrastructure.ir.models.interprocedural import (
    InterproceduralDataFlowEdge,
)
from codegraph_engine.code_foundation.infrastructure.ir.shared_variable_index import (
    get_shared_variable_index,
)
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import (
    Expression,
    ExprKind,
)

logger = get_logger(__name__)

# Collection mutation methods that propagate taint TO the collection
COLLECTION_STORE_METHODS = {
    # List methods
    "append": {"collection_type": "list", "arg_index": 0},
    "extend": {"collection_type": "list", "arg_index": 0, "is_iterable": True},
    "insert": {"collection_type": "list", "arg_index": 1},  # insert(index, value)
    # Set methods
    "add": {"collection_type": "set", "arg_index": 0},
    "update": {"collection_type": "set", "arg_index": 0, "is_iterable": True},
    # Dict methods
    "__setitem__": {"collection_type": "dict", "arg_index": 1},  # dict[key] = value
    "setdefault": {"collection_type": "dict", "arg_index": 1},
    # Queue/Deque
    "put": {"collection_type": "queue", "arg_index": 0},
    "appendleft": {"collection_type": "deque", "arg_index": 0},
}

# Collection access methods that propagate taint FROM the collection
# Note: get() and pop() are polymorphic (work on dict/queue and dict/list respectively)
COLLECTION_LOAD_METHODS = {
    # Dict methods
    "__getitem__": {"collection_type": "dict"},  # dict[key]
    "get": {"collection_type": "dict|queue"},  # get() on dict/queue
    "pop": {"collection_type": "dict|list"},  # pop() on dict/list
    "values": {"collection_type": "dict", "returns_iterator": True},
    "items": {"collection_type": "dict", "returns_iterator": True},
    # Deque
    "popleft": {"collection_type": "deque"},
}


class CollectionDataFlowBuilder:
    """
    Build data flow edges through collections (Heap-Sensitive Analysis)

    Key insight: Collections act as "taint containers"
    - Store operations: taint flows INTO collection
    - Load operations: taint flows OUT OF collection
    - Abstract heap: collection[*] represents "any element"

    Algorithm:
    1. Detect collection operations (append, __setitem__, etc.)
    2. Create abstract heap location for collection elements
    3. Generate collection_store edges (value → collection[*])
    4. Detect iteration/access patterns
    5. Generate collection_load edges (collection[*] → iterator var)
    """

    def __init__(self) -> None:
        # Track collections and their abstract element locations
        # collection_var_id → abstract_element_id
        self._collection_elements: dict[str, str] = {}
        self._edge_count = 0

    def build(
        self,
        variables: list[VariableEntity],
        expressions: list[Expression],
        repo_id: str = "",
    ) -> list[InterproceduralDataFlowEdge]:
        """
        Build collection data flow edges

        Args:
            variables: All variables from DFG
            expressions: All expressions
            repo_id: Repository ID

        Returns:
            List of collection data flow edges
        """
        edges: list[InterproceduralDataFlowEdge] = []
        self._edge_count = 0

        # SOTA: Use SharedVariableIndex for O(1) lookups (11x faster)
        # Previously built 3 separate indexes: O(3V) → now O(V) shared
        var_index = get_shared_variable_index(variables)
        var_by_id = var_index.var_by_id
        var_by_scope_name = var_index.var_by_scope_name
        call_vars_by_line = var_index.call_vars_by_line

        # First pass: Detect collection stores (append, __setitem__, etc.)
        for expr in expressions:
            if expr.kind != ExprKind.CALL:
                continue

            callee = expr.attrs.get("callee_name", "")
            call_args = expr.attrs.get("call_args", [])

            # Check for method call pattern: obj.method()
            if "." in callee:
                parts = callee.rsplit(".", 1)
                if len(parts) == 2:
                    obj_name, method_name = parts

                    # Check if it's a collection store method
                    if method_name in COLLECTION_STORE_METHODS:
                        store_info = COLLECTION_STORE_METHODS[method_name]
                        arg_idx = store_info.get("arg_index", 0)

                        if arg_idx < len(call_args):
                            value_arg = call_args[arg_idx]

                            # 🔥 FIX: Special handling for <call> variables
                            # <call> variables need line-based resolution
                            if value_arg == "<call>":
                                expr_line = expr.span.start_line if expr.span else 0
                                call_vars = call_vars_by_line.get(expr_line, [])
                                value_var_id = call_vars[0].id if call_vars else None
                            else:
                                # Resolve value to full var_id
                                value_var_id = self._resolve_var_id(value_arg, expr.function_fqn, var_by_scope_name)

                            # Resolve collection to full var_id
                            collection_var_id = self._resolve_var_id(obj_name, expr.function_fqn, var_by_scope_name)

                            if value_var_id and collection_var_id:
                                # Create abstract element location
                                element_id = f"{collection_var_id}[*]"
                                self._collection_elements[collection_var_id] = element_id

                                edge = InterproceduralDataFlowEdge(
                                    id=f"collection:{self._edge_count}",
                                    kind=InterproceduralEdgeKind.COLLECTION_STORE,
                                    from_var_id=value_var_id,
                                    to_var_id=element_id,
                                    call_site_id=expr.id,
                                    caller_func_fqn=expr.function_fqn,
                                    callee_func_fqn=f"{collection_var_id}.{method_name}",
                                    arg_position=arg_idx,
                                    repo_id=repo_id,
                                    file_path=expr.file_path,
                                    collection_var_id=collection_var_id,
                                    element_key="*",  # Any element
                                )
                                edges.append(edge)
                                self._edge_count += 1
                                logger.debug(f"collection_store: {value_arg} → {obj_name}[*]")

                    # Check if it's a collection load method
                    elif method_name in COLLECTION_LOAD_METHODS:
                        # Resolve collection to full var_id
                        collection_var_id = self._resolve_var_id(obj_name, expr.function_fqn, var_by_scope_name)

                        if collection_var_id:
                            # Check if collection has abstract element
                            element_id = self._collection_elements.get(collection_var_id, f"{collection_var_id}[*]")

                            # Result variable (if assigned)
                            result_var = expr.attrs.get("result_var")
                            if result_var:
                                edge = InterproceduralDataFlowEdge(
                                    id=f"collection:{self._edge_count}",
                                    kind=InterproceduralEdgeKind.COLLECTION_LOAD,
                                    from_var_id=element_id,
                                    to_var_id=result_var,
                                    call_site_id=expr.id,
                                    caller_func_fqn=expr.function_fqn,
                                    callee_func_fqn=f"{collection_var_id}.{method_name}",
                                    arg_position=None,
                                    repo_id=repo_id,
                                    file_path=expr.file_path,
                                    collection_var_id=collection_var_id,
                                    element_key="*",
                                )
                                edges.append(edge)
                                self._edge_count += 1
                                logger.debug(f"collection_load: {obj_name}[*] → {result_var}")

        # Second pass: Detect for-loop iteration patterns
        edges.extend(self._build_iteration_edges(expressions, var_by_id, var_by_scope_name, repo_id))

        logger.info("collection_edges_built", num_edges=len(edges))
        return edges

    def _build_iteration_edges(
        self,
        expressions: list[Expression],
        var_by_id: dict[str, VariableEntity],
        var_by_scope_name: dict[tuple[str, str], str],
        repo_id: str,
    ) -> list[InterproceduralDataFlowEdge]:
        """
        Build edges for iteration patterns:
        - for item in collection: item receives taint from collection[*]

        Detection strategy:
        1. Look for NAME_LOAD expressions where:
           - reads_vars contains a collection name
           - defines_var is an iterator variable
        2. This pattern indicates: `for iterator in collection`
        """
        edges: list[InterproceduralDataFlowEdge] = []

        # First, identify which variables are collections (have store edges)
        collection_vars = set(self._collection_elements.keys())
        collection_names = set()
        for var_id in collection_vars:
            # Extract name from var_id: var:{repo}:{file}:{fqn}:{name}@{block}:{shadow}
            # The name is the part before @ in the last segment
            # But the last segment after : might just be block:shadow if format is different
            # Better approach: find the @, then extract name before it
            if "@" in var_id:
                # Split at last @ and take the part before
                before_at = var_id.rsplit("@", 1)[0]
                # The name is the last : segment before @
                name_part = before_at.rsplit(":", 1)[-1] if ":" in before_at else before_at
                collection_names.add(name_part)
            else:
                # No @, just take last part
                parts = var_id.split(":")
                if parts:
                    collection_names.add(parts[-1])

        for expr in expressions:
            # Pattern 1: FOR_LOOP, ITERATION, or COMPREHENSION expression
            # Use enum value comparison for robustness
            kind_value = expr.kind.value if hasattr(expr.kind, "value") else str(expr.kind)
            if kind_value in ("ForLoop", "Iteration", "Comprehension"):
                iterator_var = expr.attrs.get("iterator_var") or expr.attrs.get("target")
                iterable = expr.attrs.get("iterable") or expr.attrs.get("iter")

                if iterator_var and iterable:
                    self._add_iteration_edge(edges, iterable, iterator_var, expr, var_by_scope_name, repo_id)

            # Pattern 2: NAME_LOAD that reads collection and defines iterator
            # This is the pattern for `for q in queries:` where
            # expr.reads_vars=['queries'], expr.defines_var='q'
            elif expr.kind == ExprKind.NAME_LOAD:
                reads = expr.reads_vars
                defines = expr.defines_var

                if defines and reads:
                    # Check if any read var is a collection
                    for read_var in reads:
                        if read_var in collection_names:
                            self._add_iteration_edge(edges, read_var, defines, expr, var_by_scope_name, repo_id)
                            break

        return edges

    def _add_iteration_edge(
        self,
        edges: list[InterproceduralDataFlowEdge],
        collection_name: str,
        iterator_name: str,
        expr: Expression,
        var_by_scope_name: dict[tuple[str, str], str],
        repo_id: str,
    ) -> None:
        """Add a collection_load edge for iteration pattern"""
        # Resolve collection to full var_id
        collection_var_id = self._resolve_var_id(collection_name, expr.function_fqn, var_by_scope_name)

        # Resolve iterator to var_id
        iterator_var_id = self._resolve_var_id(iterator_name, expr.function_fqn, var_by_scope_name)

        if collection_var_id and iterator_var_id:
            # Get or create abstract element
            element_id = self._collection_elements.get(collection_var_id, f"{collection_var_id}[*]")

            edge = InterproceduralDataFlowEdge(
                id=f"collection:{self._edge_count}",
                kind=InterproceduralEdgeKind.COLLECTION_LOAD,
                from_var_id=element_id,
                to_var_id=iterator_var_id,
                call_site_id=expr.id,
                caller_func_fqn=expr.function_fqn,
                callee_func_fqn="__iter__",
                arg_position=None,
                repo_id=repo_id,
                file_path=expr.file_path,
                collection_var_id=collection_var_id,
                element_key="*",
            )
            edges.append(edge)
            self._edge_count += 1
            logger.debug(f"iteration_load: {collection_name}[*] → {iterator_name}")

    def _resolve_var_id(
        self,
        var_name: str,
        function_fqn: str,
        var_by_scope_name: dict[tuple[str, str], str],
    ) -> str | None:
        """
        Resolve variable name to full var_id

        Tries multiple matching strategies:
        1. Exact (function_fqn, name) match
        2. Fuzzy match by function suffix
        3. Global match by name only
        """
        if not var_name:
            return None

        # Normalize function FQN
        normalized_fqn = self._normalize_fqn(function_fqn)

        # Try exact match
        result = var_by_scope_name.get((normalized_fqn, var_name))
        if result:
            return result

        # Try fuzzy match
        for (fqn, name), var_id in var_by_scope_name.items():
            if name == var_name:
                if not fqn:  # Global match
                    return var_id
                if fqn.endswith(normalized_fqn.split(".")[-1]):
                    return var_id
                if normalized_fqn.endswith(fqn.split(".")[-1]):
                    return var_id

        # Return as-is for abstract references
        return var_name

    def _normalize_fqn(self, fqn: str) -> str:
        """Normalize function FQN to match variable's function_fqn format"""
        if not fqn:
            return ""

        # If it's in "function:/repo:/path:module.func" format
        if fqn.startswith("function:"):
            parts = fqn.split(":")
            if len(parts) >= 4:
                return parts[-1]

        # If it's already dotted
        if "." in fqn:
            parts = fqn.split(".")
            if len(parts) >= 2:
                return ".".join(parts[-2:])
            return parts[-1]

        return fqn

    def get_collection_elements(self) -> dict[str, str]:
        """Get mapping of collection var_id → abstract element_id"""
        return self._collection_elements.copy()
