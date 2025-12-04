"""
Variable Resolver

Handles variable resolution with shadow count support.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal, cast

from src.contexts.code_foundation.infrastructure.dfg.models import VariableEntity


def extract_scope_info(function_fqn: str) -> tuple[str, str, int]:
    """
    Extract scope information from function FQN.

    Args:
        function_fqn: Fully qualified function name (e.g., "module.Class.method", "module.func.<lambda_1>")

    Returns:
        Tuple of (scope_id, scope_kind, scope_depth)

    Examples:
        - "module" → ("module", "module", 0)
        - "module.function" → ("module.function", "function", 1)
        - "module.Class.method" → ("module.Class.method", "method", 2)
        - "module.function.<lambda_1>" → ("module.function.<lambda_1>", "lambda", 2)
        - "module.function.<comprehension_1>" → ("module.function.<comprehension_1>", "comprehension", 2)
    """
    if not function_fqn:
        return ("", "module", 0)

    # Scope ID is the function FQN itself
    scope_id = function_fqn

    # Determine scope kind based on FQN structure
    parts = function_fqn.split(".")

    # Calculate depth: module=0, first-level function=1, nested=2, etc.
    scope_depth = len(parts) - 1

    # Determine scope kind from last part
    last_part = parts[-1] if parts else ""

    if last_part.startswith("<lambda"):
        scope_kind = "lambda"
    elif last_part.startswith("<comprehension"):
        scope_kind = "comprehension"
    elif len(parts) == 1:
        # Top-level module
        scope_kind = "module"
    elif len(parts) >= 2:
        # Check if this is a method (parent is likely a class)
        # Heuristic: If parent starts with uppercase, it's likely a class
        parent = parts[-2] if len(parts) >= 2 else ""
        if parent and parent[0].isupper():
            scope_kind = "method"
        else:
            scope_kind = "function"
    else:
        scope_kind = "function"

    return (scope_id, scope_kind, scope_depth)


@dataclass
class VarResolverState:
    """
    State for variable resolution within a function.

    Tracks:
    - All variables by name
    - Current variable per block
    - Shadow counters for name disambiguation

    Attributes:
        by_name: Map of variable name → list of variable IDs (all versions)
        current_by_block: Map of (block_idx, name) → variable_id (current version in block)
        shadow_counter: Map of variable name → shadow count
    """

    by_name: dict[str, list[str]] = field(default_factory=dict)
    current_by_block: dict[tuple[int, str], str] = field(default_factory=dict)
    shadow_counter: dict[str, int] = field(default_factory=dict)


@dataclass
class DfgContext:
    """
    Context for DFG building within a function.

    Attributes:
        repo_id: Repository identifier
        file_path: File path
        function_fqn: Fully qualified function name
        language: Programming language
        variable_index: Map of variable_id → VariableEntity
        type_index: Map of variable name → type_id (optional)
        name_to_ids: Map of variable name → list of variable IDs (for O(1) lookup)
        outer_scope_vars: Variables from enclosing scopes (for closure detection)
    """

    repo_id: str
    file_path: str
    function_fqn: str
    language: str
    variable_index: dict[str, VariableEntity] = field(default_factory=dict)
    type_index: dict[str, str] = field(default_factory=dict)
    name_to_ids: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    # Outer scope variables: name → (var_id, scope_fqn) for closure detection
    outer_scope_vars: dict[str, tuple[str, str]] = field(default_factory=dict)

    def register_variable(self, var: VariableEntity) -> None:
        """
        Register a variable in the context with automatic index updates.

        Args:
            var: Variable entity to register
        """
        self.variable_index[var.id] = var
        self.name_to_ids[var.name].append(var.id)

    def find_variable_id_by_name(self, name: str) -> str | None:
        """
        Find variable ID by name (O(1) lookup).

        Returns the first variable with the given name (for simple cases).
        For shadow-aware lookup, use find_all_variable_ids_by_name().

        Args:
            name: Variable name

        Returns:
            Variable ID or None if not found
        """
        var_ids = self.name_to_ids.get(name)
        return var_ids[0] if var_ids else None

    def find_all_variable_ids_by_name(self, name: str) -> list[str]:
        """
        Find all variable IDs with the given name (handles shadowing).

        Args:
            name: Variable name

        Returns:
            List of variable IDs (empty if not found)
        """
        return self.name_to_ids.get(name, [])


def resolve_or_create_variable(
    name: str,
    block_idx: int,
    kind: str,
    state: VarResolverState,
    ctx: DfgContext,
) -> str:
    """
    Resolve or create a variable entity.

    Rules:
    - If (block_idx, name) already exists, reuse that variable_id
    - If variable exists as a parameter (block 0), reuse it for reads
    - If variable exists in outer scope, create as "captured"
    - Otherwise, create new variable with incremented shadow count

    Args:
        name: Variable name
        block_idx: CFG block index
        kind: Variable kind (param, local, captured)
        state: Resolver state
        ctx: DFG context

    Returns:
        Variable ID
    """
    key = (block_idx, name)

    # Check if already exists in this block
    if key in state.current_by_block:
        return state.current_by_block[key]

    # If this is a "local" kind (read operation), check if it's a parameter
    if kind == "local" and name in state.by_name:
        # Look for parameter variable (block 0)
        param_key = (0, name)
        if param_key in state.current_by_block:
            param_var_id = state.current_by_block[param_key]
            # Check if it's actually a parameter
            param_var = ctx.variable_index.get(param_var_id)
            if param_var and param_var.kind == "param":
                # Reuse parameter variable for this block
                state.current_by_block[key] = param_var_id
                return param_var_id

    # Check if variable is from outer scope (closure/captured)
    actual_kind = kind
    outer_var_id = None
    if kind == "local" and name in ctx.outer_scope_vars:
        # This is a captured variable from enclosing scope
        actual_kind = "captured"
        outer_var_id, _ = ctx.outer_scope_vars[name]

    # Create new variable with shadow count
    shadow_cnt = state.shadow_counter.get(name, 0) + 1
    state.shadow_counter[name] = shadow_cnt

    # Generate variable ID
    var_id = f"var:{ctx.repo_id}:{ctx.file_path}:{ctx.function_fqn}:{name}@{block_idx}:{shadow_cnt}"

    # Track in state
    if name not in state.by_name:
        state.by_name[name] = []
    state.by_name[name].append(var_id)
    state.current_by_block[key] = var_id

    # Create VariableEntity
    type_id = ctx.type_index.get(name)
    decl_block_id = f"block:{block_idx}"  # Simplified block ID

    # Extract scope information from function FQN
    scope_id, scope_kind_str, scope_depth = extract_scope_info(ctx.function_fqn)
    scope_kind = cast(Literal["module", "function", "method", "lambda", "comprehension", "class"], scope_kind_str)

    var_entity = VariableEntity(
        id=var_id,
        repo_id=ctx.repo_id,
        file_path=ctx.file_path,
        function_fqn=ctx.function_fqn,
        name=name,
        kind=cast(Literal["param", "local", "captured"], actual_kind),
        type_id=type_id,
        decl_block_id=decl_block_id,
        scope_id=scope_id,
        scope_kind=scope_kind,
        scope_depth=scope_depth,
    )

    # If captured, store reference to outer variable in attrs
    if actual_kind == "captured" and outer_var_id:
        var_entity.attrs["captured_from"] = outer_var_id

    # Store in context with automatic index updates
    ctx.register_variable(var_entity)

    return var_id
