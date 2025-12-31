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

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.ir.models.core import EdgeKind

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument

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
        all_files = set(self.dependencies.keys()) | {dep for deps in self.dependencies.values() for dep in deps}
        self.total_files = len(all_files)

        # Calculate in-degree (number of dependencies)
        in_degree = dict.fromkeys(all_files, 0)
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

    @classmethod
    def from_rust_dict(cls, rust_dict: dict) -> "GlobalContext":
        """Create GlobalContext from Rust API result.

        Args:
            rust_dict: Result from Rust build_global_context API with fields:
                - total_symbols: usize
                - total_files: usize
                - total_imports: usize (unused)
                - total_dependencies: usize (unused)
                - symbol_table: HashMap<String, Symbol> (simplified, no Node objects)
                - file_dependencies: HashMap<String, Vec<String>>
                - file_dependents: HashMap<String, Vec<String>>
                - topological_order: Vec<String>
                - build_duration_ms: u64 (unused)

        Returns:
            GlobalContext instance

        Note:
            Rust API returns simplified symbol_table without full Node objects.
            For full context, use Python-based CrossFileResolver.resolve().
        """
        # Convert file_dependencies from dict[str, list] to dict[str, set]
        dependencies = {k: set(v) for k, v in rust_dict.get("file_dependencies", {}).items()}

        # Convert file_dependents from dict[str, list] to dict[str, set]
        dependents = {k: set(v) for k, v in rust_dict.get("file_dependents", {}).items()}

        # NOTE: symbol_table from Rust is simplified (no Node objects)
        # We leave it empty for now - users should use CrossFileResolver for full context
        symbol_table: dict[str, tuple["Node", str]] = {}

        return cls(
            symbol_table=symbol_table,
            dependencies=dependencies,
            dependents=dependents,
            dep_order=rust_dict.get("topological_order", []),
            total_symbols=rust_dict.get("total_symbols", 0),
            total_files=rust_dict.get("total_files", 0),
        )

    def to_rust_dict(self) -> dict:
        """Convert GlobalContext to Rust API format.

        Returns:
            Dict compatible with Rust update_global_context API
        """
        return {
            "total_symbols": self.total_symbols,
            "total_files": self.total_files,
            "total_imports": 0,  # Not tracked in Python
            "total_dependencies": sum(len(deps) for deps in self.dependencies.values()),
            "symbol_table": {},  # Simplified for Rust
            "file_dependencies": {k: list(v) for k, v in self.dependencies.items()},
            "file_dependents": {k: list(v) for k, v in self.dependents.items()},
            "topological_order": self.dep_order,
            "build_duration_ms": 0,
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

        # Build node index for O(1) lookup (target_id → node)
        node_by_id: dict[str, "Node"] = {}
        for ir_doc in ir_docs_dict.values():
            for node in ir_doc.nodes:
                node_by_id[node.id] = node

        for file_path, ir_doc in ir_docs_dict.items():
            # Find all IMPORTS edges
            import_edges = [e for e in ir_doc.edges if e.kind == EdgeKind.IMPORTS]

            for edge in import_edges:
                # Get imported name from edge.attrs or target node.attrs
                # Priority: edge.attrs > target_node.attrs (full_symbol) > target_node.name
                imported_name = edge.attrs.get("imported_name") or edge.attrs.get("module_path")

                if not imported_name:
                    # BUG FIX: Look up target node to get import info
                    target_node = node_by_id.get(edge.target_id)
                    if target_node:
                        # Try full_symbol first (e.g., "abc.ABC")
                        imported_name = target_node.attrs.get("full_symbol") if target_node.attrs else None
                        # Fall back to node.name (e.g., "os", "sys")
                        if not imported_name:
                            imported_name = target_node.name

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

    def resolve_incremental(
        self,
        changed_files: set[str],
        new_ir_docs: dict[str, "IRDocument"],
        existing_ctx: GlobalContext,
        existing_ir_docs: dict[str, "IRDocument"],
    ) -> tuple[GlobalContext, set[str]]:
        """
        Incrementally resolve cross-file references.

        Only re-resolves:
        1. Changed files
        2. Files that depend on changed files (dependents)

        Args:
            changed_files: Set of changed file paths
            new_ir_docs: New IR documents for changed files
            existing_ctx: Existing GlobalContext
            existing_ir_docs: Existing IR documents (unchanged files)

        Returns:
            (updated_ctx, affected_files) - Updated context and set of affected files
        """
        self.logger.info(f"Incremental resolve: {len(changed_files)} changed, {len(existing_ir_docs)} existing")

        # Step 1: Find all affected files (changed + dependents)
        affected_files = set(changed_files)

        for changed_file in changed_files:
            # Add direct dependents (files that import this file)
            dependents = existing_ctx.get_dependents(changed_file)
            affected_files.update(dependents)

            # Add transitive dependents (files that depend on dependents)
            queue = list(dependents)
            visited = set(dependents)
            while queue:
                dep = queue.pop()
                for trans_dep in existing_ctx.get_dependents(dep):
                    if trans_dep not in visited:
                        visited.add(trans_dep)
                        affected_files.add(trans_dep)
                        queue.append(trans_dep)

        self.logger.debug(
            f"Affected files: {len(affected_files)} "
            f"(changed: {len(changed_files)}, dependents: {len(affected_files) - len(changed_files)})"
        )

        # Step 2: Merge IR docs
        merged_ir_docs: dict[str, IRDocument] = {}

        # Add unchanged files (not affected)
        for file_path, ir_doc in existing_ir_docs.items():
            if file_path not in affected_files:
                merged_ir_docs[file_path] = ir_doc

        # Add new/updated files
        for file_path, ir_doc in new_ir_docs.items():
            merged_ir_docs[file_path] = ir_doc

        # Step 3: Re-resolve all (full resolution on merged docs)
        # NOTE: For true incremental, we'd only re-resolve affected files
        # but symbol table needs to be consistent, so full resolve is safer
        new_ctx = self.resolve(merged_ir_docs)

        return new_ctx, affected_files
