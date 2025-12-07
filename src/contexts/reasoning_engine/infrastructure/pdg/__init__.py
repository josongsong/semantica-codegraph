"""
Program Dependence Graph (PDG) Infrastructure

PDG = Control Dependency + Data Dependency
"""

from .control_dependency import ControlDependencyAnalyzer
from .data_dependency import DataDependencyAnalyzer
from .pdg_builder import DependencyType, PDGBuilder, PDGEdge, PDGNode

__all__ = [
    "PDGBuilder",
    "PDGNode",
    "PDGEdge",
    "DependencyType",
    "ControlDependencyAnalyzer",
    "DataDependencyAnalyzer",
]
