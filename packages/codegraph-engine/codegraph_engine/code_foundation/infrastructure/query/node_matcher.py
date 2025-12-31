"""
NodeMatcher

Matches NodeSelector (domain) to IR entities (infrastructure).

Architecture:
- Infrastructure layer (uses UnifiedGraphIndex)
- Pattern matching for glob patterns
- Type-safe matching with validation

Contract:
- Returns only nodes that exactly match selector criteria
- Empty list if no matches (never None)
- Validates selector type compatibility

RFC-031 Compliance:
- NodeKind: Canonical from ir/models/kinds.py
- SelectorType: Query-specific selector logic
"""

import fnmatch
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.security.taint_config import TaintConfig

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.query.exceptions import InvalidQueryError
from codegraph_engine.code_foundation.domain.query.results import UnifiedNode
from codegraph_engine.code_foundation.domain.query.selectors import NodeSelector
from codegraph_engine.code_foundation.domain.query.types import SelectorType
from codegraph_engine.code_foundation.infrastructure.ir.models.kinds import NodeKind  # RFC-031: Canonical

if TYPE_CHECKING:
    from .graph_index import UnifiedGraphIndex

logger = get_logger(__name__)


class NodeMatcher:
    """
    Matches NodeSelector to UnifiedNode

    Selector Types:
    - var: Match VariableEntity
    - func: Match Function/Method nodes
    - call: Match Call sites (NOT IMPLEMENTED - requires Expression IR)
    - block: Match ControlFlowBlock
    - module: Match Module/File nodes
    - class: Match Class nodes
    - source/sink: Security presets (NOT IMPLEMENTED - requires taint config)
    - any: Match all nodes
    - union: Match any of operands
    - intersection: Match all of operands
    """

    def __init__(self, graph: "UnifiedGraphIndex", taint_config: "TaintConfig | None" = None):
        """
        Initialize with graph index

        Args:
            graph: Unified graph index
            taint_config: Taint configuration (optional, uses default if None)
                         NEW: 2025-12 for externalized Source/Sink config
        """
        self.graph = graph

        # Taint configuration (DI-friendly)
        if taint_config is None:
            from codegraph_engine.code_foundation.domain.security import TaintConfig

            self.taint_config = TaintConfig.default()
        else:
            self.taint_config = taint_config

    def match(self, selector: NodeSelector) -> list[UnifiedNode]:
        """
        Match selector to nodes

        Args:
            selector: Node selector (domain)

        Returns:
            List of matching nodes (empty if no matches)

        Raises:
            InvalidQueryError: If selector type is invalid or not supported
        """
        selector_type = selector.selector_type

        # Dispatch to type-specific matcher
        if selector_type == SelectorType.VAR:
            return self._match_var(selector)
        elif selector_type == SelectorType.FUNC:
            return self._match_func(selector)
        elif selector_type == SelectorType.CALL:
            return self._match_call(selector)
        elif selector_type == SelectorType.BLOCK:
            return self._match_block(selector)
        elif selector_type == SelectorType.MODULE:
            return self._match_module(selector)
        elif selector_type == SelectorType.CLASS:
            return self._match_class(selector)
        elif selector_type == SelectorType.EXPR:
            return self._match_expr(selector)
        elif selector_type == SelectorType.ALIAS:
            return self._match_alias(selector)
        elif selector_type == SelectorType.SOURCE:
            return self._match_source(selector)
        elif selector_type == SelectorType.SINK:
            return self._match_sink(selector)
        elif selector_type == SelectorType.FIELD:
            return self._match_field(selector)
        elif selector_type == SelectorType.ANY:
            return self._match_any(selector)
        elif selector_type == SelectorType.UNION:
            return self._match_union(selector)
        elif selector_type == SelectorType.INTERSECTION:
            return self._match_intersection(selector)
        else:
            raise InvalidQueryError(
                f"Unknown selector type: {selector_type}",
                "Use Q.Var(), Q.Func(), Q.Call(), Q.Block(), Q.Module(), Q.Class(), Q.Field(), Q.Expr(), or Q.Any()",
            )

    def _match_var(self, selector: NodeSelector) -> list[UnifiedNode]:
        """
        Match variable selector

        Attributes:
        - name: Variable name (supports field access: "user.password")
        - type: Variable type
        - scope: Variable scope (function FQN)
        - context: Call context (k=1 context-sensitive) ✅ FIXED

        RFC-031: Uses canonical NodeKind.VARIABLE
        """
        if selector.name:
            # Exact name match (O(1) via index)
            nodes = self.graph.find_vars_by_name(selector.name)
        else:
            # All variables (expensive!) - RFC-031: VARIABLE
            nodes = [n for n in self.graph.get_all_nodes() if self._is_kind(n, NodeKind.VARIABLE)]

        # Filter by type
        if selector.attrs.get("type"):
            target_type = selector.attrs["type"]
            nodes = [n for n in nodes if n.attrs.get("type_id") == target_type]

        # Filter by scope
        if selector.attrs.get("scope"):
            target_scope = selector.attrs["scope"]
            nodes = [n for n in nodes if n.attrs.get("scope_id") == target_scope]

        # ✅ HOTFIX: Filter by context (k=1 context-sensitive)
        if selector.context:
            nodes = [n for n in nodes if n.attrs.get("context") == selector.context]

        return nodes

    def _match_func(self, selector: NodeSelector) -> list[UnifiedNode]:
        """
        Match function selector

        Attributes:
        - name: Function name (can include class: "Calculator.add")

        RFC-031: Uses canonical NodeKind.FUNCTION, NodeKind.METHOD
        """
        if selector.name:
            # Exact name match
            nodes = self.graph.find_funcs_by_name(selector.name)
        else:
            # All functions - RFC-031: FUNCTION, METHOD (already canonical)
            nodes = [
                n
                for n in self.graph.get_all_nodes()
                if self._is_kind(n, NodeKind.FUNCTION) or self._is_kind(n, NodeKind.METHOD)
            ]

        return nodes

    def _match_call(self, selector: NodeSelector) -> list[UnifiedNode]:
        """
        Match call site selector

        Attributes:
        - name: Callee function name

        RFC-031: Uses canonical NodeKind.EXPRESSION
        """
        if selector.name:
            # Find call sites by callee name
            nodes = self.graph.find_call_sites_by_name(selector.name)
        else:
            # All call expressions - RFC-031: EXPRESSION
            nodes = [
                n
                for n in self.graph.get_all_nodes()
                if self._is_kind(n, NodeKind.EXPRESSION) and n.attrs.get("expr_kind") == "CALL"
            ]

        return nodes

    def _match_block(self, selector: NodeSelector) -> list[UnifiedNode]:
        """
        Match control flow block selector

        Attributes:
        - name: Block label (e.g., "entry", "exit")
        """
        nodes = [n for n in self.graph.get_all_nodes() if self._is_kind(n, NodeKind.BLOCK)]

        if selector.name:
            # Filter by block kind
            nodes = [n for n in nodes if n.attrs.get("block_kind") == selector.name]

        return nodes

    def _match_module(self, selector: NodeSelector) -> list[UnifiedNode]:
        """
        Match module/file selector

        Attributes:
        - pattern: Glob pattern for module path (e.g., "core.*")
        """
        nodes = [
            n
            for n in self.graph.get_all_nodes()
            if self._is_kind(n, NodeKind.FILE) or self._is_kind(n, NodeKind.MODULE)
        ]

        if selector.pattern:
            # Glob pattern matching
            pattern = selector.pattern
            nodes = [n for n in nodes if n.name and fnmatch.fnmatch(n.name, pattern)]

        return nodes

    def _match_class(self, selector: NodeSelector) -> list[UnifiedNode]:
        """
        Match class selector

        Attributes:
        - name: Class name
        """
        if selector.name:
            nodes = self.graph.find_classes_by_name(selector.name)
        else:
            nodes = [n for n in self.graph.get_all_nodes() if self._is_kind(n, NodeKind.CLASS)]

        return nodes

    def _match_expr(self, selector: NodeSelector) -> list[UnifiedNode]:
        """
        Match expression selector (NEW: 2025-12)

        Supports:
        1. Direct ID match (e.g., "expr::test.py:10:5:1") 🔥 PRIORITY
        2. By expr_kind (e.g., ExprKind.CALL)
        3. All expressions (wildcard)

        Attributes:
        - name: Expression ID (direct match) 🔥 NEW
        - expr_kind: Expression kind filter

        Examples:
            Q.Expr(id="expr::test.py:10:5:1")  # Direct ID 🔥
            Q.Expr(kind=ExprKind.BINARY_OP)    # All binary operations
            Q.Expr()                           # All expressions

        RFC-031: Uses canonical NodeKind.EXPRESSION
        """
        # 🔥 Priority 1: Direct ID match
        if selector.name:
            # Direct Expression ID lookup
            node = self.graph.get_node(selector.name)
            if node and node.kind == NodeKind.EXPRESSION:
                return [node]
            return []

        # Priority 2: Filter by expr_kind - RFC-031: EXPRESSION
        nodes = [n for n in self.graph.get_all_nodes() if self._is_kind(n, NodeKind.EXPRESSION)]

        if expr_kind := selector.attrs.get("expr_kind"):
            nodes = [n for n in nodes if n.attrs.get("expr_kind") == expr_kind]

        return nodes

    def _match_alias(self, selector: NodeSelector) -> list[UnifiedNode]:
        """
        Match alias selector (NEW: 2025-12)

        Finds all aliases of a variable using Points-to Analysis.

        Attributes:
        - name: Variable name

        Examples:
            Q.AliasOf("x")  # All aliases of x
        """
        var_name = selector.name
        if not var_name:
            return []

        # Find original variable
        original_nodes = self.graph.find_vars_by_name(var_name)
        if not original_nodes:
            return []

        # Try to get Points-to Analysis results
        try:
            # Check if IR has points_to_graph
            ir_doc = self.graph.ir_doc
            if not hasattr(ir_doc, "points_to_graph") or ir_doc.points_to_graph is None:
                # No Points-to info → return original only
                logger.debug("points_to_not_available", var=var_name)
                return original_nodes

            pts_graph = ir_doc.points_to_graph

            # Get all aliases
            all_nodes = list(original_nodes)
            for orig_node in original_nodes:
                # Get alias variable IDs from Points-to
                alias_ids = pts_graph.get_aliases(orig_node.id)

                # Find nodes for aliases
                for alias_id in alias_ids:
                    alias_node = self.graph.get_node(alias_id)
                    if alias_node and alias_node not in all_nodes:
                        all_nodes.append(alias_node)

            logger.debug("alias_expansion", original=len(original_nodes), total=len(all_nodes))
            return all_nodes

        except Exception as e:
            # Fallback: return original
            logger.warning("alias_analysis_failed", error=str(e))
            return original_nodes

    def _match_source(self, selector: NodeSelector) -> list[UnifiedNode]:
        """
        Match taint source (hybrid: YAML atom ID, Expression ID, or category)

        Supports three modes:
        1. Expression ID (e.g., "expr:..." or "expr::...") - PolicyCompiler with detected atoms 🔥 NEW
        2. YAML atom ID (e.g., "input.http.flask") - PolicyCompiler
        3. Category (e.g., "request") - Simple queries

        Attributes:
        - name: Expression ID, Atom ID, or category
        """
        source_id = selector.name
        if not source_id:
            return []

        # 🔥 FIXED: Strategy 0: Expression ID (starts with "expr:" or "expr::")
        if source_id.startswith("expr:"):
            # Direct Expression ID match - try get_node first (O(1))
            node = self.graph.get_node(source_id)
            if node:
                return [node]
            # Fallback: scan all nodes (O(N))
            nodes = [n for n in self.graph.get_all_nodes() if n.id == source_id]
            if nodes:
                return nodes
            return []

        # Strategy 1: Try as category (TaintConfig)
        if source_id in self.taint_config.sources:
            source_names = self.taint_config.get_sources(source_id)
            nodes = []
            for name in source_names:
                nodes.extend(self.graph.find_call_sites_by_name(name))
                nodes.extend(self.graph.find_vars_by_name(name))
            return nodes

        # Strategy 2: Atom ID or simple name
        nodes = []
        nodes.extend(self.graph.find_call_sites_by_name(source_id))
        nodes.extend(self.graph.find_vars_by_name(source_id))

        return nodes

        # Strategy 2: Try as atom ID (YAML)
        # Atom IDs: input.http.flask, input.file.read, etc.
        # For atom IDs, we need to match against IR nodes with atom annotations
        # This is handled by TypeAwareAtomMatcher in TaintAnalysisService
        # QueryEngine DSL only does simple name matching

        # Fallback: Treat as simple name pattern
        nodes = []
        nodes.extend(self.graph.find_call_sites_by_name(source_id))
        nodes.extend(self.graph.find_vars_by_name(source_id))

        return nodes

    def _match_sink(self, selector: NodeSelector) -> list[UnifiedNode]:
        """
        Match taint sink (hybrid: Expression ID, YAML atom ID, or category)

        Supports three modes:
        1. Expression ID (e.g., "expr:..." or "expr::...") - PolicyCompiler with detected atoms 🔥 NEW
        2. YAML atom ID (e.g., "sink.sql.sqlite3") - PolicyCompiler
        3. Category (e.g., "execute") - Simple queries

        Attributes:
        - name: Expression ID, Atom ID, or category
        """
        sink_id = selector.name
        if not sink_id:
            return []

        # 🔥 FIXED: Strategy 0: Expression ID (starts with "expr:" or "expr::")
        if sink_id.startswith("expr:"):
            # Direct Expression ID match - try get_node first (O(1))
            node = self.graph.get_node(sink_id)
            if node:
                return [node]
            # Fallback: scan all nodes (O(N))
            nodes = [n for n in self.graph.get_all_nodes() if n.id == sink_id]
            if nodes:
                return nodes
            return []

        # Strategy 1: Try as category (TaintConfig)
        if sink_id in self.taint_config.sinks:
            sink_names = self.taint_config.get_sinks(sink_id)
            nodes = []
            for name in sink_names:
                nodes.extend(self.graph.find_call_sites_by_name(name))
            return nodes

        # Strategy 2: Atom ID or simple name
        nodes = []
        nodes.extend(self.graph.find_call_sites_by_name(sink_id))

        return nodes

        # Strategy 2: Try as atom ID (YAML)
        # Atom IDs: sink.sql.sqlite3, sink.command.os, etc.
        # For atom IDs, we need type-aware matching
        # This is handled by TypeAwareAtomMatcher in TaintAnalysisService
        # QueryEngine DSL only does simple name matching

        # Fallback: Treat as simple name pattern
        nodes = []
        nodes.extend(self.graph.find_call_sites_by_name(sink_id))

        return nodes

    def _match_field(self, selector: NodeSelector) -> list[UnifiedNode]:
        """
        Match field selector (field-sensitive analysis)

        Matches variables with field access patterns.

        Attributes:
        - name: Composite name (obj.field)
        - obj_name: Object name
        - field_name: Field name

        Examples:
            Q.Field("user", "id") → matches "user.id" variables
            Q.Field("list", "[0]") → matches "list[0]" variables

        RFC-031: Uses canonical NodeKind.VARIABLE
        """
        obj_name = selector.attrs.get("obj_name")
        field_name = selector.attrs.get("field_name")

        if not obj_name or not field_name:
            return []

        # Match variables with name pattern: obj.field
        composite_name = f"{obj_name}.{field_name}"
        nodes = self.graph.find_vars_by_name(composite_name)

        # Also match attrs-based field tracking - RFC-031: VARIABLE
        all_vars = [n for n in self.graph.get_all_nodes() if self._is_kind(n, NodeKind.VARIABLE)]
        for var in all_vars:
            # Check if variable has field_path attribute
            var_field = var.attrs.get("field_path")
            if var_field == field_name and var.name == obj_name:
                nodes.append(var)

        return nodes

    def _match_any(self, selector: NodeSelector) -> list[UnifiedNode]:
        """
        Match any node (wildcard)

        Warning: Expensive operation (returns all nodes)
        """
        return self.graph.get_all_nodes()

    def _match_union(self, selector: NodeSelector) -> list[UnifiedNode]:
        """
        Match union (OR) of selectors

        Returns nodes matching ANY of the operands.
        """
        operands = selector.attrs.get("operands", [])
        if not operands:
            return []

        # Collect all matches (with deduplication)
        seen_ids = set()
        result = []

        for operand in operands:
            for node in self.match(operand):
                if node.id not in seen_ids:
                    seen_ids.add(node.id)
                    result.append(node)

        return result

    def _match_intersection(self, selector: NodeSelector) -> list[UnifiedNode]:
        """
        Match intersection (AND) of selectors

        Returns nodes matching ALL of the operands.
        """
        operands = selector.attrs.get("operands", [])
        if not operands:
            return []

        # Start with first operand
        result_set = {n.id for n in self.match(operands[0])}

        # Intersect with remaining operands
        for operand in operands[1:]:
            matched_ids = {n.id for n in self.match(operand)}
            result_set &= matched_ids

        # Convert back to nodes
        return [self.graph.get_node(node_id) for node_id in result_set if self.graph.get_node(node_id)]

    def _is_kind(self, node: UnifiedNode, kind: NodeKind) -> bool:
        """
        Type-safe kind comparison

        RFC-031: Handles both enum and string kinds (backward compatibility).
        Canonical NodeKind uses str(Enum) pattern for comparison.
        """
        # Direct enum comparison (preferred)
        if isinstance(node.kind, NodeKind):
            return node.kind == kind

        # String comparison (backward compatibility)
        node_kind_str = str(node.kind) if hasattr(node.kind, "value") else node.kind
        kind_str = kind.value if isinstance(kind, NodeKind) else str(kind)
        return node_kind_str == kind_str
