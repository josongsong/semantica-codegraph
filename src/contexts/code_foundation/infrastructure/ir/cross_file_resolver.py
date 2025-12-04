"""
Cross-file Reference Resolver

Resolves cross-file references for project-wide context.

Key features:
1. Global symbol table (FQN → Node mapping)
2. Import resolution (import → actual file)
3. Dependency graph (file → dependencies)
4. Topological ordering (for retrieval ranking)

Example usage:
    resolver = CrossFileResolver()
    global_ctx = resolver.resolve(ir_docs)

    # Query
    resolved = global_ctx.resolve_symbol("calc.Calculator")
    deps = global_ctx.get_dependencies("src/main.py")
    order = global_ctx.get_topological_order()
"""

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.ir.models.core import EdgeKind

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.ir.models.core import Node
    from src.contexts.code_foundation.infrastructure.ir.models.document import IRDocument

logger = get_logger(__name__)


@dataclass
class ResolvedSymbol:
    """Resolved symbol with location"""

    fqn: str
    node_id: str
    file_path: str


@dataclass
class GlobalContext:
    """
    Project-wide context.

    Contains:
    - Global symbol table (FQN → Node)
    - Import resolution (import → file)
    - Dependency graph (file → dependencies)
    - Topological order (for ranking)
    """

    # FQN → (Node, file_path)
    symbol_table: dict[str, tuple["Node", str]] = field(default_factory=dict)

    # file → dependencies
    dependencies: dict[str, set[str]] = field(default_factory=dict)

    # file → dependents (reverse deps)
    dependents: dict[str, set[str]] = field(default_factory=dict)

    # Dependency graph (topological order)
    dep_order: list[str] = field(default_factory=list)

    # Stats
    total_symbols: int = 0
    total_files: int = 0

    def register_symbol(self, fqn: str, node: "Node", file_path: str):
        """
        Register symbol in global table.

        Args:
            fqn: Fully qualified name
            node: Symbol node
            file_path: File containing symbol
        """
        self.symbol_table[fqn] = (node, file_path)
        self.total_symbols += 1

    def resolve_symbol(self, fqn: str) -> ResolvedSymbol | None:
        """
        Resolve FQN → Node.

        Args:
            fqn: Fully qualified name

        Returns:
            ResolvedSymbol with location, or None if not found
        """
        if fqn not in self.symbol_table:
            return None

        node, file_path = self.symbol_table[fqn]
        return ResolvedSymbol(
            fqn=fqn,
            node_id=node.id,
            file_path=file_path,
        )

    def add_dependency(self, from_file: str, to_file: str):
        """
        Add file dependency.

        Args:
            from_file: Source file (depends on to_file)
            to_file: Target file (dependency)
        """
        self.dependencies.setdefault(from_file, set()).add(to_file)
        self.dependents.setdefault(to_file, set()).add(from_file)

    def get_dependencies(self, file_path: str) -> set[str]:
        """
        Get all dependencies of a file.

        Args:
            file_path: File path

        Returns:
            Set of dependency file paths
        """
        return self.dependencies.get(file_path, set())

    def get_dependents(self, file_path: str) -> set[str]:
        """
        Get all files that depend on this file.

        Args:
            file_path: File path

        Returns:
            Set of dependent file paths
        """
        return self.dependents.get(file_path, set())

    def build_dependency_graph(self):
        """
        Build topological order (for retrieval ranking).

        Topological sort gives us:
        - Files with no dependencies first (base/utility modules)
        - Files with many dependents ranked higher (popular modules)
        """
        # Collect all files
        all_files = set(self.dependencies.keys()) | set(dep for deps in self.dependencies.values() for dep in deps)
        self.total_files = len(all_files)

        # Calculate in-degree (number of dependencies)
        in_degree = {f: 0 for f in all_files}
        for deps in self.dependencies.values():
            for dep in deps:
                in_degree[dep] = in_degree.get(dep, 0) + 1

        # Topological sort (Kahn's algorithm)
        queue = deque([f for f in in_degree if in_degree[f] == 0])
        order = []

        while queue:
            file = queue.popleft()
            order.append(file)

            # Update in-degree for dependents
            for dep_file in self.dependencies.get(file, []):
                in_degree[dep_file] -= 1
                if in_degree[dep_file] == 0:
                    queue.append(dep_file)

        self.dep_order = order

        logger.debug(f"Built dependency graph: {len(order)} files in topological order")

    def get_topological_order(self) -> list[str]:
        """
        Get topological order (base modules first).

        Returns:
            List of file paths in topological order
        """
        if not self.dep_order:
            self.build_dependency_graph()
        return self.dep_order

    def get_stats(self) -> dict[str, int]:
        """Get context statistics"""
        return {
            "total_symbols": self.total_symbols,
            "total_files": self.total_files,
            "total_dependencies": sum(len(deps) for deps in self.dependencies.values()),
        }


