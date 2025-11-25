"""
Code Search Tool

Searches code using Semantica's multi-index system.

Features:
- Hybrid search (lexical + vector + symbol)
- Semantic search (vector embeddings)
- Lexical search (exact/fuzzy text matching)
- Symbol search (function/class names)

Integrates with IndexingService for powerful multi-index search.
"""

import logging

from src.agent.schemas import CodeSearchInput, CodeSearchOutput, SearchResult
from src.agent.tools.base import BaseTool
from src.index.service import IndexingService

logger = logging.getLogger(__name__)


class CodeSearchTool(BaseTool[CodeSearchInput, CodeSearchOutput]):
    """
    Search code using Semantica's multi-index system.

    Supports multiple search types:
    - hybrid: Combines lexical, vector, and symbol search (default)
    - semantic: Vector-based semantic similarity
    - lexical: Text-based exact/fuzzy matching
    - symbol: Search by function/class names

    Example:
        tool = CodeSearchTool(indexing_service=container.indexing_service)

        # Semantic search
        result = await tool.execute(CodeSearchInput(
            query="function that validates user input",
            search_type="semantic",
            limit=10
        ))

        # Lexical search with scope
        result = await tool.execute(CodeSearchInput(
            query="def authenticate",
            search_type="lexical",
            scope="src/auth/"
        ))
    """

    name = "code_search"
    description = (
        "Search code in the repository using natural language or code patterns. "
        "Supports semantic, lexical, and symbol-based search. "
        "Returns ranked results with file paths, line numbers, and code snippets."
    )
    input_schema = CodeSearchInput
    output_schema = CodeSearchOutput

    def __init__(
        self,
        indexing_service: IndexingService,
        repo_id: str = "current",
        snapshot_id: str = "main",
    ):
        """
        Initialize code search tool.

        Args:
            indexing_service: Semantica indexing service
            repo_id: Repository ID to search in
            snapshot_id: Snapshot ID to search in
        """
        super().__init__()
        self.indexing_service = indexing_service
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id

    async def _execute(self, input_data: CodeSearchInput) -> CodeSearchOutput:
        """
        Execute code search.

        Args:
            input_data: Search query and parameters

        Returns:
            Search results with file paths, line numbers, and snippets
        """
        try:
            # Determine search weights based on search_type
            if input_data.search_type == "hybrid":
                weights = {"lexical": 0.3, "vector": 0.4, "symbol": 0.3}
            elif input_data.search_type == "semantic":
                weights = {"vector": 1.0}
            elif input_data.search_type == "lexical":
                weights = {"lexical": 1.0}
            elif input_data.search_type == "symbol":
                weights = {"symbol": 1.0}
            else:
                weights = {"lexical": 0.3, "vector": 0.4, "symbol": 0.3}

            # Execute search using IndexingService
            search_hits = await self.indexing_service.search(
                repo_id=self.repo_id,
                snapshot_id=self.snapshot_id,
                query=input_data.query,
                weights=weights,
                limit=input_data.limit,
            )

            # Convert SearchHits to SearchResults
            results = []
            for hit in search_hits:
                # Get chunk metadata
                metadata = hit.metadata or {}

                # Extract snippet from chunk (TODO: actual chunk content retrieval)
                snippet = self._generate_snippet(hit, input_data.query)

                result = SearchResult(
                    file_path=hit.file_path,
                    symbol_name=metadata.get("symbol_name"),
                    start_line=metadata.get("start_line", 1),
                    end_line=metadata.get("end_line", 1),
                    score=hit.score,
                    snippet=snippet,
                    context=metadata.get("docstring") or metadata.get("signature"),
                )
                results.append(result)

            return CodeSearchOutput(
                success=True,
                results=results,
                total_found=len(results),
            )

        except Exception as e:
            logger.error(f"Code search failed: {e}", exc_info=True)
            return CodeSearchOutput(
                success=False,
                results=[],
                total_found=0,
                error=str(e),
            )

    def _generate_snippet(self, hit, query: str) -> str:
        """
        Generate code snippet from search hit.

        Args:
            hit: Search hit with metadata
            query: Search query

        Returns:
            Code snippet string
        """
        # TODO: Retrieve actual chunk content from chunk store
        # For now, generate placeholder snippet
        metadata = hit.metadata or {}
        symbol_name = metadata.get("symbol_name", "code")
        return f"# {symbol_name} (matched: '{query[:50]}')\n# See {hit.file_path}"

    def _apply_scope_filter(self, results: list[SearchResult], scope: str | None) -> list[SearchResult]:
        """
        Filter results by scope (file path or directory).

        Args:
            results: Search results to filter
            scope: Scope filter (e.g., "src/auth/", "utils.py")

        Returns:
            Filtered results
        """
        if not scope:
            return results

        filtered = []
        for result in results:
            # Check if file path matches scope
            if scope in result.file_path or result.file_path.startswith(scope):
                filtered.append(result)

        return filtered
