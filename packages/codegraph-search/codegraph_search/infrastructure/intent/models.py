"""
Intent Analysis Models

Defines query intent types and their structures for the Retriever Layer.
"""

from dataclasses import dataclass, field
from enum import Enum


class IntentKind(str, Enum):
    """Query intent types for code search."""

    CODE_SEARCH = "code_search"  # Find specific code implementation
    SYMBOL_NAV = "symbol_nav"  # Navigate to definition/references of a symbol
    CONCEPT_SEARCH = "concept_search"  # Understand high-level concepts or architecture
    FLOW_TRACE = "flow_trace"  # Trace execution flow or call chains
    REPO_OVERVIEW = "repo_overview"  # Get repository structure or entry points
    DOC_SEARCH = "doc_search"  # Search documentation and docstrings (P0-1)


@dataclass
class QueryIntent:
    """
    Query intent analysis result.

    Attributes:
        kind: Primary intent type
        symbol_names: Extracted symbol names from query
        file_paths: File path hints from query
        module_paths: Module/package path hints
        is_nl: Whether query is primarily natural language
        has_symbol: Whether query contains symbol references
        has_path_hint: Whether query contains path hints
        confidence: Confidence score (0.0-1.0) for LLM-based classification
        raw_query: Original query string
    """

    kind: IntentKind
    symbol_names: list[str] = field(default_factory=list)
    file_paths: list[str] = field(default_factory=list)
    module_paths: list[str] = field(default_factory=list)
    is_nl: bool = True
    has_symbol: bool = False
    has_path_hint: bool = False
    confidence: float = 0.0
    raw_query: str = ""

    def __post_init__(self):
        """Validate and normalize intent data."""
        self.has_symbol = len(self.symbol_names) > 0
        self.has_path_hint = len(self.file_paths) > 0 or len(self.module_paths) > 0

        # Natural language heuristic: no symbols or paths → likely NL
        if not self.has_symbol and not self.has_path_hint:
            self.is_nl = True


@dataclass
class IntentClassificationResult:
    """
    Result of intent classification including metadata.

    Attributes:
        intent: The classified intent
        method: Classification method used ("llm" or "rule")
        latency_ms: Time taken for classification
        fallback_reason: Reason for fallback to rule-based (if applicable)
    """

    intent: QueryIntent
    method: str  # "llm" or "rule"
    latency_ms: float
    fallback_reason: str | None = None
