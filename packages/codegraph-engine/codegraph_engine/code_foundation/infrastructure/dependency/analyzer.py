"""
Dependency Analyzer

Analyzes dependency graphs to detect:
- Circular dependencies (using Tarjan's SCC algorithm or rustworkx)
- Dependency layers (topological sorting)
- Change impact analysis
- Dependency metrics
- Workspace boundary violations (SOTA monorepo support)

RFC-021: rustworkx integration for 5-20x SCC speedup
"""

from collections import defaultdict, deque
from pathlib import Path
from typing import Any

# rustworkx optional dependency (RFC-021)
try:
    import rustworkx as rx

    HAS_RUSTWORKX = True
except ImportError:
    rx = None  # type: ignore
    HAS_RUSTWORKX = False

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.infrastructure.dependency.models import DependencyGraph
from codegraph_engine.code_foundation.infrastructure.dependency.monorepo_detector import (
    MonorepoDetector,
    WorkspaceBoundary,
)

logger = get_logger(__name__)


class DependencyAnalyzer:
    """
    Analyzes dependency graphs.

    Example:
        ```python
        analyzer = DependencyAnalyzer(graph)

        # Detect circular dependencies
        cycles = analyzer.detect_circular_dependencies()
        for cycle in cycles:
            print(f"Circular dependency: {' -> '.join(cycle)}")

        # Analyze change impact
        affected = analyzer.analyze_change_impact(["src.foundation.ir.models"])
        print(f"Affected modules: {len(affected)}")

        # Calculate dependency layers
        layers = analyzer.calculate_dependency_layers()
        for i, layer in enumerate(layers):
            print(f"Layer {i}: {len(layer)} modules")

        # SOTA: Workspace boundary validation (monorepo support)
        analyzer.detect_workspace_boundary(Path("/path/to/repo"))
        violations = analyzer.validate_workspace_imports()
        for v in violations:
            print(f"Boundary violation: {v}")
        ```
    """

    def __init__(self, graph: DependencyGraph):
        """
        Initialize analyzer.

        Args:
            graph: Dependency graph to analyze
        """
        self.graph = graph
        self._workspace_boundary: WorkspaceBoundary | None = None
        self._monorepo_detector = MonorepoDetector()
        logger.info(
            "dependency_analyzer_initialized",
            repo_id=graph.repo_id,
            node_count=len(graph.nodes),
            edge_count=len(graph.edges),
        )

    def detect_circular_dependencies(self, internal_only: bool = True) -> list[list[str]]:
        """
        Detect circular dependencies using Tarjan's algorithm.

        Finds all strongly connected components (SCCs) with size > 1,
        which represent circular dependencies.

        Args:
            internal_only: Only consider internal dependencies

        Returns:
            List of cycles, where each cycle is a list of module paths
        """
        logger.info(
            "detecting_circular_dependencies",
            internal_only=internal_only,
        )

        # Get nodes to analyze
        if internal_only:
            nodes_to_analyze = {node.module_path for node in self.graph.get_internal_nodes()}
        else:
            nodes_to_analyze = set(self.graph.nodes.keys())

        # Run Tarjan's algorithm
        sccs = self._tarjan_scc(nodes_to_analyze)

        # Filter to only cycles (SCCs with > 1 node)
        cycles = [scc for scc in sccs if len(scc) > 1]

        # Store in graph
        self.graph.circular_dependencies = cycles

        logger.info(
            "circular_dependencies_detected",
            cycle_count=len(cycles),
            total_scc_count=len(sccs),
        )

        return cycles

    def _tarjan_scc(self, nodes: set[str]) -> list[list[str]]:
        """
        Find strongly connected components (with rustworkx acceleration).

        RFC-021: Automatic rustworkx acceleration when available.
        실측: 0.7-1.1x 성능, 하지만 ≥1000 nodes 시 Python 불가능으로 필수

        Time complexity:
            - rustworkx: O(V+E) with Rust optimization
            - Python: O(V+E) Tarjan's algorithm

        Args:
            nodes: Set of node IDs to analyze

        Returns:
            List of SCCs, where each SCC is a list of node IDs
        """
        # Check if rustworkx usage is enabled (can be configured)
        from codegraph_engine.code_foundation.infrastructure.dfg.ssa.dominator import is_rustworkx_enabled

        # Try rustworkx first (if enabled)
        if is_rustworkx_enabled() and HAS_RUSTWORKX:
            try:
                return self._tarjan_scc_rustworkx(nodes)
            except Exception:
                # Fallback to Python if rustworkx fails
                pass

        # Fallback to Python implementation
        return self._tarjan_scc_python(nodes)

    def _tarjan_scc_rustworkx(self, nodes: set[str]) -> list[list[str]]:
        """
        Strongly connected components using rustworkx (5-20x faster).

        RFC-021 Phase 1: rustworkx selective adoption

        Args:
            nodes: Set of node IDs to analyze

        Returns:
            List of SCCs, where each SCC is a list of node IDs

        Raises:
            ImportError: If rustworkx is not available
        """
        if not HAS_RUSTWORKX:
            raise ImportError("rustworkx is required. Install with: pip install rustworkx")

        # Build rustworkx graph
        graph = rx.PyDiGraph()
        node_map: dict[str, int] = {}
        index_to_id: dict[int, str] = {}

        # Add nodes
        for node_id in nodes:
            idx = graph.add_node(node_id)
            node_map[node_id] = idx
            index_to_id[idx] = node_id

        # Add edges
        for node_id in nodes:
            dependencies = self.graph.get_dependencies(node_id)
            if node_id not in node_map:
                continue

            for dep in dependencies:
                if dep not in node_map:
                    continue
                graph.add_edge(node_map[node_id], node_map[dep], None)

        # Compute SCCs using rustworkx (1 line!)
        scc_indices = rx.strongly_connected_components(graph)

        # Convert indices to node IDs
        sccs = [[index_to_id[idx] for idx in scc] for scc in scc_indices]

        return sccs

    def _tarjan_scc_python(self, nodes: set[str]) -> list[list[str]]:
        """
        Tarjan's algorithm for finding strongly connected components (Python fallback).

        Time complexity: O(V + E)

        Args:
            nodes: Set of node IDs to analyze

        Returns:
            List of SCCs, where each SCC is a list of node IDs
        """
        # Algorithm state
        index_counter = [0]  # Use list to make it mutable in nested function
        stack: list[str] = []
        lowlinks: dict[str, int] = {}
        index: dict[str, int] = {}
        on_stack: dict[str, bool] = defaultdict(bool)
        sccs: list[list[str]] = []

        def strongconnect(node: str) -> None:
            """Recursive helper for Tarjan's algorithm."""
            # Set the depth index for this node
            index[node] = index_counter[0]
            lowlinks[node] = index_counter[0]
            index_counter[0] += 1
            stack.append(node)
            on_stack[node] = True

            # Consider successors of node
            successors = self.graph.get_dependencies(node)
            for successor in successors:
                if successor not in nodes:
                    # Skip nodes not in analysis set
                    continue

                if successor not in index:
                    # Successor has not yet been visited; recurse
                    strongconnect(successor)
                    lowlinks[node] = min(lowlinks[node], lowlinks[successor])
                elif on_stack[successor]:
                    # Successor is in stack and hence in the current SCC
                    lowlinks[node] = min(lowlinks[node], index[successor])

            # If node is a root node, pop the stack and create an SCC
            if lowlinks[node] == index[node]:
                scc = []
                while True:
                    successor = stack.pop()
                    on_stack[successor] = False
                    scc.append(successor)
                    if successor == node:
                        break
                sccs.append(scc)

        # Run algorithm on all nodes
        for node in nodes:
            if node not in index:
                strongconnect(node)

        return sccs

    def calculate_dependency_layers(self, internal_only: bool = True) -> list[set[str]]:
        """
        Calculate dependency layers using modified Kahn's algorithm.

        Modules with no dependencies are in layer 0.
        Modules that only depend on layer N are in layer N+1.

        Args:
            internal_only: Only consider internal dependencies

        Returns:
            List of layers, where each layer is a set of module paths
        """
        logger.info(
            "calculating_dependency_layers",
            internal_only=internal_only,
        )

        # Get nodes to analyze
        if internal_only:
            nodes_to_analyze = {node.module_path for node in self.graph.get_internal_nodes()}
        else:
            nodes_to_analyze = set(self.graph.nodes.keys())

        # Calculate in-degree for each node
        in_degree = dict.fromkeys(nodes_to_analyze, 0)
        for node in nodes_to_analyze:
            deps = self.graph.get_dependencies(node)
            # Count only dependencies within analysis set
            in_degree[node] = len(deps & nodes_to_analyze)

        # Process layers
        layers = []
        remaining = set(nodes_to_analyze)

        while remaining:
            # Find all nodes with in-degree 0
            current_layer = {node for node in remaining if in_degree[node] == 0}

            if not current_layer:
                # Circular dependency prevents complete layering
                # Put remaining nodes in final layer
                logger.warning(
                    "circular_dependency_prevents_layering",
                    remaining_count=len(remaining),
                )
                layers.append(remaining)
                break

            layers.append(current_layer)
            remaining -= current_layer

            # Update in-degrees
            for node in current_layer:
                # Get dependents of this node
                dependents = self.graph.get_dependents(node)
                for dependent in dependents & remaining:
                    in_degree[dependent] -= 1

        # Store in graph
        self.graph.dependency_layers = layers

        logger.info(
            "dependency_layers_calculated",
            layer_count=len(layers),
            max_layer_size=max(len(layer) for layer in layers) if layers else 0,
        )

        return layers

    def analyze_change_impact(
        self,
        changed_modules: list[str],
        max_depth: int | None = None,
        internal_only: bool = True,
    ) -> dict[str, Any]:
        """
        Analyze the impact of changes to specific modules.

        Finds all modules that (transitively) depend on the changed modules.

        Args:
            changed_modules: List of module paths that changed
            max_depth: Maximum depth to traverse (None = unlimited)
            internal_only: Only consider internal modules as affected

        Returns:
            Dictionary with impact analysis results
        """
        logger.info(
            "analyzing_change_impact",
            changed_module_count=len(changed_modules),
            max_depth=max_depth,
            internal_only=internal_only,
        )

        # Collect all affected modules
        directly_affected = set()
        transitively_affected = set()

        for module in changed_modules:
            # Get direct dependents
            direct = self.graph.get_dependents(module)
            directly_affected.update(direct)

            # Get transitive dependents
            transitive = self.graph.get_transitive_dependents(module, max_depth)
            transitively_affected.update(transitive)

        # Remove changed modules from affected sets
        directly_affected -= set(changed_modules)
        transitively_affected -= set(changed_modules)

        # Filter to internal only if requested
        if internal_only:
            internal_modules = {node.module_path for node in self.graph.get_internal_nodes()}
            directly_affected &= internal_modules
            transitively_affected &= internal_modules

        # Calculate total affected (direct + transitive)
        all_affected = directly_affected | transitively_affected

        result = {
            "changed_modules": changed_modules,
            "directly_affected": sorted(directly_affected),
            "transitively_affected": sorted(transitively_affected),
            "all_affected": sorted(all_affected),
            "direct_count": len(directly_affected),
            "transitive_count": len(transitively_affected),
            "total_affected_count": len(all_affected),
        }

        logger.info(
            "change_impact_analyzed",
            direct_count=result["direct_count"],
            transitive_count=result["transitive_count"],
            total_count=result["total_affected_count"],
        )

        return result

    def calculate_metrics(self) -> dict[str, Any]:
        """
        Calculate various dependency metrics.

        Returns:
            Dictionary with dependency metrics
        """
        logger.info("calculating_dependency_metrics")

        internal_nodes = self.graph.get_internal_nodes()
        internal_module_paths = {node.module_path for node in internal_nodes}

        if not internal_nodes:
            return {
                "total_internal_modules": 0,
                "avg_dependencies": 0.0,
                "avg_dependents": 0.0,
                "max_dependencies": 0,
                "max_dependents": 0,
                "modules_with_no_dependencies": 0,
                "modules_with_no_dependents": 0,
            }

        # Calculate dependency counts
        dependency_counts = []
        dependent_counts = []
        no_deps = 0
        no_dependents = 0

        for node in internal_nodes:
            # Count internal dependencies only
            deps = self.graph.get_dependencies(node.module_path)
            internal_deps = deps & internal_module_paths
            dep_count = len(internal_deps)
            dependency_counts.append(dep_count)
            if dep_count == 0:
                no_deps += 1

            # Count internal dependents only
            dependents = self.graph.get_dependents(node.module_path)
            internal_dependents = dependents & internal_module_paths
            dependent_count = len(internal_dependents)
            dependent_counts.append(dependent_count)
            if dependent_count == 0:
                no_dependents += 1

        metrics = {
            "total_internal_modules": len(internal_nodes),
            "avg_dependencies": (sum(dependency_counts) / len(dependency_counts) if dependency_counts else 0.0),
            "avg_dependents": (sum(dependent_counts) / len(dependent_counts) if dependent_counts else 0.0),
            "max_dependencies": max(dependency_counts) if dependency_counts else 0,
            "max_dependents": max(dependent_counts) if dependent_counts else 0,
            "modules_with_no_dependencies": no_deps,
            "modules_with_no_dependents": no_dependents,
        }

        logger.info("dependency_metrics_calculated", **metrics)

        return metrics

    def find_dependency_path(self, source: str, target: str, max_depth: int = 10) -> list[str] | None:
        """
        Find a dependency path from source to target using BFS.

        Args:
            source: Source module path
            target: Target module path
            max_depth: Maximum path length to search

        Returns:
            List of module paths forming the dependency chain,
            or None if no path exists
        """
        if source == target:
            return [source]

        # BFS to find shortest path
        queue = deque([(source, [source])])
        visited = {source}

        while queue:
            current, path = queue.popleft()

            if len(path) > max_depth:
                continue

            # Get dependencies of current
            deps = self.graph.get_dependencies(current)

            for dep in deps:
                if dep == target:
                    # Found target
                    return path + [dep]

                if dep not in visited:
                    visited.add(dep)
                    queue.append((dep, path + [dep]))

        # No path found
        return None

    def get_most_depended_upon(self, top_n: int = 10) -> list[tuple[str, int]]:
        """
        Get the most depended-upon internal modules.

        Args:
            top_n: Number of modules to return

        Returns:
            List of (module_path, dependent_count) tuples
        """
        internal_nodes = self.graph.get_internal_nodes()
        internal_module_paths = {node.module_path for node in internal_nodes}

        # Count internal dependents for each module
        dependent_counts = []
        for node in internal_nodes:
            dependents = self.graph.get_dependents(node.module_path)
            internal_dependents = dependents & internal_module_paths
            dependent_counts.append((node.module_path, len(internal_dependents)))

        # Sort by count (descending)
        dependent_counts.sort(key=lambda x: x[1], reverse=True)

        return dependent_counts[:top_n]

    def get_most_dependent(self, top_n: int = 10) -> list[tuple[str, int]]:
        """
        Get the modules with the most dependencies.

        Args:
            top_n: Number of modules to return

        Returns:
            List of (module_path, dependency_count) tuples
        """
        internal_nodes = self.graph.get_internal_nodes()
        internal_module_paths = {node.module_path for node in internal_nodes}

        # Count internal dependencies for each module
        dependency_counts = []
        for node in internal_nodes:
            deps = self.graph.get_dependencies(node.module_path)
            internal_deps = deps & internal_module_paths
            dependency_counts.append((node.module_path, len(internal_deps)))

        # Sort by count (descending)
        dependency_counts.sort(key=lambda x: x[1], reverse=True)

        return dependency_counts[:top_n]

    # =========================================================================
    # SOTA: Monorepo Workspace Boundary Support
    # =========================================================================

    def detect_workspace_boundary(self, repo_root: Path) -> WorkspaceBoundary | None:
        """
        Auto-detect monorepo workspace boundary.

        Supports: npm/yarn/pnpm workspaces, Cargo, Go, Lerna, Nx, Turborepo

        Args:
            repo_root: Repository root directory

        Returns:
            Detected WorkspaceBoundary or None if not a monorepo
        """
        boundary = self._monorepo_detector.detect(repo_root)
        if boundary:
            self._workspace_boundary = boundary
            logger.info(
                "workspace_boundary_detected",
                workspace_type=boundary.workspace_type.value,
                package_count=len(boundary.packages),
                packages=list(boundary.packages.keys())[:10],  # First 10
            )
        else:
            logger.info("no_workspace_boundary_detected", repo_root=str(repo_root))
        return boundary

    def set_workspace_boundary(self, boundary: WorkspaceBoundary) -> None:
        """
        Manually set workspace boundary.

        Args:
            boundary: Pre-configured WorkspaceBoundary
        """
        self._workspace_boundary = boundary
        logger.info(
            "workspace_boundary_set",
            workspace_type=boundary.workspace_type.value,
            package_count=len(boundary.packages),
        )

    def get_workspace_boundary(self) -> WorkspaceBoundary | None:
        """Get the current workspace boundary."""
        return self._workspace_boundary

    def validate_workspace_imports(self) -> list[dict[str, Any]]:
        """
        Validate all imports against workspace boundaries.

        Detects:
        - Cross-package imports without declared dependencies
        - Imports from private packages
        - Restricted package access violations

        Returns:
            List of violations with details:
            [
                {
                    "from_module": "packages/frontend/src/app.ts",
                    "to_module": "@org/backend",
                    "violation_type": "undeclared_dependency",
                    "message": "Package 'frontend' does not declare dependency on '@org/backend'"
                }
            ]
        """
        if not self._workspace_boundary:
            logger.warning("validate_workspace_imports_no_boundary")
            return []

        violations: list[dict[str, Any]] = []

        # Iterate through all edges in the dependency graph
        for edge in self.graph.edges:
            from_module = edge.source
            to_module = edge.target

            # Get the source node to find its file path
            from_node = self.graph.nodes.get(from_module)
            if not from_node or not from_node.file_path:
                continue

            from_path = Path(from_node.file_path)

            # Check if import crosses workspace boundary
            allowed, reason = self._workspace_boundary.is_import_allowed(from_path, to_module)

            if not allowed:
                violation_type = self._classify_violation(reason)
                violations.append(
                    {
                        "from_module": from_module,
                        "to_module": to_module,
                        "from_file": str(from_path),
                        "violation_type": violation_type,
                        "message": reason,
                    }
                )

        logger.info(
            "workspace_imports_validated",
            total_edges=len(list(self.graph.edges)),
            violation_count=len(violations),
        )

        return violations

    def _classify_violation(self, reason: str | None) -> str:
        """Classify violation type from reason string."""
        if not reason:
            return "unknown"
        if "not accessible" in reason:
            return "private_package"
        if "does not declare dependency" in reason:
            return "undeclared_dependency"
        if "restricted" in reason.lower():
            return "restricted_access"
        return "boundary_violation"

    def get_cross_package_dependencies(self) -> dict[str, dict[str, int]]:
        """
        Get cross-package dependency counts for workspace visualization.

        Returns:
            Dict mapping source package -> {target package -> count}
            Example: {"frontend": {"backend": 5, "shared": 10}}
        """
        if not self._workspace_boundary:
            return {}

        cross_deps: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for edge in self.graph.edges:
            from_node = self.graph.nodes.get(edge.source)
            to_node = self.graph.nodes.get(edge.target)

            if not from_node or not from_node.file_path:
                continue

            from_path = Path(from_node.file_path)
            from_pkg = self._workspace_boundary.get_package_for_path(from_path)

            # Determine target package
            to_pkg_name: str | None = None
            if to_node and to_node.file_path:
                to_path = Path(to_node.file_path)
                to_pkg = self._workspace_boundary.get_package_for_path(to_path)
                if to_pkg:
                    to_pkg_name = to_pkg.name

            if not to_pkg_name:
                # Check if to_module matches a package name
                to_pkg_name = edge.target

            if from_pkg and to_pkg_name and from_pkg.name != to_pkg_name:
                cross_deps[from_pkg.name][to_pkg_name] += 1

        return {k: dict(v) for k, v in cross_deps.items()}

    def get_workspace_metrics(self) -> dict[str, Any]:
        """
        Get workspace-level dependency metrics.

        Returns:
            Dict with workspace metrics including:
            - package_count: Number of packages
            - total_cross_deps: Total cross-package dependencies
            - most_imported_package: Package with most importers
            - most_importing_package: Package that imports the most
            - boundary_violations: Count of violations
        """
        if not self._workspace_boundary:
            return {"error": "No workspace boundary configured"}

        cross_deps = self.get_cross_package_dependencies()
        violations = self.validate_workspace_imports()

        # Calculate imports received by each package
        imports_received: dict[str, int] = defaultdict(int)
        imports_made: dict[str, int] = defaultdict(int)

        for from_pkg, targets in cross_deps.items():
            for to_pkg, count in targets.items():
                imports_received[to_pkg] += count
                imports_made[from_pkg] += count

        most_imported = max(imports_received.items(), key=lambda x: x[1]) if imports_received else ("", 0)
        most_importing = max(imports_made.items(), key=lambda x: x[1]) if imports_made else ("", 0)

        return {
            "workspace_type": self._workspace_boundary.workspace_type.value,
            "package_count": len(self._workspace_boundary.packages),
            "packages": list(self._workspace_boundary.packages.keys()),
            "total_cross_package_dependencies": sum(sum(targets.values()) for targets in cross_deps.values()),
            "most_imported_package": {
                "name": most_imported[0],
                "import_count": most_imported[1],
            },
            "most_importing_package": {
                "name": most_importing[0],
                "import_count": most_importing[1],
            },
            "boundary_violation_count": len(violations),
            "strict_boundaries": self._workspace_boundary.strict_boundaries,
        }


