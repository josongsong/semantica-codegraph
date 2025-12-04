"""
Context Builder

Builds LLM context from search results with token packing and trimming.
"""

from typing import TYPE_CHECKING, Protocol

from src.contexts.retrieval_search.infrastructure.context_builder.dedup import Deduplicator
from src.contexts.retrieval_search.infrastructure.context_builder.models import ContextChunk, ContextResult
from src.contexts.retrieval_search.infrastructure.context_builder.trimming import ChunkTrimmer

if TYPE_CHECKING:
    from src.contexts.retrieval_search.infrastructure.fusion.engine import FusedHit
from src.common.observability import get_logger

logger = get_logger(__name__)


class ChunkStorePort(Protocol):
    """Protocol for chunk storage access (async)."""

    async def get_chunk(self, chunk_id: str) -> dict | None:
        """
        Get chunk by ID.

        Returns dict with:
        - content: chunk content
        - file_path: file path
        - start_line: start line
        - end_line: end line
        - summary_text: pre-generated summary (for offline summarization)
        - metadata: additional metadata
        """
        ...

    async def get_chunks_batch(self, chunk_ids: list[str]) -> dict[str, dict]:
        """
        Get multiple chunks by IDs in a single operation (N+1 방지).

        Args:
            chunk_ids: List of chunk IDs to fetch

        Returns:
            Dict mapping chunk_id to chunk dict (same format as get_chunk)
        """
        ...


class TokenCounter(Protocol):
    """Protocol for token counting."""

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        ...


class SimpleTokenCounter:
    """
    Token counter using tiktoken for accurate counting.

    Falls back to character-based estimation if tiktoken is not available.
    """

    def __init__(self, model: str = "gpt-4"):
        """
        Initialize token counter.

        Args:
            model: Model name for tiktoken encoding (default: gpt-4)
        """
        self.encoding = None
        try:
            import tiktoken

            self.encoding = tiktoken.encoding_for_model(model)
            logger.debug(f"Using tiktoken encoding for {model}")
        except ImportError:
            logger.warning("tiktoken not available, using character-based estimation")
        except Exception as e:
            logger.warning(f"Failed to load tiktoken encoding: {e}, using character-based estimation")

    def count_tokens(self, text: str) -> int:
        """
        Count tokens accurately using tiktoken.

        Falls back to estimation (1 token ≈ 4 chars) if tiktoken unavailable.
        """
        if self.encoding:
            try:
                return len(self.encoding.encode(text))
            except Exception as e:
                logger.warning(f"tiktoken encoding failed: {e}, using estimation")

        # Fallback: ~0.75 tokens per word (average English text)
        # More accurate than simple char/4 which underestimates CJK and overestimates code
        words = len(text.split())
        return max(1, int(words * 0.75)) if words else len(text) // 3


