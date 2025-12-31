"""
SemanticIndex - Semantic Search (SRP, Thread-Safe, Optimized)

Single Responsibility: 의미적 검색 및 매칭
- O(1) lookup by name
- Pattern matching support (with LRU cache)
- Type-aware search
- Thread-safe concurrent reads

SOLID:
- S: 의미적 검색만 담당
- O: Extensible for new search types
- L: Substitutable with Port
- I: Focused interface
- D: Depends on abstractions

Thread Safety:
- RLock protects all public methods
- Immutable after __init__

Performance Optimization:
- Pattern matching: LRU cache (10x-100x speedup)
- Composite indexes: O(1) direct lookup
- Lock granularity: Read-only operations
"""

import threading
from collections import OrderedDict, defaultdict
from typing import TYPE_CHECKING

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.query.results import UnifiedNode
from codegraph_engine.code_foundation.infrastructure.query.indexes.pattern_cache import get_global_pattern_cache

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument, Node

    from .node_index import NodeIndex

logger = get_logger(__name__)


class SemanticIndex:
    """
    Semantic search layer

    Responsibilities:
    1. Name-based node lookup
    2. Pattern matching
    3. Category-based search

    Performance:
    - Build: O(N) where N = total nodes
    - Lookup: O(1) for exact name
    - Pattern: O(M) where M = candidates
    - Memory: ~N * avg_name_length
    """

    def __init__(self, ir_doc: "IRDocument", node_index: "NodeIndex"):
        """
        Initialize semantic index (thread-safe, optimized)

        Args:
            ir_doc: IR document
            node_index: Node index (for node lookup)

        Performance:
            - Build: O(N) where N = total entities
            - Memory: O(N) + O(2N) for composite indexes
            - Pattern cache: Shared global LRU cache
        """
        self._node_index = node_index

        # Thread safety
        self._lock = threading.RLock()

        # Pattern cache (shared global instance for memory efficiency)
        self._pattern_cache = get_global_pattern_cache()

        # Name-based indexes (O(1) single-key lookup)
        self._vars_by_name: dict[str, list[str]] = defaultdict(list)
        self._funcs_by_name: dict[str, list[str]] = defaultdict(list)
        self._classes_by_name: dict[str, list[str]] = defaultdict(list)
        self._call_sites_by_name: dict[str, list[str]] = defaultdict(list)

        # Structural indexes
        self._blocks_by_func: dict[str, list[str]] = defaultdict(list)

        # ========================================
        # Composite indexes (O(1) multi-key lookup with LRU eviction)
        # Memory trade-off: Bounded to _composite_max_size per index
        #
        # Memory Estimation (with max_size=10000):
        # - 10,000 entries × 3 indexes → ~2.4MB (bounded)
        # - LRU eviction prevents unbounded growth
        # ========================================
        self._composite_max_size = 10000  # Max entries per composite index
        self._vars_by_name_and_type: OrderedDict[tuple[str, str], list[str]] = OrderedDict()
        self._vars_by_name_and_scope: OrderedDict[tuple[str, str], list[str]] = OrderedDict()
        self._funcs_by_class_and_name: OrderedDict[tuple[str, str], list[str]] = OrderedDict()

        self._build(ir_doc)

        logger.info(
            "semantic_index_built",
            vars=len(self._vars_by_name),
            funcs=len(self._funcs_by_name),
            classes=len(self._classes_by_name),
        )

    def _build(self, ir_doc: "IRDocument") -> None:
        """
        Build semantic index from IR (with LRU-bounded composite indexes)

        Performance:
            - Single-key indexes: O(N)
            - Composite indexes: O(N) with LRU eviction
            - Total build time: O(N)

        Memory:
            - Bounded to _composite_max_size per index
        """
        from codegraph_engine.code_foundation.infrastructure.ir.models import NodeKind as IRNodeKind
        from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import ExprKind

        # 1. Index IR nodes (functions, classes)
        for node in ir_doc.nodes:
            if node.kind == IRNodeKind.FUNCTION or node.kind == IRNodeKind.METHOD:
                if node.name:
                    self._funcs_by_name[node.name].append(node.id)

                    # Composite: (class, func_name) with LRU
                    class_name = self._extract_class_name(node, ir_doc)

                    if class_name:
                        method_name = node.name.split(".")[-1] if "." in node.name else node.name
                        composite_key = (class_name, method_name)
                        self._add_to_composite_lru(self._funcs_by_class_and_name, composite_key, node.id)

            elif node.kind == IRNodeKind.CLASS:
                if node.name:
                    self._classes_by_name[node.name].append(node.id)

        # 2. Index variables (with composite keys and defensive access)
        if ir_doc.dfg_snapshot:
            for var in ir_doc.dfg_snapshot.variables:
                if var.name:
                    self._vars_by_name[var.name].append(var.id)

                    # Composite: (name, type_id) - defensive access
                    type_id = self._get_var_type_id(var)
                    if type_id:
                        composite_key = (var.name, type_id)
                        self._add_to_composite_lru(self._vars_by_name_and_type, composite_key, var.id)

                    # Composite: (name, scope_id) - defensive access
                    scope_id = self._get_var_scope_id(var)
                    if scope_id:
                        composite_key = (var.name, scope_id)
                        self._add_to_composite_lru(self._vars_by_name_and_scope, composite_key, var.id)

        # 3. Index blocks by function
        for block in ir_doc.cfg_blocks:
            self._blocks_by_func[block.function_node_id].append(block.id)

        # 4. Index call sites by callee name
        for expr in ir_doc.expressions:
            if expr.kind == ExprKind.CALL:
                callee_name = expr.attrs.get("callee_name")
                if callee_name:
                    self._call_sites_by_name[callee_name].append(expr.id)

    def _add_to_composite_lru(
        self, cache: "OrderedDict[tuple[str, str], list[str]]", key: tuple[str, str], value: str
    ) -> None:
        """
        Add entry to composite index with LRU eviction

        Args:
            cache: Composite index (OrderedDict)
            key: Composite key (name, type/scope/class)
            value: Node ID to append

        LRU Strategy:
            - If cache full (>= max_size), evict oldest key
            - Move accessed keys to end (mark as recently used)
            - O(1) eviction and append
        """
        # LRU eviction
        if key not in cache and len(cache) >= self._composite_max_size:
            # Evict oldest (first item)
            cache.popitem(last=False)

        # Add or append
        if key not in cache:
            cache[key] = []
        cache[key].append(value)

        # Move to end (mark as recently used)
        cache.move_to_end(key)

    def _get_var_type_id(self, var) -> str | None:
        """
        Get variable type_id (defensive field access)

        Supports both:
        1. Direct field: var.type_id
        2. Attrs dict: var.attrs['type_id']

        Args:
            var: VariableEntity

        Returns:
            Type ID or None
        """
        # Method 1: Direct field (preferred)
        if hasattr(var, "type_id"):
            type_id = getattr(var, "type_id", None)
            if type_id:
                return type_id

        # Method 2: Attrs dict (fallback)
        if hasattr(var, "attrs") and isinstance(var.attrs, dict):
            return var.attrs.get("type_id")

        return None

    def _get_var_scope_id(self, var) -> str | None:
        """
        Get variable scope_id (defensive field access)

        Args:
            var: VariableEntity

        Returns:
            Scope ID or None
        """
        # Method 1: Direct field
        if hasattr(var, "scope_id"):
            scope_id = getattr(var, "scope_id", None)
            if scope_id:
                return scope_id

        # Method 2: Attrs dict
        if hasattr(var, "attrs") and isinstance(var.attrs, dict):
            return var.attrs.get("scope_id")

        return None

    def _extract_class_name(self, node: "Node", ir_doc: "IRDocument") -> str | None:
        """
        Extract class name from IR node (for composite indexing)

        FIXED: Uses ir_doc for parent lookup instead of NodeIndex

        Strategy:
        1. Check parent_id in IR nodes (most reliable)
        2. Parse fqn for class name
        3. Check attrs (fallback)

        Args:
            node: IR Node (METHOD or FUNCTION)
            ir_doc: IR document (for parent lookup)

        Returns:
            Class name or None

        Examples:
            - parent_id → CLASS node → "Calculator"
            - fqn="test.Calculator.add" → "Calculator"
            - fqn="test.module.function" → None (no class)

        Edge Cases:
            - Nested classes: "Outer.Inner.method" → "Inner"
            - Module function: "module.function" → None
            - Lambda: Skip
        """
        from codegraph_engine.code_foundation.infrastructure.ir.models import NodeKind as IRNodeKind

        # Method 1: Check parent_id in IR nodes (FIXED)
        if node.parent_id:
            # Find parent in IR nodes (not NodeIndex!)
            parent = next((n for n in ir_doc.nodes if n.id == node.parent_id), None)
            if parent and parent.kind == IRNodeKind.CLASS:
                return parent.name

        # Method 2: Parse fqn
        if node.fqn:
            parts = node.fqn.split(".")
            if len(parts) >= 2:
                # Take second-to-last as potential class name
                potential_class = parts[-2]

                # Validate: class names typically start with uppercase
                if potential_class and potential_class[0].isupper():
                    return potential_class

        # Method 3: Check attrs (fallback)
        if hasattr(node, "attrs") and isinstance(node.attrs, dict):
            class_name = node.attrs.get("class_name")
            if class_name:
                return class_name

        # No class found (module-level function)
        return None

    # ============================================================
    # Lookup Methods
    # ============================================================

    def find_vars_by_name(self, name: str) -> list[UnifiedNode]:
        """
        Find variables by name (O(1), thread-safe, fine-grained lock)

        Args:
            name: Variable name

        Returns:
            List of matching variable nodes (never None)

        Performance:
            - O(1) for name lookup (with lock)
            - O(k) for node retrieval (without lock)

        Thread Safety:
            Fine-grained locking: Lock only for index access, not node retrieval.
            NodeIndex has its own thread safety.
        """
        # Step 1: Lock only for index lookup
        with self._lock:
            var_ids = list(self._vars_by_name.get(name, []))

        # Step 2: Retrieve nodes without lock (NodeIndex is thread-safe)
        result: list[UnifiedNode] = []
        for vid in var_ids:
            node = self._node_index.get(vid)
            if node is not None:
                result.append(node)
        return result

    def find_funcs_by_name(self, name: str) -> list[UnifiedNode]:
        """
        Find functions by name (O(1), thread-safe, fine-grained lock)

        Args:
            name: Function name

        Returns:
            List of matching function nodes (never None)
        """
        with self._lock:
            func_ids = list(self._funcs_by_name.get(name, []))

        result: list[UnifiedNode] = []
        for fid in func_ids:
            node = self._node_index.get(fid)
            if node is not None:
                result.append(node)
        return result

    def find_classes_by_name(self, name: str) -> list[UnifiedNode]:
        """
        Find classes by name (O(1), thread-safe, fine-grained lock)

        Args:
            name: Class name

        Returns:
            List of matching class nodes
        """
        with self._lock:
            class_ids = list(self._classes_by_name.get(name, []))

        result: list[UnifiedNode] = []
        for cid in class_ids:
            if self._node_index.exists(cid):
                node = self._node_index.get(cid)
                if node:
                    result.append(node)
        return result

    def find_call_sites_by_name(self, callee_name: str) -> list[UnifiedNode]:
        """
        Find call sites by callee name (O(1), thread-safe, fine-grained lock)

        Args:
            callee_name: Callee function name (supports suffix matching for dotted names)

        Returns:
            List of call expression nodes (never None)

        Example:
            find_call_sites_by_name("execute")
            # Returns: conn.execute, cursor.execute, db.execute, etc.

            find_call_sites_by_name("conn.execute")
            # Returns: conn.execute only (exact match)
        """
        with self._lock:
            # 1. Exact match first (O(1))
            expr_ids = list(self._call_sites_by_name.get(callee_name, []))

            # 2. Suffix match for dotted names (e.g., "execute" matches "conn.execute")
            # Only if exact match found nothing and callee_name doesn't contain dot
            if not expr_ids and "." not in callee_name:
                suffix_pattern = f".{callee_name}"
                for full_name, ids in self._call_sites_by_name.items():
                    if full_name.endswith(suffix_pattern) or full_name == callee_name:
                        expr_ids.extend(ids)

        result: list[UnifiedNode] = []
        for eid in expr_ids:
            node = self._node_index.get(eid)
            if node is not None:
                result.append(node)
        return result

    def find_blocks_by_function(self, func_id: str) -> list[UnifiedNode]:
        """
        Find CFG blocks by function ID (O(1), thread-safe, fine-grained lock)

        Args:
            func_id: Function node ID

        Returns:
            List of block nodes (never None)
        """
        with self._lock:
            block_ids = list(self._blocks_by_func.get(func_id, []))

        result: list[UnifiedNode] = []
        for bid in block_ids:
            node = self._node_index.get(bid)
            if node is not None:
                result.append(node)
        return result

    # ============================================================
    # Pattern Matching (Advanced)
    # ============================================================

    def find_vars_by_pattern(self, pattern: str) -> list[UnifiedNode]:
        """
        Find variables by glob pattern (O(M) with full-result LRU cache, thread-safe)

        Args:
            pattern: Glob pattern (e.g., "user_*", "*_input")

        Returns:
            List of matching variable nodes

        Performance:
            - Cache hit: O(1) - returns cached node IDs → 10x-100x faster
            - Cache miss: O(M) - compute once, cache for future

        Caching Strategy:
            - Caches full result (node IDs), not just matching names
            - Safe because SemanticIndex is immutable after __init__

        Thread Safety:
            Protected by RLock, safe for concurrent calls
        """
        import fnmatch

        with self._lock:
            # Use full-result caching (caches node IDs, not just names)
            matching_ids = self._pattern_cache.match_pattern_with_ids(
                pattern, self._vars_by_name, lambda name: fnmatch.fnmatch(name, pattern)
            )

            # Convert node IDs to UnifiedNodes
            matching_nodes = []
            for vid in matching_ids:
                node = self._node_index.get(vid)
                if node:
                    matching_nodes.append(node)

            return matching_nodes

    def find_funcs_by_pattern(self, pattern: str) -> list[UnifiedNode]:
        """
        Find functions by glob pattern (O(M) with full-result LRU cache, thread-safe)

        Args:
            pattern: Glob pattern (e.g., "get_*", "*_handler")

        Returns:
            List of matching function nodes

        Performance:
            - Cache hit: O(1) - returns cached node IDs → 10x-100x faster
            - Cache miss: O(M) - compute once, cache for future

        Caching Strategy:
            - Caches full result (node IDs), not just matching names
            - Safe because SemanticIndex is immutable after __init__

        Thread Safety:
            Protected by RLock, safe for concurrent calls
        """
        import fnmatch

        with self._lock:
            # Use full-result caching (caches node IDs, not just names)
            matching_ids = self._pattern_cache.match_pattern_with_ids(
                pattern, self._funcs_by_name, lambda name: fnmatch.fnmatch(name, pattern)
            )

            # Convert node IDs to UnifiedNodes
            matching_nodes = []
            for fid in matching_ids:
                node = self._node_index.get(fid)
                if node:
                    matching_nodes.append(node)

            return matching_nodes

    # ============================================================
    # Composite Index (Performance Optimization)
    # ============================================================

    def find_vars_by_name_and_type(self, name: str, type_id: str) -> list[UnifiedNode]:
        """
        Find variables by name AND type (TRUE O(1) composite index, thread-safe)

        Before (O(k) filtering):
            vars = find_vars_by_name(name)  # O(1)
            return [v for v in vars if v.attrs.get("type_id") == type_id]  # O(k)

        After (O(1) direct lookup):
            var_ids = composite_index[(name, type_id)]  # O(1)
            return [node_index.get(vid) for vid in var_ids]  # O(k) node retrieval

        Args:
            name: Variable name
            type_id: Type ID

        Returns:
            List of matching variables (never None)

        Performance:
            - Lookup: O(1) from composite index
            - Retrieval: O(k) where k = number of matches
            - Total: O(1) + O(k) ≈ O(1) for typical k << N

        Thread Safety:
            Protected by RLock, safe for concurrent calls
        """
        with self._lock:
            composite_key = (name, type_id)
            var_ids = self._vars_by_name_and_type.get(composite_key, [])

            result: list[UnifiedNode] = []
            for vid in var_ids:
                node = self._node_index.get(vid)
                if node is not None:
                    result.append(node)
            return result

    def find_vars_by_name_and_scope(self, name: str, scope_id: str) -> list[UnifiedNode]:
        """
        Find variables by name AND scope (TRUE O(1) composite index, thread-safe)

        Args:
            name: Variable name
            scope_id: Scope ID (function FQN)

        Returns:
            List of matching variables (never None)

        Performance:
            - O(1) composite index lookup
        """
        with self._lock:
            composite_key = (name, scope_id)
            var_ids = self._vars_by_name_and_scope.get(composite_key, [])

            result: list[UnifiedNode] = []
            for vid in var_ids:
                node = self._node_index.get(vid)
                if node is not None:
                    result.append(node)
            return result

    def find_funcs_in_class(self, func_name: str, class_name: str) -> list[UnifiedNode]:
        """
        Find functions in specific class (TRUE O(1) composite index, thread-safe)

        Before (O(k) filtering):
            all_funcs = find_funcs_by_name(func_name)  # O(1)
            return [f for f in all_funcs if class_name in f.attrs.get("fqn", "")]  # O(k)

        After (O(1) direct lookup):
            func_ids = composite_index[(class_name, func_name)]  # O(1)
            return [node_index.get(fid) for fid in func_ids]  # O(k) retrieval

        Args:
            func_name: Function/method name
            class_name: Class name

        Returns:
            List of matching methods (never None)

        Performance:
            - O(1) composite index lookup

        Thread Safety:
            Protected by RLock, safe for concurrent calls
        """
        with self._lock:
            composite_key = (class_name, func_name)
            func_ids = self._funcs_by_class_and_name.get(composite_key, [])

            result: list[UnifiedNode] = []
            for fid in func_ids:
                node = self._node_index.get(fid)
                if node is not None:
                    result.append(node)
            return result

    # ============================================================
    # Statistics
    # ============================================================

    def get_stats(self) -> dict:
        """
        Get semantic index statistics (thread-safe)

        Returns:
            Statistics including memory usage of composite indexes

        Thread Safety:
            Protected by RLock, safe for concurrent calls
        """
        with self._lock:
            return self._get_stats_unsafe()

    def _get_stats_unsafe(self) -> dict:
        """Internal stats getter (no lock, for internal use only)"""
        return {
            # Single-key indexes
            "unique_var_names": len(self._vars_by_name),
            "unique_func_names": len(self._funcs_by_name),
            "unique_class_names": len(self._classes_by_name),
            "unique_call_names": len(self._call_sites_by_name),
            "total_vars": sum(len(ids) for ids in self._vars_by_name.values()),
            "total_funcs": sum(len(ids) for ids in self._funcs_by_name.values()),
            "total_classes": sum(len(ids) for ids in self._classes_by_name.values()),
            "total_call_sites": sum(len(ids) for ids in self._call_sites_by_name.values()),
            # Composite indexes (O(1) multi-key)
            "composite_var_name_type_keys": len(self._vars_by_name_and_type),
            "composite_var_name_type_entries": sum(len(ids) for ids in self._vars_by_name_and_type.values()),
            "composite_var_name_scope_keys": len(self._vars_by_name_and_scope),
            "composite_var_name_scope_entries": sum(len(ids) for ids in self._vars_by_name_and_scope.values()),
            "composite_func_class_name_keys": len(self._funcs_by_class_and_name),
            "composite_func_class_name_entries": sum(len(ids) for ids in self._funcs_by_class_and_name.values()),
        }
