"""
Zoekt Search Adapter

Adapter for Zoekt lexical search engine.
Implements fuzzy search and prefix search using Zoekt's ctags-based indexing.
"""

from typing import TYPE_CHECKING

from src.contexts.code_foundation.infrastructure.search_index.models import SearchableSymbol, SearchIndex

if TYPE_CHECKING:
    from src.contexts.code_foundation.infrastructure.symbol_graph.models import SymbolKind
    from src.infra.search.zoekt import ZoektAdapter
from src.common.observability import get_logger

logger = get_logger(__name__)


class ZoektSearchAdapter:
    """
    Zoekt implementation of SearchIndexPort (lexical search).

    Uses Zoekt for:
    - Fuzzy name search (trigram-based)
    - Prefix search (autocomplete)
    - Full-text search in code

    Note: Zoekt indexes are built externally via zoekt-index.
    This adapter only queries the index.
    """

    def __init__(self, zoekt_adapter: "ZoektAdapter"):
        """
        Initialize Zoekt adapter.

        Args:
            zoekt_adapter: ZoektAdapter instance for querying
        """
        self.zoekt = zoekt_adapter

    def index_symbols(self, search_index: SearchIndex) -> None:
        """
        Index symbols in Zoekt.

        Note: Zoekt indexing is done externally via zoekt-index CLI.
        This method logs a warning - use zoekt-index for actual indexing.

        Args:
            search_index: SearchIndex to be indexed
        """
        logger.warning(
            "Zoekt indexing must be done externally via zoekt-index CLI. "
            f"SearchIndex contains {search_index.symbol_count} symbols."
        )
        # Zoekt requires external indexing process:
        # zoekt-index -index /path/to/index /path/to/repo

    async def search_fuzzy(
        self,
        query: str,
        repo_id: str,
        snapshot_id: str,
        limit: int = 10,
    ) -> list[SearchableSymbol]:
        """
        Fuzzy search using Zoekt.

        Uses Zoekt's trigram-based fuzzy matching.

        Args:
            query: Fuzzy search query
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            limit: Maximum results

        Returns:
            List of matching symbols
        """
        try:
            # Zoekt query for symbol names (case-insensitive)
            zoekt_query = f"sym:{query}"

            results = await self.zoekt.search(
                query=zoekt_query,
                limit=limit,
                repo_filter=repo_id,
            )

            return self._convert_results(results, repo_id, snapshot_id)

        except Exception as e:
            logger.error(f"Zoekt fuzzy search failed: {e}")
            return []

    async def search_prefix(
        self,
        prefix: str,
        repo_id: str,
        snapshot_id: str,
        limit: int = 10,
    ) -> list[SearchableSymbol]:
        """
        Prefix search using Zoekt.

        Uses Zoekt's prefix matching for autocomplete.

        Args:
            prefix: Name prefix
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            limit: Maximum results

        Returns:
            List of matching symbols
        """
        try:
            # Zoekt query for prefix matching
            # Use regex for prefix: ^prefix
            zoekt_query = f"sym:^{prefix}"

            results = await self.zoekt.search(
                query=zoekt_query,
                limit=limit,
                repo_filter=repo_id,
            )

            return self._convert_results(results, repo_id, snapshot_id)

        except Exception as e:
            logger.error(f"Zoekt prefix search failed: {e}")
            return []

    async def search_signature(
        self,
        signature_pattern: str,
        repo_id: str,
        snapshot_id: str,
        limit: int = 10,
    ) -> list[SearchableSymbol]:
        """
        Signature search using Zoekt regex.

        Args:
            signature_pattern: Signature pattern (e.g., "def.*str.*int")
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            limit: Maximum results

        Returns:
            List of matching symbols
        """
        try:
            # Use regex search for signature patterns
            zoekt_query = f"r:{signature_pattern}"

            results = await self.zoekt.search(
                query=zoekt_query,
                limit=limit,
                repo_filter=repo_id,
            )

            return self._convert_results(results, repo_id, snapshot_id)

        except Exception as e:
            logger.error(f"Zoekt signature search failed: {e}")
            return []

    async def search_content(
        self,
        query: str,
        repo_id: str,
        snapshot_id: str,
        limit: int = 10,
        file_pattern: str | None = None,
    ) -> list[SearchableSymbol]:
        """
        Full-text content search using Zoekt.

        Args:
            query: Search query
            repo_id: Repository ID
            snapshot_id: Snapshot ID
            limit: Maximum results
            file_pattern: Optional file pattern filter (e.g., "*.py")

        Returns:
            List of matching symbols
        """
        try:
            # Build query with optional file filter
            zoekt_query = query
            if file_pattern:
                zoekt_query = f"f:{file_pattern} {query}"

            results = await self.zoekt.search(
                query=zoekt_query,
                limit=limit,
                repo_filter=repo_id,
            )

            return self._convert_results(results, repo_id, snapshot_id)

        except Exception as e:
            logger.error(f"Zoekt content search failed: {e}")
            return []

    def _convert_results(
        self,
        zoekt_results: list,
        repo_id: str,
        snapshot_id: str,
    ) -> list[SearchableSymbol]:
        """
        Convert Zoekt results to SearchableSymbol list.

        Args:
            zoekt_results: List of ZoektFileMatch
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            List of SearchableSymbol
        """

        symbols = []
        seen_ids = set()

        for file_match in zoekt_results:
            file_path = file_match.FileName
            language = file_match.Language or "unknown"

            for match in file_match.Matches:
                # Build symbol from match
                line_num = match.LineNum

                # Extract matched text from fragments
                matched_text = ""
                context = ""
                for fragment in match.Fragments:
                    matched_text += fragment.Match
                    context += fragment.Pre + fragment.Match + fragment.Post

                # Skip if no meaningful match
                if not matched_text.strip():
                    continue

                # Generate unique ID
                symbol_id = f"{repo_id}:{file_path}:{line_num}:{matched_text[:50]}"
                if symbol_id in seen_ids:
                    continue
                seen_ids.add(symbol_id)

                # Infer symbol kind from context
                kind = self._infer_symbol_kind(context, language)

                symbol = SearchableSymbol(
                    id=symbol_id,
                    kind=kind,
                    fqn=f"{file_path}:{matched_text}",
                    name=matched_text.strip(),
                    repo_id=repo_id,
                    snapshot_id=snapshot_id,
                    full_text=context.strip(),
                )
                symbols.append(symbol)

        return symbols

    def _infer_symbol_kind(self, context: str, language: str) -> "SymbolKind":
        """
        Infer symbol kind from context.

        Args:
            context: Code context
            language: Programming language

        Returns:
            Inferred SymbolKind
        """
        from src.contexts.code_foundation.infrastructure.symbol_graph.models import SymbolKind

        context_lower = context.lower().strip()

        if language.lower() == "python":
            if context_lower.startswith("class "):
                return SymbolKind.CLASS
            if context_lower.startswith("def "):
                return SymbolKind.FUNCTION
            if context_lower.startswith("import ") or context_lower.startswith("from "):
                return SymbolKind.MODULE

        elif language.lower() in ("javascript", "typescript"):
            if "class " in context_lower:
                return SymbolKind.CLASS
            if "function " in context_lower or "=>" in context:
                return SymbolKind.FUNCTION

        elif language.lower() in ("java", "kotlin"):
            if "class " in context_lower:
                return SymbolKind.CLASS
            if "interface " in context_lower:
                return SymbolKind.CLASS
            if "(" in context and ")" in context:
                return SymbolKind.METHOD

        return SymbolKind.FUNCTION

    async def delete_index(self, repo_id: str, snapshot_id: str) -> None:
        """
        Delete Zoekt index.

        Note: Zoekt index deletion is done externally.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID
        """
        logger.warning(
            f"Zoekt index deletion must be done externally for {repo_id}:{snapshot_id}. "
            "Delete the index shard files from the Zoekt index directory."
        )

    async def exists(self, repo_id: str, snapshot_id: str) -> bool:
        """
        Check if Zoekt index exists.

        Performs a simple query to check if the repo is indexed.

        Args:
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            True if index exists
        """
        try:
            # Try to search for anything in the repo
            results = await self.zoekt.search(
                query=".",
                limit=1,
                repo_filter=repo_id,
            )
            return len(results) > 0
        except Exception:
            return False

    async def healthcheck(self) -> bool:
        """
        Check Zoekt availability.

        Returns:
            True if Zoekt is responsive
        """
        return await self.zoekt.healthcheck()
