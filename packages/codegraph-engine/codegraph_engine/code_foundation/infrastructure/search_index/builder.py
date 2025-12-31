"""Search Index Builder.

Converts SymbolGraph → SearchIndex (add ranking signals and search metadata).
Enriches lightweight symbols with heavy search-optimized data.
"""

from collections import defaultdict
from typing import TYPE_CHECKING

from codegraph_engine.code_foundation.infrastructure.search_index.models import (
    QueryIndexes,
    SearchableRelation,
    SearchableSymbol,
    SearchIndex,
)
from codegraph_engine.code_foundation.infrastructure.symbol_graph.models import (
    Relation,
    RelationKind,
    Symbol,
    SymbolGraph,
    SymbolKind,
)

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models.core import Node
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument


class SearchIndexBuilder:
    """Builds heavy SearchIndex from lightweight SymbolGraph.

    Enrichment strategy:
    1. Symbol → SearchableSymbol (add ranking signals)
    2. Relation → SearchableRelation (add frequency)
    3. Build QueryIndexes (fuzzy, prefix, signature)

    Result: ~500-800 bytes/symbol (vs 200 bytes in SymbolGraph)
    """

    def build_from_symbol_graph(
        self,
        symbol_graph: SymbolGraph,
        include_full_text: bool = False,
        module_exports: dict[str, set[str]] | None = None,
        ir_document: "IRDocument | None" = None,
    ) -> SearchIndex:
        """Build SearchIndex from SymbolGraph.

        Args:
            symbol_graph: Lightweight SymbolGraph
            include_full_text: Include full source text for fuzzy search
            module_exports: Optional module-level exports mapping
                          module_path → set of exported symbol FQNs
                          (e.g., from __all__ in Python)
            ir_document: Optional IR Document for extracting metrics
                        (complexity, LOC, etc.)

        Returns:
            Heavy SearchIndex with ranking signals
        """
        search_index = SearchIndex(
            repo_id=symbol_graph.repo_id,
            snapshot_id=symbol_graph.snapshot_id,
        )

        # Calculate ranking signals for all symbols
        ranking_signals = self._calculate_ranking_signals(symbol_graph)

        # Build IR Node index for fast lookup (O(1) instead of O(n))
        ir_node_index = self._build_ir_node_index(ir_document) if ir_document else None

        # Build relation frequency index (count occurrences of same relation)
        relation_frequency = self._build_relation_frequency_index(symbol_graph)

        # Convert symbols
        for symbol in symbol_graph.symbols.values():
            searchable_symbol = self._convert_to_searchable_symbol(
                symbol, ranking_signals, include_full_text, module_exports, ir_node_index
            )
            search_index.symbols[symbol.id] = searchable_symbol

        # Convert relations
        for relation in symbol_graph.relations:
            searchable_relation = self._convert_to_searchable_relation(relation, relation_frequency)
            search_index.relations.append(searchable_relation)

        # Build query indexes
        search_index.query_indexes = self._build_query_indexes(search_index)

        return search_index

    def _calculate_ranking_signals(self, symbol_graph: SymbolGraph) -> dict[str, dict[str, int]]:
        """Calculate ranking signals for all symbols.

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
        module_exports: dict[str, set[str]] | None = None,
        ir_node_index: dict[str, "Node"] | None = None,
    ) -> SearchableSymbol:
        """Convert Symbol → SearchableSymbol.

        Adds ranking signals and search metadata.
        """
        signals = ranking_signals.get(symbol.id, {"call_count": 0, "import_count": 0, "reference_count": 0})

        # Determine visibility
        is_public = self._is_public(symbol)
        is_exported = self._is_exported(symbol, module_exports)

        # Calculate metrics from IR Document
        complexity = self._calculate_complexity(symbol, ir_node_index)
        loc = self._calculate_loc(symbol)

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
            complexity=complexity,
            loc=loc,
            # Search metadata
            docstring=docstring,
            signature=signature,
            full_text=full_text if include_full_text else None,
            # Parent
            parent_id=symbol.parent_id,
        )

    def _convert_to_searchable_relation(
        self, relation: Relation, relation_frequency: dict[tuple[str, str, RelationKind], int]
    ) -> SearchableRelation:
        """Convert Relation → SearchableRelation.

        Adds frequency tracking based on how many times this relation appears.

        Args:
            relation: Relation to convert
            relation_frequency: Pre-calculated frequency index
                              (source_id, target_id, kind) → count

        Returns:
            SearchableRelation with frequency
        """
        # Lookup frequency (default: 1 if not found)
        key = (relation.source_id, relation.target_id, relation.kind)
        frequency = relation_frequency.get(key, 1)

        return SearchableRelation(
            id=relation.id,
            kind=relation.kind,
            source_id=relation.source_id,
            target_id=relation.target_id,
            frequency=frequency,
        )

    def _is_public(self, symbol: Symbol) -> bool:
        """Determine if symbol is public.

        Python convention: name not starting with _ is public.
        """
        if symbol.name.startswith("_") and not symbol.name.startswith("__"):
            return False

        # Special cases
        if symbol.kind in (SymbolKind.MODULE, SymbolKind.FILE):
            return True

        return True

    def _is_exported(self, symbol: Symbol, module_exports: dict[str, set[str]] | None = None) -> bool:
        """Determine if symbol is exported.

        Uses module-level exports (__all__ in Python, export in TS/JS) if available,
        otherwise falls back to heuristics:
        - Top-level classes/functions are considered exported
        - Symbols with public visibility (not starting with _)

        Args:
            symbol: Symbol to check
            module_exports: Optional mapping of module_path → exported symbol FQNs

        Returns:
            True if symbol is exported (part of public API)

        """
        # If module_exports provided, check exact exports
        if module_exports is not None:
            # Extract module path from FQN (e.g., "os.path.join" → "os.path")
            module_path = self._extract_module_path(symbol.fqn)
            if module_path in module_exports:
                # Check if this symbol's FQN is in the exported set
                return symbol.fqn in module_exports[module_path]

        # Fallback heuristics:
        # 1. Top-level symbols (no parent)
        # Consider classes/functions as exported if they're public
        if symbol.parent_id is None and symbol.kind in (SymbolKind.CLASS, SymbolKind.FUNCTION):
            return self._is_public(symbol)

        # 2. Methods in exported classes
        # If parent is a top-level class and method is public, consider it exported
        # (This is a heuristic; real export tracking should happen in graph generation)

        return False

    def _extract_module_path(self, fqn: str) -> str:
        """Extract module path from FQN.

        Examples:
            "os.path.join" → "os.path"
            "myapp.models.User" → "myapp.models"
            "main" → "" (no module)

        """
        parts = fqn.split(".")
        # Return all but last part (last part is the symbol name)
        return ".".join(parts[:-1]) if len(parts) > 1 else ""

    def _build_ir_node_index(self, ir_document: "IRDocument | None") -> dict[str, "Node"] | None:
        """
        Build index for fast IR Node lookup.

        Creates FQN → Node mapping for O(1) lookup instead of O(n) search.

        Args:
            ir_document: IR Document to index

        Returns:
            Dict mapping FQN → Node, or None if ir_document is None
        """
        if ir_document is None:
            return None

        index: dict[str, Node] = {}
        for node in ir_document.nodes:
            # Use FQN as key (most reliable identifier)
            if node.fqn:
                index[node.fqn] = node

        return index

    def _calculate_complexity(
        self,
        symbol: Symbol,
        ir_node_index: dict[str, "Node"] | None,
    ) -> int:
        """
        Calculate cyclomatic complexity from IR Document.

        Strategy:
        1. Lookup IR Node by FQN (O(1))
        2. Extract control_flow_summary.cyclomatic_complexity
        3. Fallback: 1 (if not found or no CFG summary)

        Args:
            symbol: Symbol to calculate complexity for
            ir_node_index: Pre-built FQN → Node index

        Returns:
            Cyclomatic complexity (default: 1)
        """
        if ir_node_index is None:
            return 1

        # Lookup by FQN (fastest)
        ir_node = ir_node_index.get(symbol.fqn)
        if ir_node is None:
            return 1

        # Extract complexity from control flow summary
        if ir_node.control_flow_summary:
            return ir_node.control_flow_summary.cyclomatic_complexity

        return 1

    def _calculate_loc(self, symbol: Symbol) -> int:
        """
        Calculate lines of code from span.

        Args:
            symbol: Symbol with span

        Returns:
            Lines of code (end_line - start_line + 1), or 0 if span is None
        """
        if symbol.span is None:
            return 0

        start_line = symbol.span.start_line
        end_line = symbol.span.end_line

        # LOC = lines in span (inclusive)
        return end_line - start_line + 1

    def _calculate_frequency(
        self,
        symbol: Symbol,
        ranking_signals: dict[str, dict[str, int]],
    ) -> int:
        """
        Calculate symbol usage frequency.

        Frequency = import_count + call_count + reference_count

        Args:
            symbol: Symbol to calculate frequency for
            ranking_signals: Pre-calculated ranking signals

        Returns:
            Total frequency (sum of all usage types)
        """
        signals = ranking_signals.get(symbol.id, {"call_count": 0, "import_count": 0, "reference_count": 0})

        return signals["call_count"] + signals["import_count"] + signals["reference_count"]

    def _build_relation_frequency_index(self, symbol_graph: SymbolGraph) -> dict[tuple[str, str, RelationKind], int]:
        """
        Build frequency index for relations.

        Counts how many times each unique (source_id, target_id, kind) combination
        appears in the graph. This represents how frequently a relationship is used.

        Args:
            symbol_graph: SymbolGraph to analyze

        Returns:
            Dict mapping (source_id, target_id, kind) → frequency count
        """
        frequency: dict[tuple[str, str, RelationKind], int] = defaultdict(int)

        for relation in symbol_graph.relations:
            key = (relation.source_id, relation.target_id, relation.kind)
            frequency[key] += 1

        return dict(frequency)

    def _build_query_indexes(self, search_index: SearchIndex) -> QueryIndexes:
        """Build pre-computed query indexes.

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
