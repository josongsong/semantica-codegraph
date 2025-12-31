"""
Symbol Search Layer (RFC-020 Phase 1)

4-Layer symbol search implementation:
- L1: OccurrenceIndex (exact match, O(1))
- L2: SymSpell (typo correction, edit distance ≤ 2)
- L3: Trigram (fuzzy substring match)
- L4: Qdrant (semantic fallback)

Architecture:
- Infrastructure layer (uses domain OccurrenceIndex)
- SOLID: SRP (symbol search only), OCP (extensible layers)
- No hardcoding: all constants in Config
- No Fake/Stub: Real OccurrenceIndex only

Performance Targets (RFC-020 Section 12.1):
- L1 Exact: < 1ms
- L2 SymSpell: < 1ms
- L3 Trigram: < 5ms
- L4 Semantic: < 10ms
"""

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

try:
    from symspellpy import SymSpell, Verbosity

    HAS_SYMSPELL = True
except ImportError:
    HAS_SYMSPELL = False
    SymSpell = None  # type: ignore
    Verbosity = None  # type: ignore

from codegraph_shared.common.observability import get_logger

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient

    from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument, Occurrence

logger = get_logger(__name__)


@dataclass
class SymbolSearchConfig:
    """
    Symbol Search 설정 (RFC-020)

    No hardcoding: 모든 상수는 Config에서 관리
    """

    # L2: SymSpell
    symspell_max_edit_distance: int = 2  # Edit distance ≤ 2
    symspell_prefix_length: int = 7  # Prefix length for dictionary

    # L3: Trigram
    trigram_similarity_threshold: float = 0.7  # Jaccard similarity ≥ 0.7
    trigram_top_k: int = 10  # Top K candidates

    # SymSpell rebuild
    rebuild_threshold: int = 100  # 100 변경마다 재빌드
    min_rebuild_interval_sec: float = 5.0  # 최소 5초 간격

    # L4: Semantic fallback
    semantic_enabled: bool = False  # Optional
    semantic_top_k: int = 10