class ContextBuilder:
    """
    Builds LLM context from fused search results.

    Process:
    1. Deduplicate overlapping chunks
    2. Sort by priority_score
    3. Pack chunks into token budget (trim if needed)
    4. Generate ContextChunks with metadata
    """

    def __init__(
        self,
        chunk_store: ChunkStorePort,
        token_counter: TokenCounter | None = None,
        enable_trimming: bool = True,
        enable_dedup: bool = True,
    ):
        """
        Initialize context builder.

        Args:
            chunk_store: Chunk storage port
            token_counter: Token counter (default: simple estimator)
            enable_trimming: Enable chunk trimming
            enable_dedup: Enable deduplication
        """
        self.chunk_store = chunk_store
        self.token_counter = token_counter or SimpleTokenCounter()

        self.deduplicator = Deduplicator() if enable_dedup else None
        self.trimmer = ChunkTrimmer() if enable_trimming else None

    async def build(
        self,
        fused_hits: "list[FusedHit]",
        token_budget: int = 4000,
    ) -> ContextResult:
        """
        Build context from fused hits.

        Args:
            fused_hits: List of fused hits (sorted by priority_score)
            token_budget: Maximum tokens for context

        Returns:
            ContextResult with selected chunks
        """
        # Step 1: Deduplicate
        if self.deduplicator:
            deduplicated = self.deduplicator.deduplicate(fused_hits)
        else:
            deduplicated = fused_hits

        # Step 2: Fetch all chunks in batch (N+1 방지)
        chunk_ids = [hit.chunk_id for hit in deduplicated]
        chunks_dict = await self.chunk_store.get_chunks_batch(chunk_ids)

        # Step 3: Token packing
        context_chunks = []
        total_tokens = 0
        num_trimmed = 0
        num_dropped = 0

        for rank, hit in enumerate(deduplicated, start=1):
            # Get chunk from batch result
            chunk_data = chunks_dict.get(hit.chunk_id)

            if not chunk_data:
                logger.warning(f"Chunk not found in store: {hit.chunk_id}")
                num_dropped += 1
                continue

            content = chunk_data.get("content", "")
            if not content:
                # Try to use summary if no content
                content = chunk_data.get("summary_text", "")

            if not content:
                logger.warning(f"No content for chunk: {hit.chunk_id}")
                num_dropped += 1
                continue

            # Count tokens
            original_tokens = self.token_counter.count_tokens(content)

            # Check if trimming needed
            is_trimmed = False
            trim_reason = "no_trim"

            if self.trimmer and original_tokens > self.trimmer.max_trimmed_tokens:
                content, final_tokens, trim_reason = self.trimmer.trim(content, original_tokens)
                is_trimmed = True
                num_trimmed += 1
            else:
                final_tokens = original_tokens

            # Check if fits in budget
            if total_tokens + final_tokens > token_budget:
                # Try to trim if not already trimmed
                if not is_trimmed and self.trimmer:
                    content, final_tokens, trim_reason = self.trimmer.trim(content, original_tokens)
                    is_trimmed = True
                    num_trimmed += 1

                # Still doesn't fit → drop
                if total_tokens + final_tokens > token_budget:
                    logger.debug(
                        f"Dropping chunk (over budget): {hit.chunk_id} ({final_tokens} tokens would exceed budget)"
                    )
                    num_dropped += 1
                    continue

            # Add to context
            context_chunk = ContextChunk(
                chunk_id=hit.chunk_id,
                content=content,
                file_path=chunk_data.get("file_path", ""),
                start_line=chunk_data.get("start_line", 0),
                end_line=chunk_data.get("end_line", 0),
                rank=rank,
                reason=trim_reason if is_trimmed else f"source:{hit.primary_source}",
                source=hit.primary_source,
                priority_score=hit.priority_score,
                is_trimmed=is_trimmed,
                original_tokens=original_tokens,
                final_tokens=final_tokens,
                metadata={
                    **chunk_data.get("metadata", {}),
                    "fused_score": hit.fused_score,
                    "sources": hit.sources,
                },
            )

            context_chunks.append(context_chunk)
            total_tokens += final_tokens

            # Check if budget exhausted
            if total_tokens >= token_budget * 0.95:  # 95% threshold
                logger.info(f"Token budget nearly exhausted, stopping at rank {rank}")
                break

        result = ContextResult(
            chunks=context_chunks,
            total_tokens=total_tokens,
            token_budget=token_budget,
            num_trimmed=num_trimmed,
            num_dropped=num_dropped,
            metadata={
                "token_utilization": total_tokens / token_budget if token_budget > 0 else 0,
                "avg_priority_score": (
                    sum(c.priority_score for c in context_chunks) / len(context_chunks) if context_chunks else 0
                ),
            },
        )

        logger.info(
            f"Context built: {len(context_chunks)} chunks, "
            f"{total_tokens}/{token_budget} tokens ({result.token_utilization:.1%}), "
            f"trimmed={num_trimmed}, dropped={num_dropped}"
        )

        return result
