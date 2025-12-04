"""
Tests for Late Interaction with Embedding Cache

Verifies:
1. Cache hit/miss behavior
2. Performance improvement with cache
3. GPU acceleration (if available)
4. Quantization accuracy
"""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.retriever.hybrid.late_interaction import SimpleEmbeddingModel
from src.retriever.hybrid.late_interaction_cache import (
    FileBasedEmbeddingCache,
    InMemoryEmbeddingCache,
    OptimizedLateInteraction,
)


@pytest.fixture
def simple_model():
    """Simple embedding model for testing."""
    return SimpleEmbeddingModel(embedding_dim=128)


@pytest.fixture
def sample_chunks():
    """Sample chunks for testing."""
    return [
        {
            "chunk_id": "chunk:1",
            "content": "def calculate_sum(a, b): return a + b",
            "metadata": {"kind": "function"},
        },
        {
            "chunk_id": "chunk:2",
            "content": "class Calculator: def add(self, x, y): return x + y",
            "metadata": {"kind": "class"},
        },
        {
            "chunk_id": "chunk:3",
            "content": "def multiply(x, y): return x * y",
            "metadata": {"kind": "function"},
        },
    ]


def test_in_memory_cache_basic(simple_model):
    """Test basic in-memory cache operations."""
    cache = InMemoryEmbeddingCache(maxsize=10)

    # Cache should be empty
    assert len(cache) == 0
    assert cache.get("chunk:1") is None

    # Set cache
    embeddings = simple_model.encode_document("test content")
    cache.set("chunk:1", embeddings)

    # Cache hit
    cached = cache.get("chunk:1")
    assert cached is not None
    assert cached.chunk_id == "chunk:1"
    np.testing.assert_array_equal(cached.embeddings, embeddings)

    # Cache size
    assert len(cache) == 1


def test_in_memory_cache_eviction(simple_model):
    """Test cache eviction when maxsize is reached."""
    cache = InMemoryEmbeddingCache(maxsize=2)

    # Add 3 items (exceeds maxsize)
    for i in range(3):
        emb = simple_model.encode_document(f"content {i}")
        cache.set(f"chunk:{i}", emb)

    # Cache should have only 2 items
    assert len(cache) == 2

    # First item should be evicted (FIFO)
    assert cache.get("chunk:0") is None
    assert cache.get("chunk:1") is not None
    assert cache.get("chunk:2") is not None


