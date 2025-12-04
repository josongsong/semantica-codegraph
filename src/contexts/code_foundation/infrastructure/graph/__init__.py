"""
Graph Construction Layer

Unified graph representation for code analysis.
Converts Structural IR + Semantic IR into GraphDocument.

Components:
- models: GraphDocument, GraphNode, GraphEdge, GraphIndex
- builder: GraphBuilder (AST → Graph)
- impact_analyzer: 심볼 수준 영향도 분석
- edge_validator: Cross-file edge stale marking / lazy validation
- edge_attrs: EdgeKind별 타입 안전 속성 스키마
"""

from typing import TYPE_CHECKING

from src.contexts.code_foundation.infrastructure.graph.models import (
    GraphDocument,
    GraphEdge,
    GraphEdgeKind,
    GraphIndex,
    GraphNode,
    GraphNodeKind,
)

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.graph.builder import GraphBuilder
    from src.contexts.code_foundation.infrastructure.graph.edge_attrs import (
        CallsEdgeAttrs,
        EdgeAttrsBase,
        ImportsEdgeAttrs,
        InheritsEdgeAttrs,
        create_edge_attrs,
        parse_edge_attrs,
    )
    from src.contexts.code_foundation.infrastructure.graph.edge_validator import (
        EdgeStatus,
        EdgeValidator,
        StaleEdgeInfo,
    )
    from src.contexts.code_foundation.infrastructure.graph.impact_analyzer import (
        ChangeType,
        GraphImpactAnalyzer,
        ImpactResult,
        SymbolChange,
        detect_symbol_changes,
    )


def __getattr__(name: str):
    """Lazy import for heavy builder/analyzer classes."""
    if name == "GraphBuilder":
        from src.contexts.code_foundation.infrastructure.graph.builder import GraphBuilder

        return GraphBuilder

    # Impact Analyzer
    if name == "GraphImpactAnalyzer":
        from src.contexts.code_foundation.infrastructure.graph.impact_analyzer import GraphImpactAnalyzer

        return GraphImpactAnalyzer
    if name == "ImpactResult":
        from src.contexts.code_foundation.infrastructure.graph.impact_analyzer import ImpactResult

        return ImpactResult
    if name == "SymbolChange":
        from src.contexts.code_foundation.infrastructure.graph.impact_analyzer import SymbolChange

        return SymbolChange
    if name == "ChangeType":
        from src.contexts.code_foundation.infrastructure.graph.impact_analyzer import ChangeType

        return ChangeType
    if name == "detect_symbol_changes":
        from src.contexts.code_foundation.infrastructure.graph.impact_analyzer import detect_symbol_changes

        return detect_symbol_changes

    # Edge Validator
    if name == "EdgeValidator":
        from src.contexts.code_foundation.infrastructure.graph.edge_validator import EdgeValidator

        return EdgeValidator
    if name == "EdgeStatus":
        from src.contexts.code_foundation.infrastructure.graph.edge_validator import EdgeStatus

        return EdgeStatus
    if name == "StaleEdgeInfo":
        from src.contexts.code_foundation.infrastructure.graph.edge_validator import StaleEdgeInfo

        return StaleEdgeInfo

    # Edge Attrs
    if name == "EdgeAttrsBase":
        from src.contexts.code_foundation.infrastructure.graph.edge_attrs import EdgeAttrsBase

        return EdgeAttrsBase
    if name == "CallsEdgeAttrs":
        from src.contexts.code_foundation.infrastructure.graph.edge_attrs import CallsEdgeAttrs

        return CallsEdgeAttrs
    if name == "ImportsEdgeAttrs":
        from src.contexts.code_foundation.infrastructure.graph.edge_attrs import ImportsEdgeAttrs

        return ImportsEdgeAttrs
    if name == "InheritsEdgeAttrs":
        from src.contexts.code_foundation.infrastructure.graph.edge_attrs import InheritsEdgeAttrs

        return InheritsEdgeAttrs
    if name == "create_edge_attrs":
        from src.contexts.code_foundation.infrastructure.graph.edge_attrs import create_edge_attrs

        return create_edge_attrs
    if name == "parse_edge_attrs":
        from src.contexts.code_foundation.infrastructure.graph.edge_attrs import parse_edge_attrs

        return parse_edge_attrs

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Builder (heavy - lazy import)
    "GraphBuilder",
    # Models (lightweight)
    "GraphNode",
    "GraphNodeKind",
    "GraphEdge",
    "GraphEdgeKind",
    "GraphIndex",
    "GraphDocument",
    # Impact Analyzer (lazy import)
    "GraphImpactAnalyzer",
    "ImpactResult",
    "SymbolChange",
    "ChangeType",
    "detect_symbol_changes",
    # Edge Validator (lazy import)
    "EdgeValidator",
    "EdgeStatus",
    "StaleEdgeInfo",
    # Edge Attrs (lazy import)
    "EdgeAttrsBase",
    "CallsEdgeAttrs",
    "ImportsEdgeAttrs",
    "InheritsEdgeAttrs",
    "create_edge_attrs",
    "parse_edge_attrs",
]
