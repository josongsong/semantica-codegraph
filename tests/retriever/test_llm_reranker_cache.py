"""
Tests for LLM Reranker with Caching

Verifies:
1. Cache hit/miss behavior
2. TTL expiration
3. Cache key generation
4. Performance improvement with cache
5. File-based persistent cache
"""

import asyncio
import tempfile
import time
from pathlib import Path

import pytest

from src.retriever.hybrid.llm_reranker import LLMScore
from src.retriever.hybrid.llm_reranker_cache import (
    CachedLLMReranker,
    FileBasedLLMScoreCache,
    InMemoryLLMScoreCache,
)


class MockLLMClient:
    """Mock LLM client for testing."""

    def __init__(self, delay_ms: int = 0):
        """
        Initialize mock LLM client.

        Args:
            delay_ms: Simulated LLM latency in milliseconds
        """
        self.delay_ms = delay_ms
        self.call_count = 0

    async def generate(self, prompt: str, max_tokens: int = 300) -> str:
        """Generate mock LLM response."""
        self.call_count += 1

        # Simulate LLM latency
        if self.delay_ms > 0:
            await asyncio.sleep(self.delay_ms / 1000.0)

        # Return mock JSON response
        return """{
            "match_quality": 0.8,
            "semantic_relevance": 0.7,
            "structural_fit": 0.9,
            "reasoning": "Good match for the query"
        }"""


@pytest.fixture
def mock_llm_client():
    """Mock LLM client with simulated latency."""
    return MockLLMClient(delay_ms=100)  # 100ms simulated LLM call


@pytest.fixture
def sample_candidates():
    """Sample candidates for testing."""
    return [
        {
            "chunk_id": "chunk:1",
            "content": "def calculate_sum(a, b): return a + b",
            "score": 0.9,
            "file_path": "math_utils.py",
            "chunk_type": "function",
        },
        {
            "chunk_id": "chunk:2",
            "content": "class Calculator: def add(self, x, y): return x + y",
            "score": 0.8,
            "file_path": "calculator.py",
            "chunk_type": "class",
        },
        {
            "chunk_id": "chunk:3",
            "content": "def multiply(x, y): return x * y",
            "score": 0.7,
            "file_path": "math_utils.py",
            "chunk_type": "function",
        },
    ]


def test_in_memory_cache_basic():
    """Test basic in-memory cache operations."""
    cache = InMemoryLLMScoreCache(maxsize=10, default_ttl=3600)

    # Cache should be empty
    assert len(cache) == 0
    assert cache.get("key:1") is None

    # Set cache
    score = LLMScore(
        match_quality=0.8,
        semantic_relevance=0.7,
        structural_fit=0.9,
        overall=0.8,
        reasoning="Test",
    )
    cache.set("key:1", score)

    # Cache hit
    cached = cache.get("key:1")
    assert cached is not None
    assert cached.score.match_quality == 0.8
    assert cached.score.semantic_relevance == 0.7
    assert cached.cache_version == "v1"

    # Cache size
    assert len(cache) == 1


def test_in_memory_cache_ttl():
    """Test TTL expiration."""
    cache = InMemoryLLMScoreCache(maxsize=10, default_ttl=1)  # 1 second TTL

    score = LLMScore(
        match_quality=0.8,
        semantic_relevance=0.7,
        structural_fit=0.9,
        overall=0.8,
        reasoning="Test",
    )

    # Set cache
    cache.set("key:1", score)
    assert cache.get("key:1") is not None

    # Wait for expiration
    time.sleep(1.1)

    # Should be expired
    assert cache.get("key:1") is None
    assert len(cache) == 0  # Should be removed


def test_in_memory_cache_eviction():
    """Test cache eviction when maxsize is reached."""
    cache = InMemoryLLMScoreCache(maxsize=2)

    score = LLMScore(0.8, 0.7, 0.9, 0.8, "Test")

    # Add 3 items (exceeds maxsize)
    for i in range(3):
        cache.set(f"key:{i}", score)

    # Cache should have only 2 items
    assert len(cache) == 2

    # First item should be evicted (FIFO)
    assert cache.get("key:0") is None
    assert cache.get("key:1") is not None
    assert cache.get("key:2") is not None


