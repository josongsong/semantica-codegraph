"""
Dependency Resolution System

Resolves import statements to actual modules, builds dependency graphs,
and analyzes dependencies for circular dependencies, change impact, etc.

Architecture:
- models: Core data models (DependencyNode, DependencyGraph, DependencyEdge)
- python_resolver: Python-specific import resolution
- graph_builder: Constructs dependency graphs from IR
- analyzer: Analyzes dependency graphs (cycles, impact, etc.)
- monorepo_detector: SOTA monorepo workspace boundary detection
"""

from codegraph_engine.code_foundation.infrastructure.dependency.analyzer import DependencyAnalyzer
from codegraph_engine.code_foundation.infrastructure.dependency.graph_builder import (
    DependencyGraphBuilder,
    build_dependency_graph,
)
from codegraph_engine.code_foundation.infrastructure.dependency.models import (
    DependencyEdge,
    DependencyEdgeKind,
    DependencyGraph,
    DependencyKind,
    DependencyNode,
    ImportLocation,
)
from codegraph_engine.code_foundation.infrastructure.dependency.monorepo_detector import (
    MonorepoDetector,
    PackageVisibility,
    WorkspaceBoundary,
    WorkspacePackage,
    WorkspaceType,
    validate_workspace_imports,
)
from codegraph_engine.code_foundation.infrastructure.dependency.python_resolver import PythonResolver

__all__ = [
    # Models
    "DependencyKind",
    "DependencyEdgeKind",
    "ImportLocation",
    "DependencyNode",
    "DependencyEdge",
    "DependencyGraph",
    # Resolver
    "PythonResolver",
    # Builder
    "DependencyGraphBuilder",
    "build_dependency_graph",
    # Analyzer
    "DependencyAnalyzer",
    # Monorepo
    "MonorepoDetector",
    "WorkspaceType",
    "WorkspacePackage",
    "WorkspaceBoundary",
    "PackageVisibility",
    "validate_workspace_imports",
]
