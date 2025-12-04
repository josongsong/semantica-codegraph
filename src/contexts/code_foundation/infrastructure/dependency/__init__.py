"""
Dependency Resolution System

Resolves import statements to actual modules, builds dependency graphs,
and analyzes dependencies for circular dependencies, change impact, etc.

Architecture:
- models: Core data models (DependencyNode, DependencyGraph, DependencyEdge)
- python_resolver: Python-specific import resolution
- graph_builder: Constructs dependency graphs from IR
- analyzer: Analyzes dependency graphs (cycles, impact, etc.)
"""

from src.contexts.code_foundation.infrastructure.dependency.analyzer import DependencyAnalyzer
from src.contexts.code_foundation.infrastructure.dependency.graph_builder import (
    DependencyGraphBuilder,
    build_dependency_graph,
)
from src.contexts.code_foundation.infrastructure.dependency.models import (
    DependencyEdge,
    DependencyEdgeKind,
    DependencyGraph,
    DependencyKind,
    DependencyNode,
    ImportLocation,
)
from src.contexts.code_foundation.infrastructure.dependency.python_resolver import PythonResolver

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
]
