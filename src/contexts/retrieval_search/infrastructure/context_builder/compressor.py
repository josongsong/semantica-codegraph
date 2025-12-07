"""
Contextual Compression

Compresses retrieved context while preserving key information.

References:
- LLMLingua (Jiang et al., 2023)
- https://arxiv.org/abs/2310.05736
- Selective Context (Li et al., 2023)

Key Insight:
Not all tokens in retrieved docs are equally important.
Compress by removing redundant/irrelevant content while keeping:
- Key entities (functions, classes, variables)
- Core logic
- Critical comments
"""

from typing import Any, Protocol

from src.common.observability import get_logger

logger = get_logger(__name__)


class LLMPort(Protocol):
    """LLM interface for compression."""

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text from prompt."""
        ...


COMPRESSION_PROMPT = """You are compressing code/documentation while preserving essential information.

Original Query: "{query}"

Content to compress:
```
{content}
```

Compress this to ~{target_ratio}% of original length while keeping:
- Function/class names and signatures
- Key logic and control flow
- Important comments
- Variables and data structures

Remove:
- Redundant code
- Verbose comments
- Boilerplate
- Unnecessary whitespace

Compressed output:"""


SELECTIVE_PROMPT = """You are extracting the most relevant parts of code for this query.

Query: "{query}"

Full Content:
```
{content}
```

Extract only the parts that directly help answer the query. Include:
- Relevant function/method signatures
- Key logic related to the query
- Important variables/parameters

Omit everything else.

