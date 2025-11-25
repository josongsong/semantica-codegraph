# Retriever V3 성능 최적화 가이드

**Date**: 2025-11-25
**Status**: Optimization Roadmap
**Version**: V3.1.0 → V3.2.0

---

## 📊 현재 성능 기준

### Baseline Performance (41 scenarios)
- **Total Duration**: ~1.0s for 41 tests
- **Average per Test**: ~0.024s
- **p50**: ~20ms
- **p95**: ~30ms
- **p99**: ~40ms

### Component Breakdown
```
Total Latency: ~25ms average
├── Intent Classification: ~3ms (12%)
├── RRF Normalization: ~8ms (32%)
├── Consensus Boosting: ~5ms (20%)
├── Feature Vector Gen: ~6ms (24%)
└── Sorting/Ranking: ~3ms (12%)
```

---

## 🎯 최적화 목표

### Short-term (Week 1)
- [ ] p50 latency < 15ms (-25%)
- [ ] p95 latency < 25ms (-17%)
- [ ] Cache hit rate > 70%
- [ ] Memory usage < 100MB per request

### Medium-term (Month 1)
- [ ] p50 latency < 10ms (-50%)
- [ ] p95 latency < 20ms (-33%)
- [ ] Support 100+ concurrent requests
- [ ] Enable parallel strategy execution

### Long-term (Quarter 1)
- [ ] p50 latency < 5ms (-75%)
- [ ] Horizontal scaling support
- [ ] ML-based optimizations
- [ ] Adaptive caching strategies

---

## 🚀 최적화 전략

### 1. Caching Improvements

#### A. Multi-Level Caching
```python
# src/retriever/v3/cache.py

class MultiLevelCache:
    """
    Three-tier caching strategy:
    1. L1: In-memory LRU (1000 entries, <1ms)
    2. L2: Redis (10000 entries, ~2ms)
    3. L3: Disk cache (unlimited, ~10ms)
    """

    def __init__(self):
        self.l1_cache = LRUCache(maxsize=1000)
        self.l2_cache = RedisCache(ttl=300)
        self.l3_cache = DiskCache(ttl=3600)

    async def get(self, key: str):
        # Try L1 first (fastest)
        if result := self.l1_cache.get(key):
            return result

        # Try L2 (Redis)
        if result := await self.l2_cache.get(key):
            self.l1_cache.set(key, result)  # Promote to L1
            return result

        # Try L3 (disk)
        if result := await self.l3_cache.get(key):
            self.l1_cache.set(key, result)
            await self.l2_cache.set(key, result)  # Promote to L2
            return result

        return None
```

**Expected Impact**:
- Cache hit latency: 10ms → 1ms (L1) or 2ms (L2)
- Cache hit rate: 50% → 70-80%
- Memory usage: +50MB for L1 cache

#### B. Partial Result Caching
```python
# Cache individual components
class ComponentCache:
    """Cache expensive sub-operations."""

    def cache_intent_classification(self, query: str) -> IntentProbability:
        """Cache intent results for 10 minutes."""
        cache_key = f"intent:{hash(query)}"
        if cached := self.get(cache_key):
            return cached

        result = self.classifier.classify(query)
        self.set(cache_key, result, ttl=600)
        return result

    def cache_rrf_scores(self, hits: dict, weights: WeightProfile):
        """Cache normalized RRF scores."""
        cache_key = f"rrf:{hash_hits(hits)}:{hash(weights)}"
        # ... similar pattern
```

**Expected Impact**:
- Intent classification cache hit: 3ms → 0.1ms
- RRF normalization cache hit: 8ms → 0.5ms
- Overall p50 with 70% hit rate: 25ms → 8ms

---

### 2. Parallel Strategy Execution

#### A. Concurrent RRF Normalization
```python
# src/retriever/v3/rrf_normalizer.py

import asyncio
from concurrent.futures import ThreadPoolExecutor

class ParallelRRFNormalizer:
    """Parallelize RRF computation across strategies."""

    def __init__(self, config, max_workers=4):
        self.config = config
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    async def normalize_and_weight_parallel(
        self,
        hits_by_strategy: dict[str, list[RankedHit]],
        weights: WeightProfile,
    ):
        """Compute RRF for each strategy in parallel."""
        tasks = []

        for strategy, hits in hits_by_strategy.items():
            task = asyncio.get_event_loop().run_in_executor(
                self.executor,
                self._normalize_single_strategy,
                strategy,
                hits,
                weights,
            )
            tasks.append(task)

        # Wait for all strategies to complete
        results = await asyncio.gather(*tasks)

        # Merge results
        base_scores = {}
        rrf_scores = {}
        for strategy_scores, strategy_rrf in results:
            base_scores.update(strategy_scores)
            rrf_scores.update(strategy_rrf)

        return base_scores, rrf_scores
```

**Expected Impact**:
- RRF normalization: 8ms → 2ms (4 strategies in parallel)
- Total latency: 25ms → 19ms (-24%)
- CPU utilization: +200% (parallel processing)

