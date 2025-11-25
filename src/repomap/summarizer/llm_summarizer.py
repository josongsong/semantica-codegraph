"""
LLM Summarizer

Generates AI-powered summaries for RepoMap nodes.
"""

import asyncio
from typing import Any

from src.foundation.chunk.models import Chunk
from src.ports import LLMPort
from src.repomap.models import RepoMapNode

from .cache import SummaryCache
from .cost_control import CostController


class SummaryPromptTemplate:
    """
    Prompt templates for different node kinds.

    Uses concise, focused prompts to minimize tokens.
    """

    FUNCTION = """Summarize this function in 1-2 sentences. Focus on purpose and behavior.

Function: {fqn}
Code:
```{language}
{code}
```

Summary:"""

    CLASS = """Summarize this class in 1-2 sentences. Focus on responsibility and key methods.

Class: {fqn}
Code:
```{language}
{code}
```

Summary:"""

    FILE = """Summarize this file in 1-2 sentences. Focus on main purpose and exports.

File: {path}
Code:
```{language}
{code}
```

Summary:"""

    MODULE = """Summarize this module in 1-2 sentences. Focus on main components and purpose.

Module: {fqn}
Contents:
{contents}

Summary:"""

    DEFAULT = """Summarize this code element in 1-2 sentences.

{kind}: {fqn}
Code:
```{language}
{code}
```

Summary:"""

    @classmethod
    def get_template(cls, node_kind: str) -> str:
        """Get prompt template for node kind."""
        templates = {
            "function": cls.FUNCTION,
            "class": cls.CLASS,
            "file": cls.FILE,
            "module": cls.MODULE,
        }
        return templates.get(node_kind, cls.DEFAULT)


class LLMSummarizer:
    """
    Generates LLM-based summaries for RepoMap nodes.

    Features:
    - Async batch processing
    - Content-hash based caching
    - Cost control integration
    - Node kind-specific prompts
    """

    def __init__(
        self,
        llm: LLMPort,
        cache: SummaryCache,
        cost_controller: CostController,
        chunk_store: Any,  # ChunkStore protocol
    ):
        """
        Initialize LLM summarizer.

        Args:
            llm: LLM port for generating summaries
            cache: Summary cache
            cost_controller: Cost controller
            chunk_store: Store to retrieve chunk content
        """
        self.llm = llm
        self.cache = cache
        self.cost_controller = cost_controller
        self.chunk_store = chunk_store

    async def summarize_nodes(self, nodes: list[RepoMapNode], max_concurrent: int = 5) -> dict[str, str]:
        """
        Generate summaries for multiple nodes concurrently.

        Args:
            nodes: RepoMap nodes to summarize
            max_concurrent: Maximum concurrent LLM requests

        Returns:
            Dict mapping node_id to summary
        """
        # Check cache first
        cached_hashes = set()
        summaries = {}

        for node in nodes:
            if node.chunk_ids:
                # Try to get from cache using first chunk's hash
                # (simplified - in production might combine hashes)
                chunk_id = node.chunk_ids[0]
                chunk = self.chunk_store.get_chunk(chunk_id)
                if chunk and chunk.content_hash:
                    cached_summary = self.cache.get(chunk.content_hash)
                    if cached_summary:
                        summaries[node.id] = cached_summary
                        cached_hashes.add(chunk.content_hash)

        # Filter nodes that need summarization
        nodes_to_summarize = [n for n in nodes if n.id not in summaries]

        # Select nodes within budget
        selected_nodes = self.cost_controller.select_nodes_to_summarize(nodes_to_summarize, cached_hashes)

        # Generate summaries with concurrency limit
        semaphore = asyncio.Semaphore(max_concurrent)

        async def summarize_with_limit(node: RepoMapNode) -> tuple[str, str]:
            async with semaphore:
                summary = await self._summarize_node(node)
                return (node.id, summary)

        # Run concurrent summarization
        tasks = [summarize_with_limit(node) for node in selected_nodes]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results
        for result in results:
            if isinstance(result, Exception):
                # Log error but continue
                print(f"Summarization error: {result}")
                continue

            node_id, summary = result
            summaries[node_id] = summary

        return summaries

    async def _summarize_node(self, node: RepoMapNode) -> str:
        """
        Generate summary for a single node.

        Args:
            node: RepoMap node

        Returns:
            Generated summary
        """
        # Get chunk content
        if not node.chunk_ids:
            return ""

        chunk_id = node.chunk_ids[0]  # Use first chunk
        chunk = self.chunk_store.get_chunk(chunk_id)
        if not chunk:
            return ""

        # Build prompt
        prompt = self._build_prompt(node, chunk)

        # Generate summary
        try:
            response = await self.llm.generate(prompt, max_tokens=200, temperature=0.3)
            summary = response.strip()

            # Cache summary
            if chunk.content_hash:
                self.cache.set(chunk.content_hash, summary)

            return summary

        except Exception as e:
            print(f"LLM generation error for {node.id}: {e}")
            return ""

    def _build_prompt(self, node: RepoMapNode, chunk: Chunk) -> str:
        """
        Build prompt for node summarization.

        Args:
            node: RepoMap node
            chunk: Source chunk

        Returns:
            Prompt string
        """
        template = SummaryPromptTemplate.get_template(node.kind)

        # Get code content (simplified - might need source file reader)
        code = f"<content from {chunk.file_path}:{chunk.start_line}-{chunk.end_line}>"

        # For modules/files, might aggregate child info
        contents = f"{len(node.children_ids)} children" if node.children_ids else "Empty"

        return template.format(
            fqn=node.fqn or node.name,
            kind=node.kind,
            path=node.path or "",
            language=chunk.language or "python",
            code=code,
            contents=contents,
        )

    def update_node_summaries(self, nodes: list[RepoMapNode], summaries: dict[str, str]) -> None:
        """
        Update nodes with generated summaries.

        Args:
            nodes: RepoMap nodes
            summaries: Dict mapping node_id to summary
        """
        for node in nodes:
            if node.id in summaries:
                summary_text = summaries[node.id]
                # Update summary_body (2-3 sentences)
                node.summary_body = summary_text
                # Generate simple title from first sentence
                first_sentence = summary_text.split(". ")[0] if ". " in summary_text else summary_text
                node.summary_title = first_sentence[:100]  # Cap at 100 chars