class SymbolSearchLayer:
    """
    Symbol Search Layer (4-Layer cascading)

    Architecture (Hexagonal):
    - Infrastructure layer
    - Uses domain OccurrenceIndex (Port)
    - No dependency on concrete adapters

    SOLID:
    - SRP: Symbol search only
    - OCP: Extensible (add layers)
    - LSP: Protocol compatible
    - ISP: Minimal interface
    - DIP: Depends on OccurrenceIndex (abstraction)

    Performance (RFC-020):
    - L1: ~0.01ms (dict lookup)
    - L2: ~0.1ms (SymSpell)
    - L3: ~1-5ms (Trigram)
    - L4: ~10ms (Semantic)
    """

    def __init__(
        self,
        ir_doc: "IRDocument",
        qdrant_client: "AsyncQdrantClient | None" = None,
        config: SymbolSearchConfig | None = None,
    ):
        """
        Initialize Symbol Search Layer

        Args:
            ir_doc: IR document with OccurrenceIndex (must have _occurrence_index)
            qdrant_client: Optional Qdrant client for L4 semantic search
            config: Symbol search configuration

        Raises:
            ValueError: If ir_doc or _occurrence_index is None
            ImportError: If symspellpy not installed
        """
        if not HAS_SYMSPELL:
            raise ImportError(
                "symspellpy not installed. Install: pip install symspellpy>=6.7.7 (RFC-020 Phase 1 requirement)"
            )

        if not ir_doc:
            raise ValueError("IRDocument cannot be None")

        if not ir_doc._occurrence_index:
            raise ValueError("IRDocument must have _occurrence_index built")

        self.ir_doc = ir_doc
        self.occurrence_idx = ir_doc._occurrence_index  # L1: 기존 재활용
        self.qdrant_client = qdrant_client
        self.config = config or SymbolSearchConfig()

        # L2: SymSpell 초기화
        self.symspell = SymSpell(
            max_dictionary_edit_distance=self.config.symspell_max_edit_distance,
            prefix_length=self.config.symspell_prefix_length,
        )
        self._build_symspell()

        # L3: Trigram 인덱스
        self.trigram_index: dict[str, set[str]] = {}
        self._build_trigram_index()

        # Incremental rebuild tracking
        self._pending_changes = 0
        self._last_rebuild = time.time()
        self._symspell_version = 1

        logger.info(
            "symbol_search_layer_initialized",
            symbols=len(self.occurrence_idx.by_id),
            trigrams=len(self.trigram_index),
            symspell_version=self._symspell_version,
        )

    def _build_symspell(self) -> None:
        """
        Build SymSpell dictionary from OccurrenceIndex

        L2: Typo correction
        """
        for occ in self.occurrence_idx.by_id.values():
            if occ.symbol_id:
                # Add symbol to SymSpell
                # Frequency = 1 (모든 심볼 동등)
                self.symspell.create_dictionary_entry(occ.symbol_id, 1)

        logger.debug(f"SymSpell dictionary built: {self.symspell.word_count} words")

    def _build_trigram_index(self) -> None:
        """
        Build Trigram index from OccurrenceIndex

        L3: Fuzzy substring match
        Memory: ~0.1MB/10K symbols (실측, RFC-020 Section 19.6)
        """
        for occ in self.occurrence_idx.by_id.values():
            if occ.symbol_id:
                # Generate trigrams
                trigrams = self._generate_trigrams(occ.symbol_id)
                for trigram in trigrams:
                    if trigram not in self.trigram_index:
                        self.trigram_index[trigram] = set()
                    self.trigram_index[trigram].add(occ.symbol_id)

        logger.debug(f"Trigram index built: {len(self.trigram_index)} trigrams")

    @staticmethod
    def _generate_trigrams(text: str) -> set[str]:
        """
        Generate trigrams from text

        Args:
            text: Input string

        Returns:
            Set of 3-character substrings
        """
        if len(text) < 3:
            return set()

        return {text[i : i + 3] for i in range(len(text) - 2)}

    def search(self, query: str, max_results: int = 50) -> list["Occurrence"]:
        """
        Search symbols (4-Layer cascading)

        Fallback chain:
        1. L1: Exact match (OccurrenceIndex)
        2. L2: Typo correction (SymSpell)
        3. L3: Fuzzy match (Trigram)
        4. L4: Semantic (Qdrant, optional)

        Args:
            query: Search query
            max_results: Maximum results

        Returns:
            List of Occurrence objects

        Performance:
        - L1 hit: ~0.01ms
        - L2 hit: ~0.1ms
        - L3 hit: ~1-5ms
        - L4 hit: ~10ms
        """
        if not query or not query.strip():
            return []

        query = query.strip()

        # L1: Exact match (OccurrenceIndex)
        exact_results = self.occurrence_idx.get_references(query)
        if exact_results:
            logger.debug(f"L1 exact match: {query} → {len(exact_results)} results")
            return exact_results[:max_results]

        # L2: SymSpell typo correction
        symspell_results = self._search_symspell(query, max_results)
        if symspell_results:
            logger.debug(f"L2 SymSpell match: {query} → {len(symspell_results)} results")
            return symspell_results

        # L3: Trigram fuzzy match
        trigram_results = self._search_trigram(query, max_results)
        if trigram_results:
            logger.debug(f"L3 Trigram match: {query} → {len(trigram_results)} results")
            return trigram_results

        # L4: Semantic fallback (optional)
        if self.config.semantic_enabled and self.qdrant_client:
            # TODO: Phase 1에서는 구현 생략, Phase 4 이후 추가
            logger.debug(f"L4 Semantic fallback: {query} (not implemented)")

        logger.debug(f"No match: {query}")
        return []

    def _search_symspell(self, query: str, max_results: int) -> list["Occurrence"]:
        """
        L2: SymSpell typo correction

        Args:
            query: Search query
            max_results: Maximum results

        Returns:
            List of Occurrence objects from corrected query
        """
        # SymSpell lookup
        suggestions = self.symspell.lookup(
            query,
            Verbosity.CLOSEST,  # Only closest match
            max_edit_distance=self.config.symspell_max_edit_distance,
        )

        if not suggestions:
            return []

        # Get occurrences for corrected term
        corrected_term = suggestions[0].term
        results = self.occurrence_idx.get_references(corrected_term)

        if results:
            logger.debug(f"SymSpell: '{query}' → '{corrected_term}' ({len(results)} results)")

        return results[:max_results]

    def _search_trigram(self, query: str, max_results: int) -> list["Occurrence"]:
        """
        L3: Trigram fuzzy substring match

        Algorithm:
        1. Generate query trigrams
        2. Find candidate symbols (Jaccard similarity ≥ threshold)
        3. Return top-K by similarity

        Args:
            query: Search query
            max_results: Maximum results

        Returns:
            List of Occurrence objects sorted by similarity
        """
        query_trigrams = self._generate_trigrams(query)
        if not query_trigrams:
            return []

        # Calculate Jaccard similarity for each symbol
        candidates: list[tuple[str, float]] = []

        for trigram in query_trigrams:
            if trigram in self.trigram_index:
                for symbol_id in self.trigram_index[trigram]:
                    # Calculate similarity (lazy - only for candidates)
                    symbol_trigrams = self._generate_trigrams(symbol_id)
                    similarity = self._jaccard_similarity(query_trigrams, symbol_trigrams)

                    if similarity >= self.config.trigram_similarity_threshold:
                        candidates.append((symbol_id, similarity))

        # Deduplicate and sort by similarity
        unique_candidates = {}
        for symbol_id, similarity in candidates:
            if symbol_id not in unique_candidates or similarity > unique_candidates[symbol_id]:
                unique_candidates[symbol_id] = similarity

        sorted_candidates = sorted(unique_candidates.items(), key=lambda x: x[1], reverse=True)

        # Get occurrences for top-K
        results = []
        for symbol_id, _similarity in sorted_candidates[: self.config.trigram_top_k]:
            occurrences = self.occurrence_idx.get_references(symbol_id)
            results.extend(occurrences)

            if len(results) >= max_results:
                break

        return results[:max_results]

    @staticmethod
    def _jaccard_similarity(set1: set[str], set2: set[str]) -> float:
        """
        Calculate Jaccard similarity

        Args:
            set1: First set
            set2: Second set

        Returns:
            Jaccard similarity (0.0-1.0)
        """
        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def update_incremental(self, added_symbols: list[str], removed_symbols: list[str]) -> None:
        """
        Incremental update for SymSpell/Trigram

        Strategy (RFC-020 Section 11.7):
        - Batch rebuild every 100 changes
        - Minimum 5-second interval
        - Async rebuild (non-blocking)

        Args:
            added_symbols: Newly added symbol IDs
            removed_symbols: Removed symbol IDs
        """
        self._pending_changes += len(added_symbols) + len(removed_symbols)
        current_time = time.time()

        # Check rebuild conditions
        should_rebuild = (
            self._pending_changes >= self.config.rebuild_threshold
            and (current_time - self._last_rebuild) >= self.config.min_rebuild_interval_sec
        )

        if should_rebuild:
            # Async rebuild (non-blocking)
            asyncio.create_task(self._rebuild_async())
            self._last_rebuild = current_time
            self._pending_changes = 0
            logger.info(
                "symbol_search_rebuild_triggered",
                pending_changes=self._pending_changes,
                version=self._symspell_version,
            )

    async def _rebuild_async(self) -> None:
        """
        Async rebuild SymSpell/Trigram

        Performance: ~100ms for 10K symbols (RFC-020 Section 11.8)
        """
        start = time.time()

        try:
            # Rebuild SymSpell
            new_symspell = SymSpell(
                max_dictionary_edit_distance=self.config.symspell_max_edit_distance,
                prefix_length=self.config.symspell_prefix_length,
            )

            for occ in self.occurrence_idx.by_id.values():
                if occ.symbol_id:
                    new_symspell.create_dictionary_entry(occ.symbol_id, 1)

            # Rebuild Trigram
            new_trigram_index: dict[str, set[str]] = {}
            for occ in self.occurrence_idx.by_id.values():
                if occ.symbol_id:
                    trigrams = self._generate_trigrams(occ.symbol_id)
                    for trigram in trigrams:
                        if trigram not in new_trigram_index:
                            new_trigram_index[trigram] = set()
                        new_trigram_index[trigram].add(occ.symbol_id)

            # Atomic swap
            self.symspell = new_symspell
            self.trigram_index = new_trigram_index
            self._symspell_version += 1

            duration_ms = (time.time() - start) * 1000
            logger.info(
                "symbol_search_rebuild_complete",
                duration_ms=duration_ms,
                version=self._symspell_version,
                symbols=len(self.occurrence_idx.by_id),
                trigrams=len(self.trigram_index),
            )

        except Exception as e:
            logger.error("symbol_search_rebuild_failed", error=str(e))

    def get_stats(self) -> dict:
        """Get statistics"""
        return {
            "total_symbols": len(self.occurrence_idx.by_id),
            "symspell_words": self.symspell.word_count(),
            "trigram_count": len(self.trigram_index),
            "symspell_version": self._symspell_version,
            "pending_changes": self._pending_changes,
        }
