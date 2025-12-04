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

from pathlib import Path
from typing import TYPE_CHECKING

from src.contexts.agent_automation.infrastructure.schemas import CodeSearchInput, CodeSearchOutput, SearchResult
from src.contexts.agent_automation.infrastructure.tools.base import BaseTool
from src.contexts.multi_index.infrastructure.service import IndexingService

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.chunk.store import ChunkStore
from src.common.observability import get_logger

logger = get_logger(__name__)


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
        chunk_store: "ChunkStore | None" = None,
        repo_root: str | None = None,
    ):
        """
        Initialize code search tool.

        Args:
            indexing_service: Semantica indexing service
            repo_id: Repository ID to search in
            snapshot_id: Snapshot ID to search in
            chunk_store: Optional ChunkStore for retrieving chunk content
            repo_root: Optional repository root path for file reading
        """
        super().__init__()
        self.indexing_service = indexing_service
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id
        self.chunk_store = chunk_store
        self.repo_root = Path(repo_root) if repo_root else None

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

            # Convert SearchHits to SearchResults with actual content
            results = []
            for hit in search_hits:
                # Get chunk metadata
                metadata = hit.metadata or {}

                # Extract actual code snippet
                snippet = await self._get_snippet(hit, input_data.query)

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

    async def _get_snippet(self, hit, query: str) -> str:
        """
        Get actual code snippet from chunk or file.

        Retrieval strategy (priority order):
        1. ChunkStore: Get chunk by ID and read content from file using span
        2. Direct file read: Read from repo_root using metadata line numbers
        3. Fallback: Generate placeholder snippet

        Args:
            hit: Search hit with chunk_id, file_path, metadata
            query: Search query (for fallback)

        Returns:
            Code snippet string
        """
        metadata = hit.metadata or {}
        start_line = metadata.get("start_line")
        end_line = metadata.get("end_line")

        # Strategy 1: Try ChunkStore
        if self.chunk_store and hit.chunk_id:
            try:
                chunk = await self.chunk_store.get_chunk(hit.chunk_id)
                if chunk and chunk.file_path:
                    start_line = chunk.start_line or start_line
                    end_line = chunk.end_line or end_line
                    # Try to read actual content from file
                    snippet = await self._read_file_lines(chunk.file_path, start_line, end_line)
                    if snippet:
                        return snippet
            except Exception as e:
                logger.debug(f"ChunkStore retrieval failed for {hit.chunk_id}: {e}")

        # Strategy 2: Direct file read
        if self.repo_root and hit.file_path and start_line and end_line:
            try:
                snippet = await self._read_file_lines(hit.file_path, start_line, end_line)
                if snippet:
                    return snippet
            except Exception as e:
                logger.debug(f"Direct file read failed for {hit.file_path}: {e}")

        # Strategy 3: Fallback placeholder
        return self._generate_placeholder_snippet(hit, query, start_line, end_line)

    async def _read_file_lines(self, file_path: str, start_line: int | None, end_line: int | None) -> str | None:
        """
        Read specific lines from a file.

        Args:
            file_path: Path to the file (relative or absolute)
            start_line: Start line number (1-indexed)
            end_line: End line number (1-indexed, inclusive)

        Returns:
            Code content string or None if failed
        """
        if not start_line or not end_line:
            return None

        # Resolve file path
        if self.repo_root:
            full_path = self.repo_root / file_path
        else:
            full_path = Path(file_path)

        if not full_path.exists():
            return None

        try:
            # Read file content
            content = full_path.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()

            # Extract lines (convert to 0-indexed)
            start_idx = max(0, start_line - 1)
            end_idx = min(len(lines), end_line)

            # Limit snippet size (max 50 lines)
            if end_idx - start_idx > 50:
                end_idx = start_idx + 50

            selected_lines = lines[start_idx:end_idx]

            # Format with line numbers
            formatted = []
            for i, line in enumerate(selected_lines, start=start_line):
                formatted.append(f"{i:4d} | {line}")

            return "\n".join(formatted)

        except Exception as e:
            logger.debug(f"Failed to read file {full_path}: {e}")
            return None

    def _generate_placeholder_snippet(self, hit, query: str, start_line: int | None, end_line: int | None) -> str:
        """
        Generate placeholder snippet when actual content is unavailable.

        Args:
            hit: Search hit with metadata
            query: Search query
            start_line: Start line if known
            end_line: End line if known

        Returns:
            Placeholder snippet string
        """
        metadata = hit.metadata or {}
        symbol_name = metadata.get("symbol_name", "code")
        line_info = ""
        if start_line and end_line:
            line_info = f" (lines {start_line}-{end_line})"
        return f"# {symbol_name}{line_info}\n# File: {hit.file_path}\n# Query: '{query[:50]}'"

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
