"""
Variable Resolver

Handles variable resolution with shadow count support.
"""

from dataclasses import dataclass, field
from typing import Literal, cast

from .models import VariableEntity


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
    """

    repo_id: str
    file_path: str
    function_fqn: str
    language: str
    variable_index: dict[str, VariableEntity] = field(default_factory=dict)
    type_index: dict[str, str] = field(default_factory=dict)


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

    # Create new variable with shadow count
    shadow_cnt = state.shadow_counter.get(name, 0) + 1
    state.shadow_counter[name] = shadow_cnt

    # Generate variable ID
    var_id = f"var:{ctx.repo_id}:{ctx.file_path}:{ctx.function_fqn}:{name}@{block_idx}:{shadow_cnt}"

    # Track in state
    state.by_name.setdefault(name, []).append(var_id)
    state.current_by_block[key] = var_id

    # Create VariableEntity
    type_id = ctx.type_index.get(name)
    decl_block_id = f"block:{block_idx}"  # Simplified block ID

    var_entity = VariableEntity(
        id=var_id,
        repo_id=ctx.repo_id,
        file_path=ctx.file_path,
        function_fqn=ctx.function_fqn,
        name=name,
        kind=cast(Literal["param", "local", "captured"], kind),
        type_id=type_id,
        decl_block_id=decl_block_id,
    )

    # Store in context
    ctx.variable_index[var_id] = var_entity

    return var_id
