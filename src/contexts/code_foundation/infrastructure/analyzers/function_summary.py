"""
Function-level taint analysis summary cache

Performance improvement:
- Before: O(n * m * k) where n=functions, m=avg size, k=callsites
- After: O(n * m) + O(k) with cache

Key insight: Most functions are called multiple times but analyzed once.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Set, Dict, Optional, Callable
import logging

logger = logging.getLogger(__name__)


@dataclass
class FunctionTaintSummary:
    """
    함수의 Taint 입출력 관계 요약

    Example 1 - Tainted propagation:
        def process(user_input, safe_data):
            # param 0 (user_input) is tainted
            result = user_input + "suffix"
            return result  # Tainted

        Summary:
            function_id: "app.py:10:process:(str,str)->str"
            tainted_params: {0}
            tainted_return: True
            sanitizes: False

    Example 2 - Sanitizer:
        def escape_html(text):
            return text.replace("<", "&lt;").replace(">", "&gt;")

        Summary:
            tainted_params: {0}
            tainted_return: False  # Sanitized!
            sanitizes: True

    Example 3 - Global side-effects:
        CACHE = {}

        def store_in_cache(key, data):
            CACHE[key] = data  # Global tainted

        Summary:
            tainted_params: {1}
            tainted_globals: {"CACHE"}
    """

    function_id: str
    """
    Unique identifier: file_path:line:function_name:signature
    Example: "app/utils.py:42:escape_html:(str)->str"
    """

    tainted_params: Set[int] = field(default_factory=set)
    """Parameter indices that propagate taint (0-based)"""

    tainted_return: bool = False
    """Whether return value can be tainted"""

    tainted_globals: Set[str] = field(default_factory=set)
    """Global variables that can be tainted"""

    tainted_attributes: Set[str] = field(default_factory=set)
    """Object attributes that can be tainted (for methods)"""

    sanitizes: bool = False
    """Whether this function sanitizes its inputs"""

    analyzed_at: datetime = field(default_factory=datetime.now)
    """When this summary was created"""

    confidence: float = 1.0
    """Confidence score (0.0-1.0)"""

    metadata: Dict = field(default_factory=dict)
    """Additional metadata (e.g., analysis time, complexity)"""

    def __repr__(self):
        return (
            f"FunctionTaintSummary("
            f"id={self.function_id!r}, "
            f"params={self.tainted_params}, "
            f"return={self.tainted_return}, "
            f"sanitizes={self.sanitizes})"
        )

    def is_tainted_call(self, tainted_args: Set[int]) -> bool:
        """
        Check if call with given tainted arguments produces tainted output

        Args:
            tainted_args: Set of argument indices that are tainted

        Returns:
            True if return value will be tainted

        Example:
            summary = FunctionTaintSummary(..., tainted_params={0}, tainted_return=True)
            summary.is_tainted_call({0})  # True (arg 0 is tainted)
            summary.is_tainted_call({1})  # False (arg 1 not in tainted_params)
        """
        if self.sanitizes:
            return False

        # Check if any tainted argument flows to return
        if self.tainted_return and (tainted_args & self.tainted_params):
            return True

        return False


class FunctionSummaryCache:
    """
    LRU cache for function taint summaries

    Performance characteristics:
        - Cache Hit: O(1)
        - Cache Miss: O(function_size) for analysis
        - Memory: O(num_functions * summary_size)

    Typical usage:
        - 10K functions × 100 bytes/summary = 1MB
        - 100K functions × 100 bytes = 10MB

    Usage:
        cache = FunctionSummaryCache(max_size=10000)

        # First call - miss
        summary = cache.get("func_id")  # None
        summary = analyze_function()
        cache.put(summary)

        # Second call - hit (O(1))
        summary = cache.get("func_id")  # Instant!
    """

    def __init__(self, max_size: int = 10000):
        """
        Initialize cache

        Args:
            max_size: Maximum number of summaries to cache
        """
        self._summaries: Dict[str, FunctionTaintSummary] = {}
        self._access_order: list[str] = []  # LRU tracking (most recent at end)
        self._max_size = max_size

        # Performance metrics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

        logger.info(f"FunctionSummaryCache initialized (max_size={max_size})")

    def get(self, function_id: str) -> Optional[FunctionTaintSummary]:
        """
        Get cached summary

        Args:
            function_id: Unique function identifier

        Returns:
            Cached summary or None if not found
        """
        if function_id in self._summaries:
            self._hits += 1

            # Update LRU (move to end)
            self._access_order.remove(function_id)
            self._access_order.append(function_id)

            return self._summaries[function_id]

        self._misses += 1
        return None

    def put(self, summary: FunctionTaintSummary):
        """
        Store summary with LRU eviction

        Args:
            summary: Function taint summary to cache
        """
        func_id = summary.function_id

        # Already exists - update
        if func_id in self._summaries:
            self._summaries[func_id] = summary
            # Move to end (most recently used)
            self._access_order.remove(func_id)
            self._access_order.append(func_id)
            return

        # Check capacity
        if len(self._summaries) >= self._max_size:
            # Evict LRU (first in list)
            oldest = self._access_order.pop(0)
            del self._summaries[oldest]
            self._evictions += 1
            logger.debug(f"Evicted function summary: {oldest}")

        # Add new
        self._summaries[func_id] = summary
        self._access_order.append(func_id)

    def invalidate(self, function_id: str):
        """
        Invalidate cached summary

        Use case: Code changed, need to re-analyze

        Args:
            function_id: Function to invalidate
        """
        if function_id in self._summaries:
            del self._summaries[function_id]
            self._access_order.remove(function_id)
            logger.debug(f"Invalidated function summary: {function_id}")

    def clear(self):
        """Clear all cached summaries"""
        self._summaries.clear()
        self._access_order.clear()
        logger.info("Function summary cache cleared")

    def get_stats(self) -> dict:
        """
        Get cache statistics

        Returns:
            Dict with hits, misses, hit_rate, etc.
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "evictions": self._evictions,
            "cache_size": len(self._summaries),
            "max_size": self._max_size,
        }

    def __len__(self):
        return len(self._summaries)

    def __contains__(self, function_id: str):
        return function_id in self._summaries


