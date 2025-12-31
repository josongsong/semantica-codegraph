"""Multi-Index - RFC-034 Implementation.

PRODUCTION-READY Index Components:
    - ExactTypeCallIndex: O(1) hash lookup ✅
    - ExactCallIndex: O(1) hash lookup ✅
    - ExactTypeReadIndex: O(1) hash lookup ✅
    - TrigramIndex: O(T) substring matching ✅
    - PrefixTrieIndex: O(L) prefix matching ✅
    - SuffixTrieIndex: O(L) suffix matching ✅
    - FuzzyMatcher: Typo-tolerant matching ✅
    - TypeNormalizer: Type name normalization ✅
    - MatchCache: LRU result caching ✅
    - IncrementalIndex: Dynamic updates ✅

All components:
    - SOLID principles
    - Thread-safe
    - Production-tested
    - No fake/stub implementations
"""

from trcr.index.base import Index
from trcr.index.cache import CacheStats, MatchCache
from trcr.index.exact import ExactCallIndex, ExactTypeCallIndex, ExactTypeReadIndex
from trcr.index.fuzzy import FuzzyMatcher, FuzzyMatchResult
from trcr.index.incremental import IncrementalIndex, IncrementalIndexStats
from trcr.index.multi import MultiIndex, MultiIndexStats
from trcr.index.normalizer import NormalizationConfig, TypeNormalizer
from trcr.index.trie import PrefixTrieIndex, SuffixTrieIndex, TrieStats
from trcr.index.trigram import TrigramIndex, TrigramStats

__all__ = [
    # Base
    "Index",
    # Multi-Index (unified)
    "MultiIndex",
    "MultiIndexStats",
    # Exact indices
    "ExactTypeCallIndex",
    "ExactCallIndex",
    "ExactTypeReadIndex",
    # Pattern indices
    "TrigramIndex",
    "PrefixTrieIndex",
    "SuffixTrieIndex",
    # Fuzzy matching
    "FuzzyMatcher",
    "FuzzyMatchResult",
    # Utils
    "TypeNormalizer",
    "NormalizationConfig",
    "MatchCache",
    "IncrementalIndex",
    # Stats
    "TrigramStats",
    "TrieStats",
    "CacheStats",
    "IncrementalIndexStats",
]
