"""
Import Analyzer for Python IR

Handles import statement processing including 'import' and 'from...import' statements.
"""

try:
    from tree_sitter import Node as TSNode
except ImportError:
    TSNode = None

from src.contexts.code_foundation.infrastructure.generators.python.builders.edge_builder import EdgeBuilder
from src.contexts.code_foundation.infrastructure.generators.scope_stack import ScopeStack
from src.contexts.code_foundation.infrastructure.ir.id_strategy import generate_logical_id
from src.contexts.code_foundation.infrastructure.ir.models import Node, NodeKind
from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile


class ImportAnalyzer:
    """
    Handles import statement processing.

    Responsibilities:
    - Process `import module` statements
    - Process `from module import symbol` statements
    - Create IMPORT nodes
    - Create CONTAINS edges (file -> import)
    - Register imports in scope

    This analyzer focuses purely on import processing,
    delegating edge creation to EdgeBuilder.

    Example:
        >>> nodes = []
        >>> edges = []
        >>> scope = ScopeStack("main")
        >>> edge_builder = EdgeBuilder(edges)
        >>> analyzer = ImportAnalyzer(
        ...     "repo1", nodes, scope, edge_builder, source, source_bytes, ast
        ... )
        >>> # Process: import numpy as np
        >>> analyzer.process_import(import_ast_node)
        >>> assert len(nodes) == 1  # IMPORT node created
    """

    def __init__(
        self,
        repo_id: str,
        nodes: list[Node],
        scope: ScopeStack,
        edge_builder: EdgeBuilder,
        source: SourceFile,
        source_bytes: bytes,
        ast: AstTree,
    ):
        """
        Initialize import analyzer.

        Args:
            repo_id: Repository identifier
            nodes: Shared node collection (will be mutated)
            scope: Scope tracking stack
            edge_builder: Edge builder for CONTAINS edges
            source: Source file reference
            source_bytes: Source bytes (for text extraction)
            ast: AST tree (for span extraction)
        """
        self._repo_id = repo_id
        self._nodes = nodes
        self._scope = scope
        self._edge_builder = edge_builder
        self._source = source
        self._source_bytes = source_bytes
        self._ast = ast

    def process_import(self, node: TSNode):
        """
        Process import statement (dispatcher).

        Args:
            node: import_statement or import_from_statement

        Dispatches to:
        - process_import_statement() for `import x`
        - process_import_from_statement() for `from x import y`

        Example:
            >>> # import numpy
            >>> analyzer.process_import(import_ast)
            >>> # from os import path
            >>> analyzer.process_import(from_import_ast)
        """
        if node.type == "import_statement":
            self.process_import_statement(node)
        elif node.type == "import_from_statement":
            self.process_import_from_statement(node)

    def process_import_statement(self, node: TSNode):
        """
        Process `import module [as alias]` statement.

        Args:
            node: import_statement AST node

        Examples:
            >>> # import numpy
            >>> analyzer.process_import_statement(ast)
            >>> # import numpy as np
            >>> analyzer.process_import_statement(ast)
            >>> # import os.path
            >>> analyzer.process_import_statement(ast)
        """
        # import_statement contains dotted_name or aliased_import
        for child in node.children:
            if child.type == "dotted_name":
                # Simple import: import numpy
                module_name = self._get_node_text(child)
                self._create_import_node(node, module_name, module_name)

            elif child.type == "aliased_import":
                # Aliased import: import numpy as np
                name_node = self._find_child_by_type(child, "dotted_name")
                alias_node = child.child_by_field_name("alias")

                if name_node and alias_node:
                    module_name = self._get_node_text(name_node)
                    alias = self._get_node_text(alias_node)
                    self._create_import_node(node, module_name, alias)

    def process_import_from_statement(self, node: TSNode):
        """
        Process `from module import name [as alias]` statement.

        Args:
            node: import_from_statement AST node

        Examples:
            >>> # from os import path
            >>> analyzer.process_import_from_statement(ast)
            >>> # from os import path as p
            >>> analyzer.process_import_from_statement(ast)
            >>> # from os import *
            >>> analyzer.process_import_from_statement(ast)
        """
        # Get module name (from XXX import ...)
        module_node = node.child_by_field_name("module_name")
        if not module_node:
            return

        module_name = self._get_node_text(module_node)

        # Get imported names
        for child in node.children:
            if child.type == "dotted_name" and child != module_node:
                # from module import name
                symbol_name = self._get_node_text(child)
                full_symbol = f"{module_name}.{symbol_name}"
                self._create_import_node(node, full_symbol, symbol_name)

            elif child.type == "aliased_import":
                # from module import name as alias
                name_node = self._find_child_by_type(child, "dotted_name")
                alias_node = child.child_by_field_name("alias")

                if name_node and alias_node:
                    symbol_name = self._get_node_text(name_node)
                    alias = self._get_node_text(alias_node)
                    full_symbol = f"{module_name}.{symbol_name}"
                    self._create_import_node(node, full_symbol, alias)

            elif child.type == "wildcard_import":
                # from module import *
                self._create_import_node(node, f"{module_name}.*", "*")

    def _create_import_node(self, import_node: TSNode, full_symbol: str, alias: str):
        """
        Create IMPORT node, CONTAINS edge, and IMPORTS edge.

        Args:
            import_node: Import AST node
            full_symbol: Full symbol name (e.g., "numpy" or "os.path.join")
            alias: Import alias (same as full_symbol if no alias)

        Example:
            >>> # import numpy as np
            >>> analyzer._create_import_node(ast, "numpy", "np")
            >>> # Creates: IMPORT node + CONTAINS edge (file -> import) + IMPORTS edge (file -> import)
        """
        # Build FQN for import node
        import_fqn = f"{self._scope.module.fqn}.__import__.{full_symbol}"

        # Generate node ID
        span = self._ast.get_span(import_node)
        node_id = generate_logical_id(
            repo_id=self._repo_id,
            kind=NodeKind.IMPORT,
            file_path=self._source.file_path,
            fqn=import_fqn,
        )

        # Create Import node
        import_ir_node = Node(
            id=node_id,
            kind=NodeKind.IMPORT,
            fqn=import_fqn,
            file_path=self._source.file_path,
            span=span,
            language=self._source.language,
            name=full_symbol,
            module_path=self._scope.module.fqn,
            parent_id=self._scope.module.node_id,
            attrs={
                "full_symbol": full_symbol,
                "alias": alias,
                "is_wildcard": alias == "*",
            },
        )

        self._nodes.append(import_ir_node)

        # Add CONTAINS edge from file
        module_node_id = self._scope.module.node_id
        assert module_node_id is not None, "Module scope must have node_id set"
        self._edge_builder.add_contains_edge(module_node_id, node_id, span)

        # Add IMPORTS edge from file to import node
        # This enables cross_reference queries to find import relationships
        self._edge_builder.add_imports_edge(module_node_id, node_id, span)

        # Register import alias in scope
        self._scope.register_import(alias, full_symbol)

    # ============================================================
    # Helper Methods (from IRGenerator)
    # ============================================================

    def _get_node_text(self, node: TSNode) -> str:
        """
        Get text content of AST node.

        Args:
            node: Tree-sitter node

        Returns:
            Node text
        """
        return self._source_bytes[node.start_byte : node.end_byte].decode("utf-8")

    def _find_child_by_type(self, node: TSNode, child_type: str) -> TSNode | None:
        """
        Find first child node of specific type.

        Args:
            node: Parent node
            child_type: Type to find

        Returns:
            First matching child or None
        """
        for child in node.children:
            if child.type == child_type:
                return child
        return None
