"""
Code-Specific Reranking Models

Models for AST-based and call graph-based reranking.
"""

from dataclasses import dataclass, field
from enum import Enum


class StructuralFeature(str, Enum):
    """Types of structural features to consider."""

    FUNCTION_SIGNATURE = "function_signature"
    CLASS_HIERARCHY = "class_hierarchy"
    CONTROL_FLOW = "control_flow"
    VARIABLE_USAGE = "variable_usage"
    IMPORT_PATTERN = "import_pattern"
    DECORATOR_PATTERN = "decorator_pattern"


@dataclass
class ASTSimilarity:
    """
    Structural similarity between two code snippets.

    Attributes:
        overall_score: Overall structural similarity (0-1)
        feature_scores: Scores for individual structural features
        matched_patterns: Patterns that matched
        explanation: Human-readable explanation
    """

    overall_score: float
    feature_scores: dict[StructuralFeature, float] = field(default_factory=dict)
    matched_patterns: list[str] = field(default_factory=list)
    explanation: str = ""


@dataclass
class CallGraphProximity:
    """
    Proximity in the call graph.

    Attributes:
        distance: Distance in call graph (number of hops)
        path: Path through call graph (list of function names)
        relationship: Type of relationship (caller, callee, sibling, etc.)
        score: Proximity score (0-1, higher = closer)
    """

    distance: int
    path: list[str] = field(default_factory=list)
    relationship: str = "unknown"
    score: float = 0.0


@dataclass
class CodeRerankedChunk:
    """
    Chunk with code-specific reranking applied.

    Attributes:
        chunk_id: Chunk identifier
        original_score: Original score before code reranking
        structural_score: AST-based structural similarity score
        proximity_score: Call graph proximity score
        final_score: Final score after code-specific reranking
        ast_similarity: AST similarity details
        cg_proximity: Call graph proximity details
        metadata: Additional metadata
    """

    chunk_id: str
    original_score: float
    structural_score: float = 0.0
    proximity_score: float = 0.0
    final_score: float = 0.0
    ast_similarity: ASTSimilarity | None = None
    cg_proximity: CallGraphProximity | None = None
    metadata: dict = field(default_factory=dict)
