"""
Symbol Search Tool

Finds symbols (functions, classes, variables) by name.

Uses Semantica's symbol index (Kuzu graph) for precise symbol lookup.
"""

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.schemas import SymbolInfo, SymbolSearchInput, SymbolSearchOutput
from src.contexts.agent_automation.infrastructure.tools.base import BaseTool

logger = get_logger(__name__)


class SymbolSearchTool(BaseTool[SymbolSearchInput, SymbolSearchOutput]):
    """
    Find symbols (functions, classes) by name.

    Uses Semantica's symbol index for precise, structured symbol lookup.
    Much faster than general code search for symbol-specific queries.

    Example:
        tool = SymbolSearchTool(symbol_index=container.symbol_index)

        # Find function by name
        result = await tool.execute(SymbolSearchInput(
            name="authenticate",
            kind="function"
        ))

        # Find any symbol with partial match
        result = await tool.execute(SymbolSearchInput(
            name="User",
            kind="any",
            exact_match=False
        ))
    """

    name = "symbol_search"
    description = (
        "Find symbols (functions, classes, variables) by name. "
        "Fast and precise symbol lookup using the symbol index. "
        "Returns symbol information with file paths, line numbers, signatures, and docstrings."
    )
    input_schema = SymbolSearchInput
    output_schema = SymbolSearchOutput

    def __init__(
        self,
        symbol_index=None,
        repo_id: str = "current",
        snapshot_id: str = "main",
    ):
        """
        Initialize symbol search tool.

        Args:
            symbol_index: Kuzu symbol index
            repo_id: Repository ID to search in
            snapshot_id: Snapshot ID to search in
        """
        super().__init__()
        self.symbol_index = symbol_index
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id

    async def _execute(self, input_data: SymbolSearchInput) -> SymbolSearchOutput:
        """
        Execute symbol search.

        Args:
            input_data: Symbol search parameters

        Returns:
            Found symbols with metadata
        """
        try:
            # Search for symbols using symbol index
            search_hits = await self.symbol_index.search(
                repo_id=self.repo_id,
                snapshot_id=self.snapshot_id,
                query=input_data.name,
                limit=50,  # Get more results for filtering
            )

            # Filter and convert results
            symbols = []
            for hit in search_hits:
                metadata = hit.metadata or {}

                # Apply kind filter
                if input_data.kind and input_data.kind != "any":
                    symbol_kind = metadata.get("kind", "").lower()
                    if symbol_kind != input_data.kind:
                        continue

                # Apply exact match filter
                symbol_name = metadata.get("name", "")
                if input_data.exact_match and symbol_name != input_data.name:
                    continue

                # Create SymbolInfo
                symbol = SymbolInfo(
                    symbol_id=hit.symbol_id or f"sym:{hit.chunk_id}",
                    name=symbol_name,
                    kind=metadata.get("kind", "unknown"),
                    file_path=hit.file_path,
                    start_line=metadata.get("start_line", 1),
                    end_line=metadata.get("end_line", 1),
                    signature=metadata.get("signature"),
                    docstring=metadata.get("docstring"),
                )
                symbols.append(symbol)

            return SymbolSearchOutput(
                success=True,
                symbols=symbols,
            )

        except Exception as e:
            logger.error(f"Symbol search failed: {e}", exc_info=True)
            return SymbolSearchOutput(
                success=False,
                symbols=[],
                error=str(e),
            )