class TaintAnalyzerWithCache:
    """
    Taint analyzer with function summary caching

    Performance improvement:
        Without cache:
            - 1000 functions, each called 10 times
            - 10,000 analyses × 10ms = 100 seconds

        With cache:
            - 1000 analyses (misses) × 10ms = 10 seconds
            - 9,000 cache hits × 0.001ms = 0.009 seconds
            - Total: ~10 seconds (10x faster!)

    Usage:
        analyzer = TaintAnalyzerWithCache(base_analyzer, cache)

        # First call: Cache miss, analyze function
        result1 = analyzer.analyze_call(call_node1)  # Slow

        # Second call (same function): Cache hit!
        result2 = analyzer.analyze_call(call_node2)  # Fast!
    """

    def __init__(
        self,
        base_analyzer,
        summary_cache: Optional[FunctionSummaryCache] = None,
    ):
        """
        Initialize cached analyzer

        Args:
            base_analyzer: Underlying taint analyzer
            summary_cache: Function summary cache (created if None)
        """
        self.analyzer = base_analyzer
        self.cache = summary_cache or FunctionSummaryCache()

    def analyze_function_call(
        self,
        call_node,
        ir_doc,
        tainted_args: Set[int],
    ) -> bool:
        """
        Analyze function call with caching

        Args:
            call_node: AST/IR node for function call
            ir_doc: IR document
            tainted_args: Set of tainted argument indices

        Returns:
            True if return value is tainted

        Example:
            # Call: result = process(user_input, safe_data)
            #       where user_input is tainted (arg 0)

            tainted = analyzer.analyze_function_call(
                call_node,
                ir_doc,
                tainted_args={0},  # arg 0 is tainted
            )
            # Returns: True (if process propagates taint)
        """
        func_id = self._get_function_id(call_node, ir_doc)

        # Try cache first
        summary = self.cache.get(func_id)
        if summary:
            # Cache hit - fast path!
            return summary.is_tainted_call(tainted_args)

        # Cache miss - analyze and cache
        summary = self._analyze_and_cache(func_id, call_node, ir_doc)
        return summary.is_tainted_call(tainted_args)

    def get_or_analyze(
        self,
        function_id: str,
        analyzer_fn: Callable[[str], FunctionTaintSummary],
    ) -> FunctionTaintSummary:
        """
        Get cached summary or analyze

        Generic helper for custom analysis logic.

        Args:
            function_id: Unique function ID
            analyzer_fn: Function to call if cache miss

        Returns:
            Function summary
        """
        summary = self.cache.get(function_id)
        if summary:
            return summary

        # Analyze
        summary = analyzer_fn(function_id)
        self.cache.put(summary)
        return summary

    def _get_function_id(self, call_node, ir_doc) -> str:
        """
        Generate unique function ID

        Format: file_path:line:function_name:signature

        Args:
            call_node: Function call node
            ir_doc: IR document

        Returns:
            Unique function ID

        Example:
            "app/utils.py:42:escape_html:(str)->str"
        """
        func_name = self._extract_function_name(call_node)

        # Find function definition in IR
        func_def = self._find_function_def(func_name, ir_doc)
        if not func_def:
            # External function or not found
            return f"external:{func_name}"

        # Build ID
        file_path = getattr(ir_doc, "file_path", "unknown")
        line = getattr(func_def.location, "start_line", 0)
        signature = getattr(func_def, "signature", "unknown")

        return f"{file_path}:{line}:{func_name}:{signature}"

    def _analyze_and_cache(self, func_id, call_node, ir_doc) -> FunctionTaintSummary:
        """
        Analyze function and store in cache

        Args:
            func_id: Function ID
            call_node: Call node
            ir_doc: IR document

        Returns:
            Function summary
        """
        # Perform full taint analysis
        # TODO: Integrate with actual taint analyzer
        result = self._analyze_function_impl(func_id, call_node, ir_doc)

        # Create summary
        summary = FunctionTaintSummary(
            function_id=func_id,
            tainted_params=result.get("tainted_params", set()),
            tainted_return=result.get("return_tainted", False),
            tainted_globals=result.get("tainted_globals", set()),
            tainted_attributes=result.get("tainted_attrs", set()),
            sanitizes=result.get("is_sanitizer", False),
            confidence=result.get("confidence", 1.0),
            metadata=result.get("metadata", {}),
        )

        # Cache it
        self.cache.put(summary)

        logger.debug(f"Cached function summary: {func_id}")
        return summary

    def _analyze_function_impl(self, func_id, call_node, ir_doc) -> dict:
        """
        Actual function analysis implementation

        TODO: Integrate with existing TaintAnalyzer

        Returns:
            Dict with analysis results
        """
        # Placeholder implementation
        return {
            "tainted_params": set(),
            "return_tainted": False,
            "tainted_globals": set(),
            "tainted_attrs": set(),
            "is_sanitizer": False,
            "confidence": 1.0,
            "metadata": {},
        }

    def _extract_function_name(self, call_node):
        """Extract function name from call node"""
        # TODO: Handle different call types
        # - Simple: func()
        # - Attribute: obj.method()
        # - Nested: obj.attr.method()
        return getattr(call_node, "function_name", "unknown")

    def _find_function_def(self, func_name, ir_doc):
        """Find function definition in IR"""
        # TODO: Search IR for function definition
        return None

    def get_cache_stats(self) -> dict:
        """Get cache statistics"""
        return self.cache.get_stats()

    def clear_cache(self):
        """Clear function summary cache"""
        self.cache.clear()


# Convenience functions


def create_cached_analyzer(base_analyzer=None, max_cache_size: int = 10000):
    """
    Create taint analyzer with caching

    Args:
        base_analyzer: Base taint analyzer (optional)
        max_cache_size: Maximum cache entries

    Returns:
        TaintAnalyzerWithCache
    """
    cache = FunctionSummaryCache(max_size=max_cache_size)
    return TaintAnalyzerWithCache(base_analyzer, cache)