def test_file_based_cache():
    """Test file-based persistent cache."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = FileBasedEmbeddingCache(cache_dir=tmpdir)

        # Set cache
        embeddings = np.random.randn(10, 128)
        cache.set("chunk:1", embeddings)

        # Get cache
        cached = cache.get("chunk:1")
        assert cached is not None
        np.testing.assert_array_almost_equal(cached.embeddings, embeddings)

        # Verify file exists
        cache_files = list(Path(tmpdir).glob("*.pkl"))
        assert len(cache_files) == 1

        # Clear cache
        cache.clear()
        cache_files = list(Path(tmpdir).glob("*.pkl"))
        assert len(cache_files) == 0


def test_optimized_late_interaction_cache_hit(simple_model, sample_chunks):
    """Test that cache improves performance."""
    cache = InMemoryEmbeddingCache(maxsize=100)
    search = OptimizedLateInteraction(
        embedding_model=simple_model,
        cache=cache,
        use_gpu=False,  # CPU for testing
    )

    query = "calculate sum function"

    # First search - all cache misses
    results1 = search.search(query, sample_chunks, top_k=3)
    assert len(results1) == 3
    assert search.cache_misses == 3
    assert search.cache_hits == 0

    # Second search - all cache hits
    results2 = search.search(query, sample_chunks, top_k=3)
    assert len(results2) == 3
    assert search.cache_hits == 3
    assert search.cache_misses == 3  # Still 3 from first search

    # Results should be identical
    for r1, r2 in zip(results1, results2):
        assert r1["chunk_id"] == r2["chunk_id"]
        assert abs(r1["score"] - r2["score"]) < 0.001


def test_optimized_late_interaction_precompute(simple_model, sample_chunks):
    """Test pre-computation of embeddings."""
    cache = InMemoryEmbeddingCache(maxsize=100)
    search = OptimizedLateInteraction(
        embedding_model=simple_model,
        cache=cache,
        use_gpu=False,
    )

    # Verify cache is empty initially
    assert len(cache) == 0
    assert len(search.cache) == 0

    # Pre-compute embeddings
    search.precompute_embeddings(sample_chunks)

    # Cache should have all chunks
    # Note: search.cache and cache should be the same object
    assert search.cache is cache, "Cache object mismatch"
    assert len(search.cache) == 3, f"Expected 3 chunks in cache, got {len(search.cache)}"
    assert len(cache) == 3

    # Search should have 100% cache hit rate
    query = "calculate function"
    results = search.search(query, sample_chunks, top_k=3)

    stats = search.get_cache_stats()
    assert stats["cache_hits"] == 3
    assert stats["cache_misses"] == 0
    assert stats["hit_rate_pct"] == 100.0


def test_optimized_late_interaction_quantization(simple_model, sample_chunks):
    """Test quantization accuracy."""
    # Without quantization
    cache_no_quant = InMemoryEmbeddingCache()
    search_no_quant = OptimizedLateInteraction(
        embedding_model=simple_model,
        cache=cache_no_quant,
        use_gpu=False,
        quantize=False,
    )

    # With quantization
    cache_quant = InMemoryEmbeddingCache()
    search_quant = OptimizedLateInteraction(
        embedding_model=simple_model,
        cache=cache_quant,
        use_gpu=False,
        quantize=True,
    )

    query = "calculate sum"

    # Get results from both
    results_no_quant = search_no_quant.search(query, sample_chunks, top_k=3)
    results_quant = search_quant.search(query, sample_chunks, top_k=3)

    # Ranking should be similar (might differ slightly due to quantization)
    # Check that top result is the same
    assert results_no_quant[0]["chunk_id"] == results_quant[0]["chunk_id"]

    # Scores should be close (within 5% due to quantization)
    score_diff = abs(results_no_quant[0]["score"] - results_quant[0]["score"]) / results_no_quant[0]["score"]
    assert score_diff < 0.05, f"Quantization error too large: {score_diff:.2%}"


def test_cache_stats(simple_model, sample_chunks):
    """Test cache statistics tracking."""
    cache = InMemoryEmbeddingCache(maxsize=100)
    search = OptimizedLateInteraction(
        embedding_model=simple_model,
        cache=cache,
        use_gpu=False,
    )

    # Initial stats
    stats = search.get_cache_stats()
    assert stats["cache_hits"] == 0
    assert stats["cache_misses"] == 0
    assert stats["hit_rate_pct"] == 0.0

    # First search - all misses
    search.search("test query", sample_chunks, top_k=3)
    stats = search.get_cache_stats()
    assert stats["cache_misses"] == 3
    assert stats["hit_rate_pct"] == 0.0

    # Second search - all hits
    search.search("another query", sample_chunks, top_k=3)
    stats = search.get_cache_stats()
    assert stats["cache_hits"] == 3
    assert stats["cache_misses"] == 3
    assert stats["hit_rate_pct"] == 50.0


@pytest.mark.skipif(
    not pytest.importorskip("torch", reason="torch not installed"),
    reason="Skipping GPU test - torch not available",
)
def test_gpu_acceleration_if_available(simple_model, sample_chunks):
    """Test GPU acceleration if available (optional test)."""
    try:
        import torch

        if not torch.cuda.is_available():
            pytest.skip("CUDA not available")

        cache = InMemoryEmbeddingCache()
        search_gpu = OptimizedLateInteraction(
            embedding_model=simple_model,
            cache=cache,
            use_gpu=True,
        )

        query = "calculate function"
        results = search_gpu.search(query, sample_chunks, top_k=3)

        # Should produce valid results
        assert len(results) == 3
        assert all(r["score"] > 0 for r in results)

    except ImportError:
        pytest.skip("torch not available")
