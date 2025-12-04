"""
Dependency Analyzer

Analyzes dependency graphs to detect:
- Circular dependencies (using Tarjan's SCC algorithm)
- Dependency layers (topological sorting)
- Change impact analysis
- Dependency metrics
"""

from collections import defaultdict
from typing import Any

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.dependency.models import DependencyGraph

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
        ```
    """

    def __init__(self, graph: DependencyGraph):
        """
        Initialize analyzer.

        Args:
            graph: Dependency graph to analyze
        """
        self.graph = graph
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
        Tarjan's algorithm for finding strongly connected components.

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
        queue = [(source, [source])]
        visited = {source}

        while queue:
            current, path = queue.pop(0)

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


def _example_usage():
    """Example demonstrating dependency analysis."""
    from pathlib import Path

    from src.contexts.code_foundation.infrastructure.dependency.graph_builder import build_dependency_graph
    from src.contexts.code_foundation.infrastructure.parsing import parse_file

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
