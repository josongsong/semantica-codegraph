"""
Symbol Search Layer (RFC-020 Phase 1)

4-Layer symbol search:
- L1: OccurrenceIndex (exact match, O(1))
- L2: SymSpell (typo correction, edit distance ≤ 2)
- L3: Trigram (fuzzy substring match)
- L4: Qdrant (semantic fallback)
"""

from .symbol_search_layer import SymbolSearchConfig, SymbolSearchLayer

__all__ = ["SymbolSearchLayer", "SymbolSearchConfig"]