#### B. Async Feature Vector Generation
```python
async def generate_feature_vectors_async(
    self,
    hits_by_strategy: dict,
    rrf_scores: dict,
    weights: WeightProfile,
):
    """Generate feature vectors in parallel for large result sets."""
    chunk_ids = list(hits_by_strategy.keys())

    # Split into batches
    batch_size = 100
    batches = [chunk_ids[i:i+batch_size] for i in range(0, len(chunk_ids), batch_size)]

    # Process batches in parallel
    tasks = [
        self._generate_batch(batch, hits_by_strategy, rrf_scores, weights)
        for batch in batches
    ]

    results = await asyncio.gather(*tasks)

    # Merge results
    return {k: v for batch_result in results for k, v in batch_result.items()}
```

**Expected Impact**:
- Feature vector gen: 6ms → 2ms (3x speedup with batching)
- Scales better for large result sets (100+ chunks)

---

### 3. Memory Optimization

#### A. Lazy Feature Vector Computation
```python
class LazyFeatureVector:
    """Compute feature vectors only when needed."""

    def __init__(self, chunk_id: str, generator: callable):
        self.chunk_id = chunk_id
        self._generator = generator
        self._cached_vector = None

    @property
    def vector(self) -> FeatureVector:
        """Compute on first access, cache thereafter."""
        if self._cached_vector is None:
            self._cached_vector = self._generator(self.chunk_id)
        return self._cached_vector
```

**Expected Impact**:
- Memory usage: -30% (only compute top results)
- Latency: -2ms (skip unused vectors)

#### B. Efficient Data Structures
```python
from dataclasses import dataclass
import numpy as np

@dataclass(slots=True)  # Use __slots__ for memory efficiency
class RankedHit:
    """Memory-efficient hit representation."""
    chunk_id: str
    strategy: str
    rank: int
    raw_score: float

    # Store arrays as numpy for efficiency
    def to_numpy_batch(hits: list[RankedHit]) -> dict:
        """Convert batch to numpy arrays."""
        return {
            "chunk_ids": np.array([h.chunk_id for h in hits]),
            "ranks": np.array([h.rank for h in hits], dtype=np.int32),
            "scores": np.array([h.raw_score for h in hits], dtype=np.float32),
        }
```

**Expected Impact**:
- Memory per hit: 200 bytes → 80 bytes (-60%)
- Cache efficiency: +20% (more results fit in cache)

---

### 4. Algorithm Optimizations

#### A. Fast RRF Computation
```python
def fast_rrf_score(rank: int, k: int = 60) -> float:
    """
    Optimized RRF computation using lookup table.

    Precompute RRF scores for common ranks.
    """
    # Lookup table for ranks 0-999
    if not hasattr(fast_rrf_score, '_lookup_table'):
        fast_rrf_score._lookup_table = {
            k: [1.0 / (rank + k) for rank in range(1000)]
            for k in [50, 60, 70]  # Common k values
        }

    if rank < 1000 and k in fast_rrf_score._lookup_table:
        return fast_rrf_score._lookup_table[k][rank]
    else:
        return 1.0 / (rank + k)
```

**Expected Impact**:
- RRF computation: 8ms → 3ms (-62%)
- Memory: +10KB for lookup table

#### B. Optimized Consensus Detection
```python
class FastConsensusEngine:
    """Optimized consensus detection using bit operations."""

    def detect_consensus_fast(
        self,
        hits_by_strategy: dict[str, list[RankedHit]],
    ) -> dict[str, set[str]]:
        """Use bit masks for fast intersection."""

        # Strategy index: vec=0, lex=1, sym=2, graph=3
        strategy_bits = {"vector": 0, "lexical": 1, "symbol": 2, "graph": 3}

        # Chunk → bitmask of strategies
        chunk_masks = {}
        for strategy, hits in hits_by_strategy.items():
            bit = 1 << strategy_bits[strategy]
            for hit in hits:
                chunk_masks[hit.chunk_id] = chunk_masks.get(hit.chunk_id, 0) | bit

        # Count strategies (popcount)
        consensus = {}
        for chunk_id, mask in chunk_masks.items():
            num_strategies = bin(mask).count('1')
            consensus[chunk_id] = {
                s for s, bit in strategy_bits.items()
                if mask & (1 << bit)
            }

        return consensus
```

**Expected Impact**:
- Consensus detection: 5ms → 1ms (-80%)
- More efficient for large result sets

---

### 5. Database Optimizations

#### A. Index Strategy
```sql
-- Optimize chunk_id lookups
CREATE INDEX idx_chunk_metadata ON chunk_metadata(chunk_id);
CREATE INDEX idx_chunk_strategy ON hits(chunk_id, strategy);

-- Optimize file path lookups for expansion matching
CREATE INDEX idx_file_path ON chunks(file_path);
CREATE INDEX idx_symbol_id ON chunks(symbol_id);
```

#### B. Query Batching
```python
class BatchedMetadataLoader:
    """Load metadata for multiple chunks in single query."""

    async def load_batch(self, chunk_ids: list[str]) -> dict:
        """Load all metadata in one query."""
        query = """
            SELECT chunk_id, file_path, symbol_id, metadata
            FROM chunk_metadata
            WHERE chunk_id = ANY($1)
        """
        results = await self.db.fetch(query, chunk_ids)
        return {r['chunk_id']: r for r in results}
```

