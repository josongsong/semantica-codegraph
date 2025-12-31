"""
Test-Time Reasoning Models

Models for o1-style reasoning during retrieval.
"""

from dataclasses import dataclass, field
from enum import Enum


class SearchTool(str, Enum):
    """Available search tools for reasoning."""

    LEXICAL = "lexical"  # Text/regex search
    VECTOR = "vector"  # Semantic search
    SYMBOL = "symbol"  # Symbol navigation
    GRAPH = "graph"  # Call graph traversal


@dataclass
class ReasoningStep:
    """
    A single step in reasoning process.

    Attributes:
        step_num: Step number (1-based)
        thought: LLM's reasoning/thinking
        action: Action to take (search tool + query)
        tool: Search tool to use
        query: Search query
        expected_outcome: What LLM expects to find
    """

    step_num: int
    thought: str
    action: str
    tool: SearchTool
    query: str
    expected_outcome: str = ""


@dataclass
class SearchStrategy:
    """
    Complete search strategy from LLM reasoning.

    Attributes:
        query: Original query
        analysis: LLM's analysis of the query
        steps: Planned reasoning steps
        estimated_difficulty: Query difficulty (1-5)
        trace: Full reasoning trace
    """

    query: str
    analysis: str
    steps: list[ReasoningStep] = field(default_factory=list)
    estimated_difficulty: int = 3
    trace: str = ""


@dataclass
class ReasonedResult:
    """
    Result from reasoning-based retrieval.

    Attributes:
        strategy: Search strategy used
        step_results: Results from each reasoning step
        raw_results: Raw results before refinement
        refined_results: LLM-refined final results
        reasoning_trace: Complete trace of reasoning
        metadata: Additional metadata
    """

    strategy: SearchStrategy
    step_results: list[dict] = field(default_factory=list)
    raw_results: list[dict] = field(default_factory=list)
    refined_results: list[dict] = field(default_factory=list)
    reasoning_trace: str = ""
    metadata: dict = field(default_factory=dict)
