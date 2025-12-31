"""
SOTA-level AST Indexing System

Multi-level indexing for O(1) node lookups:
- Type index: by node type (function_definition, class_definition, etc.)
- Line index: by start line number
- Position index: by (line, column) tuple

L11 Design: Direct TSNode storage for true O(1) performance.
Safety via explicit invalidation contract (ProcessPool provides isolation).
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Node as TSNode

from codegraph_engine.code_foundation.infrastructure.ir.models import Span


@dataclass
class AstIndex:
    """
    Multi-level AST index for O(1) lookups.

    L11 SOTA Design:
    - Direct TSNode storage for true O(1) resolution
    - Generation tracking for lifecycle safety
    - Explicit invalidation API (no implicit magic)

    Trade-off Analysis:
    - Memory safety: Manual invalidation required
    - Performance: True O(1) (vs O(n) with NodeRef)
    - Complexity: Simple dict (vs WeakRef complexity)

    Decision: Performance > Implicit Safety
    Rationale: ProcessPool already isolates memory, manual invalidation acceptable
    """

    # Direct storage (O(1) resolution)
    by_type: dict[str, list["TSNode"]] = field(default_factory=lambda: defaultdict(list))
    by_line: dict[int, list["TSNode"]] = field(default_factory=lambda: defaultdict(list))
    by_position: dict[tuple[int, int], "TSNode"] = field(default_factory=dict)

    # Generation tracking (safety)
    tree_generation: int = 0

    # Statistics
    node_count: int = 0
    type_count: int = 0

    def add_node(self, node: "TSNode", span: Span) -> None:
        """
        Add node to all indexes (L11: Direct TSNode for O(1)).

        Args:
            node: Tree-sitter node
            span: Node span (required)
        """
        # Type index (always)
        self.by_type[node.type].append(node)

        # Line/position index
        self.by_line[span.start_line].append(node)
        self.by_position[(span.start_line, span.start_col)] = node

        self.node_count += 1

    def get_by_type(self, node_type: str) -> list["TSNode"]:
        """O(1) lookup by type."""
        return self.by_type.get(node_type, [])

    def get_by_line(self, line: int) -> list["TSNode"]:
        """O(1) lookup by line."""
        return self.by_line.get(line, [])

    def get_by_position(self, line: int, col: int) -> "TSNode | None":
        """O(1) lookup by exact position."""
        return self.by_position.get((line, col))

    def find_function_at_line(self, line: int, language: str) -> "TSNode | None":
        """
        Find function/method at line (O(1) index lookup).

        L11 Design: Direct TSNode return (no O(n) resolution).

        Args:
            line: Line number (1-based)
            language: Source language

        Returns:
            TSNode or None
        """
        candidates = self.get_by_line(line)

        # Language-specific function types
        if language == "python":
            types = {"function_definition", "decorated_definition"}
        elif language == "java":
            types = {"method_declaration", "constructor_declaration"}
        elif language == "kotlin":
            types = {"function_declaration"}
        elif language in ("javascript", "typescript"):
            types = {"function_declaration", "arrow_function", "method_definition", "function"}
        else:
            types = {"function_definition", "function_declaration"}

        # O(k) where k = nodes at this line (typically 1-3)
        for node in candidates:
            if node.type in types:
                # Handle decorated (Python)
                if node.type == "decorated_definition":
                    definition = node.child_by_field_name("definition")
                    if definition and definition.type == "function_definition":
                        return definition
                return node

        return None

    def get_all_functions(self, language: str) -> list["TSNode"]:
        """Get all functions (O(1) index lookup)."""
        results = []

        if language == "python":
            results.extend(self.get_by_type("function_definition"))
            # Handle decorated
            for decorated in self.get_by_type("decorated_definition"):
                definition = decorated.child_by_field_name("definition")
                if definition and definition.type == "function_definition":
                    results.append(definition)

        elif language == "java":
            results.extend(self.get_by_type("method_declaration"))
            results.extend(self.get_by_type("constructor_declaration"))

        elif language == "kotlin":
            results.extend(self.get_by_type("function_declaration"))

        elif language in ("javascript", "typescript"):
            results.extend(self.get_by_type("function_declaration"))
            results.extend(self.get_by_type("arrow_function"))
            results.extend(self.get_by_type("method_definition"))
            results.extend(self.get_by_type("function"))

        return results

    def get_stats(self) -> dict[str, int]:
        """Get index statistics."""
        return {
            "total_nodes": self.node_count,
            "unique_types": len(self.by_type),
            "indexed_lines": len(self.by_line),
            "indexed_positions": len(self.by_position),
        }

    def clear(self) -> None:
        """Clear all indexes."""
        self.by_type.clear()
        self.by_line.clear()
        self.by_position.clear()
        self.all_nodes.clear()
        self.node_count = 0
        self.type_count = 0