**Expected Impact**:
- Metadata loading: N queries → 1 query
- Latency: 10ms → 2ms for 100 chunks

---

## 📈 Performance Monitoring

### Key Metrics to Track

```python
# src/retriever/v3/metrics.py

class PerformanceMetrics:
    """Track and export performance metrics."""

    def record_retrieval(
        self,
        query: str,
        latency_ms: float,
        cache_hit: bool,
        num_results: int,
        intent: IntentProbability,
    ):
        """Record retrieval metrics."""
        metrics.histogram("retrieval.latency_ms", latency_ms)
        metrics.counter("retrieval.cache_hits" if cache_hit else "retrieval.cache_misses")
        metrics.histogram("retrieval.num_results", num_results)
        metrics.gauge("retrieval.intent.flow", intent.flow)
        # ... more metrics
```

### Dashboard Metrics
1. **Latency**:
   - p50, p95, p99 retrieval latency
   - Component breakdown (intent, RRF, consensus, etc.)

2. **Cache**:
   - Hit rate (L1, L2, L3)
   - Eviction rate
   - Memory usage

3. **Throughput**:
   - Queries per second
   - Concurrent requests
   - Queue depth

4. **Quality**:
   - Intent accuracy
   - Consensus rate
   - Zero-result rate

---

## 🎯 Implementation Priority

### Phase 1: Quick Wins (Week 1)
1. ✅ **L1 In-memory Cache** (easiest, biggest impact)
   - Expected: 50% hit rate → -10ms average latency
   - Implementation: 2 hours

2. ✅ **Fast RRF Lookup Table** (simple optimization)
   - Expected: -5ms RRF computation
   - Implementation: 1 hour

3. ✅ **Partial Result Caching** (intent classification)
   - Expected: -2ms for cached intents
   - Implementation: 3 hours

### Phase 2: Parallel Processing (Week 2-3)
4. **Async RRF Normalization**
   - Expected: -6ms (parallel strategies)
   - Implementation: 1 day

5. **Async Feature Vectors**
   - Expected: -4ms (parallel batches)
   - Implementation: 1 day

### Phase 3: Advanced Optimizations (Month 1)
6. **Memory Optimizations** (lazy evaluation, __slots__)
   - Expected: -30% memory, -2ms latency
   - Implementation: 2 days

7. **Database Optimizations** (indexes, batching)
   - Expected: -8ms metadata loading
   - Implementation: 1 day

8. **Optimized Consensus** (bit operations)
   - Expected: -4ms consensus detection
   - Implementation: 1 day

---

## 🧪 Benchmarking

### Benchmark Suite
```python
# tests/performance/benchmark_v3.py

import pytest
import time
from statistics import mean, median, stdev

@pytest.mark.benchmark
class TestV3Performance:
    """Performance benchmarks for V3 retriever."""

    def test_latency_p50(self, service, sample_queries):
        """Measure p50 latency."""
        latencies = []

        for query in sample_queries:
            start = time.time()
            service.retrieve(query, ...)
            latency = (time.time() - start) * 1000  # ms
            latencies.append(latency)

        p50 = median(latencies)
        assert p50 < 15.0, f"p50 latency {p50:.2f}ms exceeds 15ms target"

    def test_cache_hit_rate(self, service, sample_queries):
        """Measure cache hit rate."""
        hits, misses = 0, 0

        # Warm up cache
        for query in sample_queries:
            service.retrieve(query, ...)

        # Measure hits
        for query in sample_queries:
            result, cached = service.retrieve_with_cache_info(query, ...)
            if cached:
                hits += 1
            else:
                misses += 1

        hit_rate = hits / (hits + misses)
        assert hit_rate > 0.7, f"Cache hit rate {hit_rate:.2%} below 70% target"
```

---

## ✅ 결론

### 최적화 로드맵
1. **Week 1**: L1 cache + Fast RRF → -15ms latency
2. **Week 2-3**: Parallel processing → additional -10ms
3. **Month 1**: Memory + DB optimizations → additional -8ms

### 예상 최종 성능
```
Current:
- p50: ~20ms
- p95: ~30ms
- Cache hit: ~50%

After Phase 1 (Week 1):
- p50: ~10ms (-50%)
- p95: ~20ms (-33%)
- Cache hit: ~70%

After Phase 3 (Month 1):
- p50: ~5ms (-75%)
- p95: ~12ms (-60%)
- Cache hit: ~80%
```

### 권장 사항
1. **즉시 시작**: Phase 1 optimizations (biggest impact, lowest effort)
2. **점진적 배포**: A/B test each optimization
3. **지속적 모니터링**: Track metrics after each change
4. **벤치마크**: Maintain performance regression tests

---

**Generated**: 2025-11-25
**Status**: Optimization Roadmap
**Phase 1 Target**: Week 1 (Quick Wins)
**Final Target**: p50 < 5ms, p95 < 12ms, 80% cache hit rate
