"""
Context Builder Models

Models for LLM context construction.
"""

from dataclasses import dataclass, field


@dataclass
class ContextChunk:
    """
    A chunk selected for LLM context.

    Attributes:
        chunk_id: Chunk identifier
        content: Chunk content (may be trimmed)
        file_path: File path
        start_line: Start line number
        end_line: End line number
        rank: Rank in final context (1-based)
        reason: Reason for inclusion
        source: Primary source index
        priority_score: Priority score used for ranking
        is_trimmed: Whether content was trimmed
        original_tokens: Original token count (before trimming)
        final_tokens: Final token count (after trimming)
        metadata: Additional metadata
    """

    chunk_id: str
    content: str
    file_path: str
    start_line: int
    end_line: int
    rank: int
    reason: str
    source: str
    priority_score: float
    is_trimmed: bool = False
    original_tokens: int = 0
    final_tokens: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class ContextResult:
    """
    Complete context construction result.

    Attributes:
        chunks: Ordered list of context chunks
        total_tokens: Total token count
        token_budget: Token budget used
        num_trimmed: Number of trimmed chunks
        num_dropped: Number of dropped chunks (over budget)
        metadata: Additional metadata
    """

    chunks: list[ContextChunk]
    total_tokens: int
    token_budget: int
    num_trimmed: int = 0
    num_dropped: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def token_utilization(self) -> float:
        """Token budget utilization (0-1)."""
        if self.token_budget == 0:
            return 0.0
        return self.total_tokens / self.token_budget

    @property
    def chunk_count(self) -> int:
        """Number of chunks in context."""
        return len(self.chunks)
