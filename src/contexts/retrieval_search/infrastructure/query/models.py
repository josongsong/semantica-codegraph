"""
Query Decomposition Models

Models for multi-step query decomposition and execution.
"""

from dataclasses import dataclass, field
from enum import Enum


class QueryType(str, Enum):
    """Type of query based on complexity."""

    SINGLE_HOP = "single_hop"  # Simple query, one retrieval step
    MULTI_HOP = "multi_hop"  # Sequential steps with dependencies
    COMPARATIVE = "comparative"  # Compare multiple entities/approaches
    CAUSAL = "causal"  # Trace cause-effect relationships


@dataclass
class QueryStep:
    """
    A single step in a decomposed query.

    Attributes:
        step_id: Unique step identifier (e.g., "step1", "step2")
        description: What to search for in this step
        query: Actual search query for this step
        dependencies: List of step_ids this step depends on
        expected_output: Expected type of output (e.g., "function", "file", "flow")
    """

    step_id: str
    description: str
    query: str
    dependencies: list[str] = field(default_factory=list)
    expected_output: str = "code"

    def has_dependencies(self) -> bool:
        """Check if this step depends on previous steps."""
        return len(self.dependencies) > 0


@dataclass
class DecomposedQuery:
    """
    Decomposed multi-step query.

    Attributes:
        original_query: Original user query
        query_type: Type of query (single_hop, multi_hop, etc.)
        steps: List of query steps in execution order
        reasoning: LLM's reasoning for decomposition
        metadata: Additional metadata
    """

    original_query: str
    query_type: QueryType
    steps: list[QueryStep]
    reasoning: str = ""
    metadata: dict = field(default_factory=dict)

    def is_multi_hop(self) -> bool:
        """Check if query requires multi-hop retrieval."""
        return self.query_type == QueryType.MULTI_HOP

    def get_step(self, step_id: str) -> QueryStep | None:
        """Get step by ID."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def get_execution_order(self) -> list[QueryStep]:
        """
        Get steps in topologically sorted order (dependencies first).

        Returns:
            List of steps in execution order
        """
        # Simple topological sort
        visited = set()
        result = []

        def visit(step: QueryStep):
            if step.step_id in visited:
                return
            visited.add(step.step_id)

            # Visit dependencies first
            for dep_id in step.dependencies:
                dep_step = self.get_step(dep_id)
                if dep_step:
                    visit(dep_step)

            result.append(step)

        for step in self.steps:
            visit(step)

        return result


@dataclass
class StepResult:
    """
    Result from executing a single query step.

    Attributes:
        step_id: Step identifier
        chunks: Retrieved chunks for this step
        summary: Summary of findings
        key_symbols: Key symbols found (for next steps)
        metadata: Additional metadata
    """

    step_id: str
    chunks: list[dict] = field(default_factory=list)
    summary: str = ""
    key_symbols: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class MultiHopResult:
    """
    Complete result from multi-hop retrieval.

    Attributes:
        decomposed_query: The decomposed query
        step_results: Results from each step
        final_chunks: Final consolidated chunks
        reasoning_chain: Chain of reasoning across steps
        metadata: Additional metadata
    """

    decomposed_query: DecomposedQuery
    step_results: list[StepResult] = field(default_factory=list)
    final_chunks: list[dict] = field(default_factory=list)
    reasoning_chain: str = ""
    metadata: dict = field(default_factory=dict)

    def get_step_result(self, step_id: str) -> StepResult | None:
        """Get result for a specific step."""
        for result in self.step_results:
            if result.step_id == step_id:
                return result
        return None