def test_file_based_cache():
    """Test file-based persistent cache."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = FileBasedLLMScoreCache(cache_dir=tmpdir, default_ttl=3600)

        score = LLMScore(
            match_quality=0.8,
            semantic_relevance=0.7,
            structural_fit=0.9,
            overall=0.8,
            reasoning="Test",
        )

        # Set cache
        cache.set("key:1", score)

        # Get cache
        cached = cache.get("key:1")
        assert cached is not None
        assert cached.score.match_quality == 0.8

        # Verify file exists
        cache_files = list(Path(tmpdir).glob("*.pkl"))
        assert len(cache_files) == 1

        # Clear cache
        cache.clear()
        cache_files = list(Path(tmpdir).glob("*.pkl"))
        assert len(cache_files) == 0


def test_file_based_cache_ttl():
    """Test file-based cache TTL expiration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = FileBasedLLMScoreCache(cache_dir=tmpdir, default_ttl=1)

        score = LLMScore(0.8, 0.7, 0.9, 0.8, "Test")

        # Set cache
        cache.set("key:1", score)
        assert cache.get("key:1") is not None

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired and file removed
        assert cache.get("key:1") is None
        cache_files = list(Path(tmpdir).glob("*.pkl"))
        assert len(cache_files) == 0


@pytest.mark.asyncio
async def test_cached_reranker_cache_hit(mock_llm_client, sample_candidates):
    """Test that cache improves performance and reduces LLM calls."""
    cache = InMemoryLLMScoreCache(maxsize=100)
    reranker = CachedLLMReranker(
        llm_client=mock_llm_client,
        cache=cache,
        top_k=3,
        llm_weight=0.3,
    )

    query = "calculate sum function"

    # First rerank - all cache misses
    start = time.time()
    results1 = await reranker.rerank(query, sample_candidates)
    duration1 = time.time() - start

    assert len(results1) == 3
    assert reranker.cache_misses == 3
    assert reranker.cache_hits == 0
    assert mock_llm_client.call_count == 3

    # Second rerank with same query - all cache hits
    start = time.time()
    results2 = await reranker.rerank(query, sample_candidates)
    duration2 = time.time() - start

    assert len(results2) == 3
    assert reranker.cache_hits == 3
    assert reranker.cache_misses == 3  # Still 3 from first rerank
    assert mock_llm_client.call_count == 3  # No new LLM calls!

    # Cache should be much faster (at least 5x)
    assert duration2 < duration1 / 5, f"Cache not faster: {duration1:.3f}s vs {duration2:.3f}s"

    # Results should be identical (same scores)
    for r1, r2 in zip(results1, results2):
        assert r1.chunk_id == r2.chunk_id
        assert abs(r1.final_score - r2.final_score) < 0.001


@pytest.mark.asyncio
async def test_cached_reranker_different_queries(mock_llm_client, sample_candidates):
    """Test that different queries result in cache misses."""
    cache = InMemoryLLMScoreCache(maxsize=100)
    reranker = CachedLLMReranker(
        llm_client=mock_llm_client,
        cache=cache,
        top_k=3,
    )

    # Query 1
    await reranker.rerank("calculate sum", sample_candidates)
    assert reranker.cache_misses == 3
    assert reranker.cache_hits == 0

    # Query 2 (different) - should miss cache
    await reranker.rerank("multiply numbers", sample_candidates)
    assert reranker.cache_misses == 6  # 3 more misses
    assert reranker.cache_hits == 0

    # Query 1 again - should hit cache
    await reranker.rerank("calculate sum", sample_candidates)
    assert reranker.cache_hits == 3
    assert reranker.cache_misses == 6


@pytest.mark.asyncio
async def test_cached_reranker_query_normalization(mock_llm_client, sample_candidates):
    """Test that query normalization enables cache hits for similar queries."""
    cache = InMemoryLLMScoreCache(maxsize=100)
    reranker = CachedLLMReranker(
        llm_client=mock_llm_client,
        cache=cache,
        top_k=3,
    )

    # Original query
    await reranker.rerank("Calculate Sum", sample_candidates)
    assert reranker.cache_misses == 3

    # Same query with different case/whitespace - should hit cache
    await reranker.rerank("calculate  sum", sample_candidates)
    assert reranker.cache_hits == 3  # Cache hit!
    assert reranker.cache_misses == 3  # No new misses


