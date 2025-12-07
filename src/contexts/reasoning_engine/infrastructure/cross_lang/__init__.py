"""
Cross-Language Value Flow Analysis

SOTA 기능:
- End-to-end value tracking (FE → BE → DB)
- OpenAPI/Protobuf/GraphQL boundary modeling
- Taint analysis for PII/security
- MSA debugging
- Smart boundary matching (85%+ accuracy)
- Type system with inference
- INTEGRATED with ReasoningPipeline
"""

from .boundary_analyzer import (
    BoundaryAnalyzer,
    GraphQLBoundaryExtractor,
    OpenAPIBoundaryExtractor,
    ProtobufBoundaryExtractor,
)
from .boundary_matcher import BoundaryCodeMatcher, MatchCandidate
from .type_system import BaseType, TypeCompatibilityChecker, TypeInference, TypeInfo
from .value_flow_builder import ValueFlowBuilder
from .value_flow_graph import (
    BoundarySpec,
    Confidence,
    FlowEdgeKind,
    ValueFlowEdge,
    ValueFlowGraph,
    ValueFlowNode,
)

__all__ = [
    # Graph
    "ValueFlowGraph",
    "ValueFlowNode",
    "ValueFlowEdge",
    "FlowEdgeKind",
    "BoundarySpec",
    "Confidence",
    # Analyzers
    "BoundaryAnalyzer",
    "OpenAPIBoundaryExtractor",
    "ProtobufBoundaryExtractor",
    "GraphQLBoundaryExtractor",
    # Boundary Matching (SOTA)
    "BoundaryCodeMatcher",
    "MatchCandidate",
    # Type System (SOTA)
    "BaseType",
    "TypeInfo",
    "TypeInference",
    "TypeCompatibilityChecker",
    # Builder (INTEGRATION)
    "ValueFlowBuilder",
]