class CrossFileResolver:
    """
    Cross-file reference resolver.

    Resolves:
    1. Symbol definitions (FQN → Node)
    2. Import targets (import → file)
    3. Dependencies (file → dependencies)

    Example usage:
        resolver = CrossFileResolver()
        global_ctx = resolver.resolve(ir_docs)

        # Query resolved symbol
        resolved = global_ctx.resolve_symbol("calc.Calculator")
        print(f"Calculator defined in {resolved.file_path}")

        # Query dependencies
        deps = global_ctx.get_dependencies("src/main.py")
        print(f"main.py depends on: {deps}")
    """

    def __init__(self):
        self.logger = logger

    def resolve(
        self,
        ir_docs: dict[str, "IRDocument"],
    ) -> GlobalContext:
        """
        Resolve all cross-file references.

        Args:
            ir_docs: Mapping of file_path → IRDocument

        Returns:
            GlobalContext with resolved references
        """
        self.logger.info(f"Resolving cross-file references for {len(ir_docs)} files")

        global_ctx = GlobalContext()

        # Convert list to dict if needed
        if isinstance(ir_docs, list):
            ir_docs_dict = {doc.nodes[0].file_path if doc.nodes else f"file_{i}": doc for i, doc in enumerate(ir_docs)}
        else:
            ir_docs_dict = ir_docs

        # ============================================================
        # Step 1: Build global symbol table
        # ============================================================
        for file_path, ir_doc in ir_docs_dict.items():
            for node in ir_doc.nodes:
                if node.fqn:
                    global_ctx.register_symbol(node.fqn, node, file_path)

        self.logger.debug(f"Built symbol table: {global_ctx.total_symbols} symbols")

        # ============================================================
        # Step 2: Resolve imports
        # ============================================================
        for file_path, ir_doc in ir_docs_dict.items():
            # Find all IMPORTS edges
            import_edges = [e for e in ir_doc.edges if e.kind == EdgeKind.IMPORTS]

            for edge in import_edges:
                # Get imported name (FQN or module path)
                imported_name = edge.attrs.get("imported_name") or edge.attrs.get("module_path")

                if not imported_name:
                    continue

                # Try to resolve FQN
                resolved = global_ctx.resolve_symbol(imported_name)

                if resolved:
                    # Found! Update edge attrs
                    edge.attrs["resolved_file"] = resolved.file_path
                    edge.attrs["resolved_node_id"] = resolved.node_id

                    # Add dependency
                    global_ctx.add_dependency(file_path, resolved.file_path)
                else:
                    # Try partial match (module.submodule → module)
                    self._try_partial_resolve(
                        imported_name,
                        file_path,
                        edge,
                        global_ctx,
                        ir_docs,
                    )

        # ============================================================
        # Step 3: Build dependency graph
        # ============================================================
        global_ctx.build_dependency_graph()

        stats = global_ctx.get_stats()
        self.logger.info(
            f"Resolved {stats['total_symbols']} symbols, "
            f"{stats['total_files']} files, "
            f"{stats['total_dependencies']} dependencies"
        )

        return global_ctx

    def _try_partial_resolve(
        self,
        imported_name: str,
        file_path: str,
        edge: any,
        global_ctx: GlobalContext,
        ir_docs: dict[str, "IRDocument"],
    ):
        """
        Try partial resolution for module imports.

        E.g., "module.submodule.Class" → try "module.submodule" → "module"

        Args:
            imported_name: Imported name to resolve
            file_path: Current file path
            edge: Import edge
            global_ctx: Global context
            ir_docs: All IR documents
        """
        parts = imported_name.split(".")

        # Try progressively shorter names
        for i in range(len(parts) - 1, 0, -1):
            partial_name = ".".join(parts[:i])
            resolved = global_ctx.resolve_symbol(partial_name)

            if resolved:
                edge.attrs["resolved_file"] = resolved.file_path
                edge.attrs["resolved_module"] = partial_name
                global_ctx.add_dependency(file_path, resolved.file_path)
                return

        # Last resort: Try to find by module path
        # E.g., "calc" might be in "src/calc.py" or "calc/__init__.py"
        self._try_module_path_resolve(
            parts[0],
            file_path,
            edge,
            global_ctx,
            ir_docs,
        )

    def _try_module_path_resolve(
        self,
        module_name: str,
        file_path: str,
        edge: any,
        global_ctx: GlobalContext,
        ir_docs: dict[str, "IRDocument"],
    ):
        """
        Try to resolve by module path.

        E.g., "calc" → "src/calc.py" or "calc/__init__.py"

        Args:
            module_name: Module name
            file_path: Current file path
            edge: Import edge
            global_ctx: Global context
            ir_docs: All IR documents
        """
        # Try common patterns
        candidates = [
            f"{module_name}.py",
            f"src/{module_name}.py",
            f"{module_name}/__init__.py",
            f"src/{module_name}/__init__.py",
        ]

        for candidate in candidates:
            if candidate in ir_docs:
                edge.attrs["resolved_file"] = candidate
                edge.attrs["resolved_module"] = module_name
                global_ctx.add_dependency(file_path, candidate)
                return