def _example_usage():
    """Example demonstrating dependency analysis."""
    from pathlib import Path

    from codegraph_engine.code_foundation.infrastructure.dependency.graph_builder import build_dependency_graph
    from codegraph_engine.code_foundation.infrastructure.parsing import parse_file

    # Parse some files
    repo_root = Path.cwd()
    files_to_parse = [
        repo_root / "src" / "foundation" / "ir" / "models" / "core.py",
        repo_root / "src" / "foundation" / "graph" / "builder.py",
        repo_root / "src" / "foundation" / "dependency" / "models.py",
    ]

    ir_documents = []
    for file_path in files_to_parse:
        if file_path.exists():
            doc = parse_file(str(file_path), language="python")
            if doc:
                ir_documents.append(doc)

    if not ir_documents:
        print("No files parsed")
        return

    # Build dependency graph
    graph = build_dependency_graph(
        ir_documents=ir_documents,
        repo_id="semantica-v2",
        snapshot_id="HEAD",
        repo_root=repo_root,
    )

    # Analyze
    analyzer = DependencyAnalyzer(graph)

    # Detect circular dependencies
    print("\n=== Circular Dependencies ===")
    cycles = analyzer.detect_circular_dependencies()
    if cycles:
        for i, cycle in enumerate(cycles, 1):
            print(f"\nCycle {i}:")
            print(f"  {' -> '.join(cycle)} -> {cycle[0]}")
    else:
        print("No circular dependencies detected")

    # Calculate layers
    print("\n=== Dependency Layers ===")
    layers = analyzer.calculate_dependency_layers()
    for i, layer in enumerate(layers):
        print(f"\nLayer {i} ({len(layer)} modules):")
        for module in sorted(layer)[:3]:
            print(f"  - {module}")
        if len(layer) > 3:
            print(f"  ... and {len(layer) - 3} more")

    # Calculate metrics
    print("\n=== Dependency Metrics ===")
    metrics = analyzer.calculate_metrics()
    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"{key}: {value:.2f}")
        else:
            print(f"{key}: {value}")

    # Most depended upon
    print("\n=== Most Depended Upon ===")
    most_depended = analyzer.get_most_depended_upon(top_n=5)
    for module, count in most_depended:
        print(f"- {module}: {count} dependents")


if __name__ == "__main__":
    _example_usage()