@pytest.mark.asyncio
async def test_cached_reranker_content_change_detection(mock_llm_client):
    """Test that cache detects content changes."""
    cache = InMemoryLLMScoreCache(maxsize=100)
    reranker = CachedLLMReranker(
        llm_client=mock_llm_client,
        cache=cache,
        top_k=2,
    )

    query = "test query"
    candidates_v1 = [
        {
            "chunk_id": "chunk:1",
            "content": "version 1 content",
            "score": 0.9,
            "file_path": "test.py",
            "chunk_type": "function",
        }
    ]

    # First rerank
    await reranker.rerank(query, candidates_v1)
    assert reranker.cache_misses == 1

    # Same chunk_id but different content - should miss cache
    candidates_v2 = [
        {
            "chunk_id": "chunk:1",
            "content": "version 2 content - changed!",
            "score": 0.9,
            "file_path": "test.py",
            "chunk_type": "function",
        }
    ]

    await reranker.rerank(query, candidates_v2)
    assert reranker.cache_misses == 2  # Cache miss due to content change
    assert reranker.cache_hits == 0


def test_cache_stats(mock_llm_client, sample_candidates):
    """Test cache statistics tracking."""
    cache = InMemoryLLMScoreCache(maxsize=100)
    reranker = CachedLLMReranker(
        llm_client=mock_llm_client,
        cache=cache,
        top_k=3,
    )

    # Initial stats
    stats = reranker.get_cache_stats()
    assert stats["cache_hits"] == 0
    assert stats["cache_misses"] == 0
    assert stats["hit_rate_pct"] == 0.0
    assert stats["total_requests"] == 0


@pytest.mark.asyncio
async def test_cache_stats_tracking(mock_llm_client, sample_candidates):
    """Test cache statistics tracking with actual reranking."""
    cache = InMemoryLLMScoreCache(maxsize=100)
    reranker = CachedLLMReranker(
        llm_client=mock_llm_client,
        cache=cache,
        top_k=3,
    )

    query = "test query"

    # First rerank - all misses
    await reranker.rerank(query, sample_candidates)
    stats = reranker.get_cache_stats()
    assert stats["cache_misses"] == 3
    assert stats["hit_rate_pct"] == 0.0

    # Second rerank - all hits
    await reranker.rerank(query, sample_candidates)
    stats = reranker.get_cache_stats()
    assert stats["cache_hits"] == 3
    assert stats["cache_misses"] == 3
    assert stats["hit_rate_pct"] == 50.0

    # Third rerank - all hits again
    await reranker.rerank(query, sample_candidates)
    stats = reranker.get_cache_stats()
    assert stats["cache_hits"] == 6
    assert stats["cache_misses"] == 3
    assert stats["hit_rate_pct"] == pytest.approx(66.67, rel=0.1)


def test_cache_key_generation(mock_llm_client):
    """Test cache key generation consistency."""
    reranker = CachedLLMReranker(llm_client=mock_llm_client)

    candidate1 = {
        "chunk_id": "chunk:1",
        "content": "test content",
        "score": 0.9,
    }

    candidate2 = {
        "chunk_id": "chunk:2",
        "content": "test content",
        "score": 0.9,
    }

    # Same query + same candidate → same key
    key1a = reranker._generate_cache_key("test query", candidate1)
    key1b = reranker._generate_cache_key("test query", candidate1)
    assert key1a == key1b

    # Same query + different chunk_id → different key
    key2 = reranker._generate_cache_key("test query", candidate2)
    assert key1a != key2

    # Different query + same candidate → different key
    key3 = reranker._generate_cache_key("different query", candidate1)
    assert key1a != key3

    # Query normalization (case/whitespace) → same key
    key4 = reranker._generate_cache_key("Test  Query", candidate1)
    assert key1a == key4  # Normalized to same key
