"""
Cost Controller

Manages summarization budget and prioritizes nodes.
"""

from pydantic import BaseModel

from src.contexts.repo_structure.infrastructure.models import RepoMapNode


class SummaryCostConfig(BaseModel):
    """Configuration for summary cost control."""

    max_tokens_per_snapshot: int = 100_000
    """Maximum total tokens for all summaries in a snapshot"""

    max_tokens_per_summary: int = 500
    """Maximum tokens for a single summary"""

    min_importance_threshold: float = 0.3
    """Minimum importance score to consider for summarization"""

    estimate_input_tokens_per_loc: int = 4
    """Estimated input tokens per line of code"""

    estimate_output_tokens: int = 150
    """Estimated output tokens per summary (conservative)"""


class CostController:
    """
    Controls summarization cost and prioritizes nodes.

    Selects nodes to summarize based on:
    1. Importance threshold
    2. Priority order (importance desc)
    3. Token budget
    """

    def __init__(self, config: SummaryCostConfig | None = None):
        self.config = config or SummaryCostConfig()
        self._used_tokens = 0

    def select_nodes_to_summarize(self, nodes: list[RepoMapNode], cached_hashes: set[str]) -> list[RepoMapNode]:
        """
        Select nodes to summarize within budget.

        Args:
            nodes: All RepoMap nodes
            cached_hashes: Set of content_hashes already cached

        Returns:
            List of nodes to summarize, sorted by importance desc
        """
        # Filter: importance threshold + not cached
        candidates = [
            n
            for n in nodes
            if n.metrics.importance >= self.config.min_importance_threshold
            and n.chunk_ids  # Has chunk references
            and (not n.chunk_ids or not any(cid in cached_hashes for cid in n.chunk_ids))
        ]

        # Sort by importance descending
        candidates.sort(key=lambda n: n.metrics.importance, reverse=True)

        # Select within budget
        selected = []
        self._used_tokens = 0

        for node in candidates:
            cost = self.estimate_node_cost(node)

            if self._used_tokens + cost > self.config.max_tokens_per_snapshot:
                break

            selected.append(node)
            self._used_tokens += cost

        return selected

    def estimate_node_cost(self, node: RepoMapNode) -> int:
        """
        Estimate total tokens (input + output) for a node.

        Args:
            node: RepoMap node

        Returns:
            Estimated total tokens
        """
        # Input tokens ~ LOC * tokens_per_loc
        input_tokens = node.metrics.loc * self.config.estimate_input_tokens_per_loc

        # Cap input at reasonable size (e.g., 2000 tokens = ~500 LOC)
        input_tokens = min(input_tokens, 2000)

        # Output tokens (conservative estimate)
        output_tokens = self.config.estimate_output_tokens

        return input_tokens + output_tokens

    def get_used_tokens(self) -> int:
        """Get total tokens used."""
        return self._used_tokens

    def get_remaining_budget(self) -> int:
        """Get remaining token budget."""
        return max(0, self.config.max_tokens_per_snapshot - self._used_tokens)
