"""
Context Navigation Mode

Explores codebase to find relevant files, symbols, and code structures.

Features:
- 5-way hybrid search (lexical, vector, symbol, fuzzy, domain)
- Symbol resolution and lookup
- Call chain tracking
- File discovery and filtering
- Context building for downstream modes
"""

import logging

from src.agent.modes.base import BaseModeHandler
from src.agent.types import AgentMode, ModeContext, Result, Task
from src.index.symbol.adapter_kuzu import KuzuSymbolIndex

logger = logging.getLogger(__name__)


class ContextNavigationMode(BaseModeHandler):
    """
    Context Navigation mode for code exploration.

    This mode finds relevant code in the codebase based on the user's query,
    using multi-modal search and symbol indexing.
    """

    def __init__(
        self,
        symbol_index: KuzuSymbolIndex | None = None,
        repo_id: str = "default",
        snapshot_id: str = "latest",
    ):
        """
        Initialize Context Navigation mode.

        Args:
            symbol_index: Optional symbol index for symbol-based search
            repo_id: Repository identifier
            snapshot_id: Snapshot/version identifier
        """
        super().__init__(AgentMode.CONTEXT_NAV)
        self.symbol_index = symbol_index
        self.repo_id = repo_id
        self.snapshot_id = snapshot_id

    async def enter(self, context: ModeContext) -> None:
        """Enter context navigation mode."""
        await super().enter(context)
        self.logger.info(f"Starting code exploration for: {context.current_task}")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute context navigation.

        1. Search for relevant code using available indexes
        2. Update context with discovered files and symbols
        3. Return results with appropriate trigger

        Args:
            task: Search task with query
            context: Shared mode context

        Returns:
            Result with discovered chunks/symbols
        """
        self.logger.info(f"Searching for: {task.query}")

        # Store task in context
        context.current_task = task.query

        results = []
        symbols_found = []

        # 1. Symbol-based search (if available)
        if self.symbol_index:
            try:
                symbol_results = await self._search_symbols(task.query)
                results.extend(symbol_results)
                symbols_found = [r.get("symbol_name") for r in symbol_results if "symbol_name" in r]
                self.logger.info(f"Found {len(symbol_results)} symbols matching query")
            except Exception as e:
                self.logger.warning(f"Symbol search failed: {e}")

        # 2. Update context with discovered files and symbols
        for result in results:
            if "file_path" in result:
                context.add_file(result["file_path"])
            if "symbol_name" in result:
                context.add_symbol(result["symbol_name"])

        # 3. Record action
        context.add_action({
            "type": "search",
            "query": task.query,
            "results_count": len(results),
            "symbols_found": symbols_found[:5],  # Top 5
        })

        # 4. Determine trigger
        # If we found relevant code, transition to implementation
        # Otherwise, stay in navigation mode
        trigger = None
        if len(results) > 0:
            trigger = "target_found"
            explanation = f"Found {len(results)} relevant items ({len(symbols_found)} symbols)"
        else:
            explanation = "No results found. Try refining your search query."

        return self._create_result(
            data={
                "results": results,
                "total_count": len(results),
                "symbols": symbols_found,
                "files": list(set(r.get("file_path") for r in results if "file_path" in r)),
            },
            trigger=trigger,
            explanation=explanation,
            requires_approval=False,  # Navigation is read-only
        )

    async def _search_symbols(self, query: str) -> list[dict]:
        """
        Search symbols using symbol index.

        Args:
            query: Search query

        Returns:
            List of symbol results
        """
        if not self.symbol_index:
            return []

        try:
            # Use symbol index search
            hits = await self.symbol_index.search(
                repo_id=self.repo_id,
                snapshot_id=self.snapshot_id,
                query=query,
                limit=10,
            )

            # Convert to dict format
            results = []
            for hit in hits:
                results.append({
                    "chunk_id": hit.chunk_id,
                    "symbol_name": hit.metadata.get("name", ""),
                    "symbol_kind": hit.metadata.get("kind", ""),
                    "fqn": hit.metadata.get("fqn", ""),
                    "file_path": hit.file_path or "",
                    "score": hit.score,
                    "content": hit.metadata.get("content", ""),
                })

            return results

        except Exception as e:
            self.logger.error(f"Symbol search error: {e}")
            return []

    async def exit(self, context: ModeContext) -> None:
        """Exit context navigation mode."""
        self.logger.info(
            f"Exiting navigation - found {len(context.current_files)} files, "
            f"{len(context.current_symbols)} symbols"
        )
        await super().exit(context)


class ContextNavigationModeSimple(BaseModeHandler):
    """
    Simplified Context Navigation mode for testing without dependencies.

    Uses simple keyword matching instead of full retrieval pipeline.
    """

    def __init__(self, mock_results: list[dict] | None = None):
        """
        Initialize simple context navigation mode.

        Args:
            mock_results: Optional pre-defined results for testing
        """
        super().__init__(AgentMode.CONTEXT_NAV)
        self.mock_results = mock_results or []

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute simple context navigation with mock results.

        Args:
            task: Search task
            context: Mode context

        Returns:
            Result with mock data
        """
        self.logger.info(f"Simple search for: {task.query}")

        # Use mock results or empty list
        results = self.mock_results

        # Update context
        for result in results:
            if "file_path" in result:
                context.add_file(result["file_path"])

        context.current_task = task.query

        # Trigger if results found
        trigger = "target_found" if len(results) > 0 else None

        return self._create_result(
            data={"results": results, "count": len(results)},
            trigger=trigger,
            explanation=f"Found {len(results)} results",
            requires_approval=False,
        )
