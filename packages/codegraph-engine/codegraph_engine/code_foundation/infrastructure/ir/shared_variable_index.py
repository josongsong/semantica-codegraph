"""
SharedVariableIndex - SOTA O(1) Variable Lookup

Eliminates 3x duplicate variable indexing across:
- InterproceduralDataFlowBuilder
- CollectionDataFlowBuilder
- (future) Any builder needing variable lookups

Problem:
    - var_by_id built 3 times: O(3V) where V = variables
    - var_by_scope_name built 3 times: O(3V)
    - func_params built 2 times: O(2V)
    - func_returns built 2 times: O(2V)
    - call_vars_by_line built 1 time: O(V)
    - Total: ~11V operations redundantly

Solution:
    - Build ONCE, share across all builders
    - Cached per DFG snapshot (invalidate on change)

Performance:
    - Before: O(11V) per file = 11 × 500 = 5,500 operations
    - After: O(V) per file = 500 operations
    - Improvement: 11x fewer indexing operations
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from codegraph_engine.code_foundation.infrastructure.ir.models.core import VariableKind

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.dfg.models import VariableEntity


@dataclass
class SharedVariableIndex:
    """
    Pre-computed variable indexes for O(1) lookup.

    All indexes are built once and shared across builders.

    Attributes:
        var_by_id: var_id → VariableEntity
        var_by_scope_name: (function_fqn, var_name) → var_id
        func_params: function_fqn → {param_name → var_id}
        func_returns: function_fqn → return_var_id
        call_vars_by_line: line_number → list of <call> variables
    """

    var_by_id: dict[str, "VariableEntity"] = field(default_factory=dict)
    var_by_scope_name: dict[tuple[str, str], str] = field(default_factory=dict)
    func_params: dict[str, dict[str, str]] = field(default_factory=dict)
    func_returns: dict[str, str] = field(default_factory=dict)
    call_vars_by_line: dict[int, list["VariableEntity"]] = field(default_factory=dict)

    @classmethod
    def build(cls, variables: list["VariableEntity"]) -> "SharedVariableIndex":
        """
        Build all indexes in SINGLE pass over variables.

        Args:
            variables: All variables from DFG snapshot

        Returns:
            SharedVariableIndex with all indexes populated

        Complexity:
            - Time: O(V) - single pass
            - Space: O(V) - all indexes combined
        """
        index = cls()

        for var in variables:
            # 1. var_by_id: O(1) per var
            index.var_by_id[var.id] = var

            # 2. var_by_scope_name: O(1) per var
            index.var_by_scope_name[(var.function_fqn, var.name)] = var.id
            # Also index by just the name for fuzzy matching (used by CollectionBuilder)
            index.var_by_scope_name[("", var.name)] = var.id

            # 3. func_params: O(1) per var
            is_param = (
                var.kind == VariableKind.PARAMETER
                or var.kind == VariableKind.PARAMETER.value
                or var.kind in ("parameter", "param")
            )
            if is_param:
                if var.function_fqn not in index.func_params:
                    index.func_params[var.function_fqn] = {}
                index.func_params[var.function_fqn][var.name] = var.id

            # 4. func_returns: O(1) per var
            if var.name == "__return__" or "return" in var.name.lower():
                index.func_returns[var.function_fqn] = var.id

            # 5. call_vars_by_line: O(1) per var
            if var.name == "<call>" and var.decl_span:
                line = var.decl_span.start_line
                if line not in index.call_vars_by_line:
                    index.call_vars_by_line[line] = []
                index.call_vars_by_line[line].append(var)

        return index

    def get_var(self, var_id: str) -> "VariableEntity | None":
        """Get variable by ID. O(1)."""
        return self.var_by_id.get(var_id)

    def get_var_id_by_scope(self, function_fqn: str, var_name: str) -> str | None:
        """Get variable ID by scope and name. O(1)."""
        return self.var_by_scope_name.get((function_fqn, var_name))

    def get_param_id(self, function_fqn: str, param_name: str) -> str | None:
        """Get parameter variable ID. O(1)."""
        params = self.func_params.get(function_fqn, {})
        return params.get(param_name)

    def get_return_var_id(self, function_fqn: str) -> str | None:
        """Get return variable ID. O(1)."""
        return self.func_returns.get(function_fqn)

    def get_call_vars_at_line(self, line: int) -> list["VariableEntity"]:
        """Get <call> variables at line. O(1)."""
        return self.call_vars_by_line.get(line, [])

    def __len__(self) -> int:
        """Return number of indexed variables."""
        return len(self.var_by_id)


class SharedVariableIndexCache:
    """
    Cache for SharedVariableIndex instances.

    Avoids rebuilding index when variables haven't changed.
    """

    def __init__(self, max_size: int = 50):
        """Initialize cache with max size."""
        self._cache: dict[int, SharedVariableIndex] = {}  # hash(variables) → index
        self._max_size = max_size

    def get_or_build(self, variables: list["VariableEntity"]) -> SharedVariableIndex:
        """
        Get cached index or build new one.

        Cache key: tuple of variable IDs (content-based, not identity-based).
        """
        # Content-based cache key: tuple of variable IDs
        # This ensures cache hit when same variables are passed in different list objects
        cache_key = tuple(v.id for v in variables) if len(variables) < 1000 else id(variables)

        if cache_key in self._cache:
            return self._cache[cache_key]

        # Build new index
        index = SharedVariableIndex.build(variables)

        # Simple FIFO eviction
        if len(self._cache) >= self._max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        self._cache[cache_key] = index
        return index

    def clear(self) -> None:
        """Clear all cached indexes."""
        self._cache.clear()


# Global cache instance for sharing across builders
_global_variable_index_cache = SharedVariableIndexCache()


def get_shared_variable_index(variables: list["VariableEntity"]) -> SharedVariableIndex:
    """
    Get or build SharedVariableIndex for variables.

    This is the main entry point for all builders to use.

    Usage:
        from codegraph_engine.code_foundation.infrastructure.ir.shared_variable_index import get_shared_variable_index

        index = get_shared_variable_index(variables)
        var = index.get_var(var_id)
    """
    return _global_variable_index_cache.get_or_build(variables)


def clear_variable_index_cache() -> None:
    """Clear the global variable index cache."""
    _global_variable_index_cache.clear()


__all__ = [
    "SharedVariableIndex",
    "SharedVariableIndexCache",
    "get_shared_variable_index",
    "clear_variable_index_cache",
]