Extracted content:"""


class ContextualCompressor:
    """
    Compresses retrieved context using LLM.

    Features:
    - Query-aware compression (preserve query-relevant info)
    - Configurable compression ratio
    - Entity preservation (functions, classes)
    - Fallback to truncation on failure
    """

    def __init__(
        self,
        llm: LLMPort,
        compression_method: str = "llm",  # llm|selective|simple
        target_ratio: float = 0.4,  # Compress to 40%
        temperature: float = 0.0,
        max_input_tokens: int = 4000,
    ):
        """
        Initialize contextual compressor.

        Args:
            llm: LLM for compression
            compression_method: Method (llm/selective/simple)
            target_ratio: Target compression ratio (0.0-1.0)
            temperature: Generation temperature
            max_input_tokens: Max tokens to compress at once
        """
        self.llm = llm
        self.method = compression_method
        self.target_ratio = max(0.1, min(1.0, target_ratio))
        self.temperature = temperature
        self.max_input_tokens = max_input_tokens

    async def compress_content(
        self,
        content: str,
        query: str = "",
    ) -> str:
        """
        Compress content while preserving query-relevant information.

        Args:
            content: Content to compress
            query: User query (for query-aware compression)

        Returns:
            Compressed content
        """
        if not content:
            return content

        # Check if compression needed
        content_len = len(content)
        target_len = int(content_len * self.target_ratio)

        if content_len <= target_len:
            # Already short enough
            return content

        if self.method == "llm":
            return await self._llm_compression(content, query, target_len)
        elif self.method == "selective":
            return await self._selective_extraction(content, query)
        elif self.method == "simple":
            return self._simple_truncation(content, target_len)
        else:
            logger.warning(f"Unknown compression method: {self.method}, using simple")
            return self._simple_truncation(content, target_len)

    async def _llm_compression(
        self,
        content: str,
        query: str,
        target_len: int,
    ) -> str:
        """
        LLM-based compression.

        Args:
            content: Content to compress
            query: User query
            target_len: Target length

        Returns:
            Compressed content
        """
        try:
            # Estimate max tokens (rough: 1 token ~= 4 chars)
            content_tokens = len(content) // 4

            if content_tokens > self.max_input_tokens:
                # Content too long, truncate first
                content = content[: self.max_input_tokens * 4]

            prompt = COMPRESSION_PROMPT.format(
                query=query or "N/A",
                content=content,
                target_ratio=int(self.target_ratio * 100),
            )

            compressed = await self.llm.generate(
                prompt,
                temperature=self.temperature,
                max_tokens=int(target_len // 4),  # Rough token estimate
            )

            compression_ratio = len(compressed) / len(content)

            logger.info(
                "llm_compression_success",
                original_len=len(content),
                compressed_len=len(compressed),
                ratio=f"{compression_ratio:.2%}",
                target_ratio=f"{self.target_ratio:.2%}",
            )

            return compressed.strip()

        except Exception as e:
            logger.warning(
                "llm_compression_failed",
                error=str(e),
                fallback="simple_truncation",
            )
            return self._simple_truncation(content, target_len)

    async def _selective_extraction(
        self,
        content: str,
        query: str,
    ) -> str:
        """
        Selective extraction of query-relevant parts.

        Args:
            content: Content to extract from
            query: User query

        Returns:
            Extracted relevant content
        """
        try:
            prompt = SELECTIVE_PROMPT.format(
                query=query or "N/A",
                content=content[: self.max_input_tokens * 4],
            )

            extracted = await self.llm.generate(
                prompt,
                temperature=self.temperature,
                max_tokens=2000,
            )

            logger.info(
                "selective_extraction_success",
                original_len=len(content),
                extracted_len=len(extracted),
                ratio=f"{len(extracted) / len(content):.2%}",
            )

            return extracted.strip()

        except Exception as e:
            logger.warning(
                "selective_extraction_failed",
                error=str(e),
                fallback="simple_truncation",
            )
            return self._simple_truncation(content, int(len(content) * self.target_ratio))

    def _simple_truncation(self, content: str, target_len: int) -> str:
        """
        Simple truncation with smart boundary detection.

        Tries to truncate at:
        1. End of function/class
        2. End of line
        3. Word boundary

        Args:
            content: Content to truncate
            target_len: Target length

        Returns:
            Truncated content
        """
        if len(content) <= target_len:
            return content

        # Try to find good truncation point near target
        search_window = min(200, target_len // 10)
        search_start = max(0, target_len - search_window)
        search_end = min(len(content), target_len + search_window)

        snippet = content[search_start:search_end]

        # Look for function/class end markers
        markers = ["\n}\n", "\n\n", "}\n", "\n"]

        for marker in markers:
            pos = snippet.rfind(marker)
            if pos != -1:
                actual_pos = search_start + pos + len(marker)
                truncated = content[:actual_pos]

                logger.info(
                    "simple_truncation",
                    original_len=len(content),
                    truncated_len=len(truncated),
                    ratio=f"{len(truncated) / len(content):.2%}",
                    marker=marker.replace("\n", "\\n"),
                )

                return truncated

        # Fallback: hard truncate
        truncated = content[:target_len]
        logger.info(
            "simple_truncation_hard",
            original_len=len(content),
            truncated_len=target_len,
        )

        return truncated


class BatchCompressor:
    """
    Compresses multiple chunks efficiently.

    Features:
    - Batch processing
    - Per-chunk compression
    - Token budget management
    """

    def __init__(
        self,
        compressor: ContextualCompressor,
        total_token_budget: int = 8000,
    ):
        """
        Initialize batch compressor.

        Args:
            compressor: Contextual compressor instance
            total_token_budget: Total token budget for all chunks
        """
        self.compressor = compressor
        self.token_budget = total_token_budget

    async def compress_chunks(
        self,
        chunks: list[dict[str, Any]],
        query: str = "",
    ) -> list[dict[str, Any]]:
        """
        Compress multiple chunks within token budget.

        Args:
            chunks: List of chunk dicts with 'content' key
            query: User query

        Returns:
            Compressed chunks
        """
        if not chunks:
            return chunks

        # Calculate current total length
        total_len = sum(len(chunk.get("content", "")) for chunk in chunks)

        # Rough token estimate (1 token ~= 4 chars)
        total_tokens = total_len // 4

        if total_tokens <= self.token_budget:
            # Within budget, no compression needed
            logger.info(
                "batch_compression_skip",
                total_tokens=total_tokens,
                budget=self.token_budget,
            )
            return chunks

        # Calculate compression ratio needed
        self.token_budget / total_tokens

        # Compress each chunk
        compressed_chunks = []

        for chunk in chunks:
            content = chunk.get("content", "")

            if content:
                compressed_content = await self.compressor.compress_content(
                    content,
                    query,
                )

                compressed_chunk = {
                    **chunk,
                    "content": compressed_content,
                    "original_length": len(content),
                    "compressed_length": len(compressed_content),
                    "compression_ratio": len(compressed_content) / len(content),
                }
            else:
                compressed_chunk = chunk

            compressed_chunks.append(compressed_chunk)

        # Calculate final stats
        final_total_len = sum(len(c.get("content", "")) for c in compressed_chunks)
        final_tokens = final_total_len // 4

        logger.info(
            "batch_compression_complete",
            num_chunks=len(chunks),
            original_tokens=total_tokens,
            compressed_tokens=final_tokens,
            ratio=f"{final_tokens / total_tokens:.2%}",
            budget=self.token_budget,
            within_budget=final_tokens <= self.token_budget,
        )

        return compressed_chunks


def compress_context(
    chunks: list[dict[str, Any]],
    query: str,
    llm: LLMPort,
    target_ratio: float = 0.4,
    method: str = "llm",
) -> list[dict[str, Any]]:
    """
    Convenience function for context compression.

    Args:
        chunks: List of chunk dicts
        query: User query
        llm: LLM instance
        target_ratio: Target compression ratio
        method: Compression method

    Returns:
        Compressed chunks
    """
    compressor = ContextualCompressor(
        llm=llm,
        compression_method=method,
        target_ratio=target_ratio,
    )

    batch_compressor = BatchCompressor(compressor=compressor)

    # This is async, but provided as sync convenience function
    # In production, use async version
    import asyncio

    return asyncio.run(batch_compressor.compress_chunks(chunks, query))
