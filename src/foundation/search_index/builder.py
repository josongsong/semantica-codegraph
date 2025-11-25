"""
Search Index Builder

Converts SymbolGraph → SearchIndex (add ranking signals and search metadata).
Enriches lightweight symbols with heavy search-optimized data.
"""

from collections import defaultdict

from ..symbol_graph.models import RelationKind, Symbol, SymbolGraph, SymbolKind
from .models import (
    QueryIndexes,
    SearchableRelation,
    SearchableSymbol,
    SearchIndex,
)


class SearchIndexBuilder:
    """
    Builds heavy SearchIndex from lightweight SymbolGraph.

    Enrichment strategy:
    1. Symbol → SearchableSymbol (add ranking signals)
    2. Relation → SearchableRelation (add frequency)
    3. Build QueryIndexes (fuzzy, prefix, signature)

    Result: ~500-800 bytes/symbol (vs 200 bytes in SymbolGraph)
    """

    def build_from_symbol_graph(
        self, symbol_graph: SymbolGraph, include_full_text: bool = False
    ) -> SearchIndex:
        """
        Build SearchIndex from SymbolGraph.

        Args:
            symbol_graph: Lightweight SymbolGraph
            include_full_text: Include full source text for fuzzy search

        Returns:
            Heavy SearchIndex with ranking signals
        """
        search_index = SearchIndex(
            repo_id=symbol_graph.repo_id,
            snapshot_id=symbol_graph.snapshot_id,
        )

        # Step 1: Calculate ranking signals
        ranking_signals = self._calculate_ranking_signals(symbol_graph)

        # Step 2: Convert symbols to searchable symbols
        for symbol in symbol_graph.symbols.values():
            searchable_symbol = self._convert_to_searchable_symbol(
                symbol, ranking_signals, include_full_text
            )
            search_index.symbols[searchable_symbol.id] = searchable_symbol

        # Step 3: Convert relations to searchable relations
        for relation in symbol_graph.relations:
            searchable_relation = self._convert_to_searchable_relation(relation)
            search_index.relations.append(searchable_relation)

        # Step 4: Build query indexes
        search_index.indexes = self._build_query_indexes(search_index)

        return search_index

    def _calculate_ranking_signals(
        self, symbol_graph: SymbolGraph
    ) -> dict[str, dict[str, int]]:
        """
        Calculate ranking signals for all symbols.

        Returns:
            Dict mapping symbol_id → {call_count, import_count, reference_count}
        """
        signals: dict[str, dict[str, int]] = defaultdict(
            lambda: {"call_count": 0, "import_count": 0, "reference_count": 0}
        )

        # Count calls, imports, references from relations
        for relation in symbol_graph.relations:
            if relation.kind == RelationKind.CALLS:
                signals[relation.target_id]["call_count"] += 1
            elif relation.kind == RelationKind.IMPORTS:
                signals[relation.target_id]["import_count"] += 1
            elif relation.kind in (
                RelationKind.REFERENCES_TYPE,
                RelationKind.REFERENCES_SYMBOL,
            ):
                signals[relation.target_id]["reference_count"] += 1

        return dict(signals)

    def _convert_to_searchable_symbol(
        self,
        symbol: Symbol,
        ranking_signals: dict[str, dict[str, int]],
        include_full_text: bool,
    ) -> SearchableSymbol:
        """
        Convert Symbol → SearchableSymbol.

        Adds ranking signals and search metadata.
        """
        signals = ranking_signals.get(
            symbol.id, {"call_count": 0, "import_count": 0, "reference_count": 0}
        )

        # Determine visibility
        is_public = self._is_public(symbol)
        is_exported = self._is_exported(symbol)

        # Extract search metadata (will be populated later from full source)
        docstring = None
        signature = None
        full_text = None

        # TODO: Extract from source code
        # - docstring from AST
        # - signature from IR
        # - full_text from SourceFile (if include_full_text)

        return SearchableSymbol(
            id=symbol.id,
            kind=symbol.kind,
            fqn=symbol.fqn,
            name=symbol.name,
            repo_id=symbol.repo_id,
            snapshot_id=symbol.snapshot_id,
            # Ranking signals
            call_count=signals["call_count"],
            import_count=signals["import_count"],
            reference_count=signals["reference_count"],
            is_public=is_public,
            is_exported=is_exported,
            complexity=1,  # TODO: Calculate from CFG
            loc=0,  # TODO: Calculate from span
            # Search metadata
            docstring=docstring,
            signature=signature,
            full_text=full_text if include_full_text else None,
            # Parent
            parent_id=symbol.parent_id,
        )

    def _convert_to_searchable_relation(self, relation) -> SearchableRelation:
        """
        Convert Relation → SearchableRelation.

        Adds frequency tracking.
        """
        return SearchableRelation(
            id=relation.id,
            kind=relation.kind,
            source_id=relation.source_id,
            target_id=relation.target_id,
            frequency=1,  # TODO: Track actual frequency from usage patterns
        )

    def _is_public(self, symbol: Symbol) -> bool:
        """
        Determine if symbol is public.

        Python convention: name not starting with _ is public.
        """
        if symbol.name.startswith("_") and not symbol.name.startswith("__"):
            return False

        # Special cases
        if symbol.kind in (SymbolKind.MODULE, SymbolKind.FILE):
            return True

        return True

    def _is_exported(self, symbol: Symbol) -> bool:
        """
        Determine if symbol is exported.

        TODO: Check __all__ in module for exported symbols.
        """
        # For now, consider top-level classes/functions as exported
        if symbol.parent_id is None:
            return symbol.kind in (SymbolKind.CLASS, SymbolKind.FUNCTION)

        return False

    def _build_query_indexes(self, search_index: SearchIndex) -> QueryIndexes:
        """
        Build pre-computed query indexes.

        Creates:
        - fuzzy_index: Name → symbol IDs (for trigram fuzzy search)
        - prefix_index: Prefix → symbol IDs (for autocomplete)
        - signature_index: Signature → symbol IDs (for signature search)
        - domain_index: Domain term → symbol IDs (for domain search)
        """
        fuzzy_index: dict[str, list[str]] = defaultdict(list)
        prefix_index: dict[str, list[str]] = defaultdict(list)
        signature_index: dict[str, list[str]] = defaultdict(list)
        domain_index: dict[str, list[str]] = defaultdict(list)

        for symbol in search_index.symbols.values():
            # Fuzzy index: full name (trigrams built by adapter)
            fuzzy_index[symbol.name.lower()].append(symbol.id)

            # Prefix index: all prefixes of name
            name_lower = symbol.name.lower()
            for i in range(1, len(name_lower) + 1):
                prefix = name_lower[:i]
                if prefix not in prefix_index[prefix]:
                    prefix_index[prefix].append(symbol.id)

            # Signature index: function signatures
            if symbol.signature:
                signature_index[symbol.signature].append(symbol.id)

            # Domain index: class names, module names
            if symbol.kind == SymbolKind.CLASS:
                domain_index["class"].append(symbol.id)
            elif symbol.kind == SymbolKind.FUNCTION:
                domain_index["function"].append(symbol.id)
            elif symbol.kind == SymbolKind.MODULE:
                domain_index["module"].append(symbol.id)

        return QueryIndexes(
            fuzzy_index=dict(fuzzy_index),
            prefix_index=dict(prefix_index),
            signature_index=dict(signature_index),
            domain_index=dict(domain_index),
        )
