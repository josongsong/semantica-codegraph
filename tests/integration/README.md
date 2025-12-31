# Retriever V3 Integration Tests

Integration tests for Retriever V3 with **real indexed data**, unlike unit tests which use mocks.

## Overview

These tests validate V3 retrieval against actual indexed codebases, testing:
- Real database connections (Postgres, Redis, Kuzu, Qdrant, Zoekt)
- Actual chunk indexing and retrieval
- End-to-end query flow
- Performance with real data
- P1 improvements (query expansion, intent boosting)

## Test Phases

### Phase 1: Small Scale ✅ (Current)
- **Repository**: `src/retriever` directory (~50 files)
- **Queries**: 10 representative queries
- **Duration**: ~5-10 seconds per test
- **Focus**: Core functionality validation

### Phase 2: Medium Scale (Planned)
- **Repository**: Full project (`src/` directory, ~500 files)
- **Queries**: All 41 scenario queries
- **Duration**: ~30-60 seconds per test
- **Focus**: Comprehensive scenario coverage

### Phase 3: Production Scale (Planned)
- **Repository**: External projects (Django, Flask, ~10,000 files)
- **Queries**: Real-world production queries
- **Duration**: ~2-5 minutes per test
- **Focus**: Production readiness validation

---

## Prerequisites

### 1. Required Services Running

All integration tests require the following services:

```bash
# PostgreSQL (chunk storage)
docker run -d -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres \
  postgres:15

# Redis (caching)
docker run -d -p 6379:6379 \
  redis:7

# Kuzu (graph storage + symbol index)
docker run -d -p 8000:8000 \
  kuzudb/kuzu:latest

# Qdrant (vector index)
docker run -d -p 6333:6333 \
  qdrant/qdrant:latest

# Zoekt (lexical index)
docker run -d -p 6070:6070 \
  sourcegraph/zoekt-webserver:latest
```

Or use docker-compose:

```bash
cd /path/to/codegraph
docker-compose up -d
```

### 2. Python Dependencies

```bash
pip install -e .
pip install pytest pytest-asyncio
```

---

## Running Integration Tests

### Run All Integration Tests

```bash
# Run all Phase 1 tests (small scale)
PYTHONPATH=. pytest tests/integration/test_v3_real_small.py -v --no-cov -m integration

# Expected output:
# - 10 query tests
# - 3 validation tests (explainability, consensus, expansion)
# - 2 performance tests
# Total: ~15 tests, ~60-120 seconds
```

### Run Specific Test

```bash
# Run single query test
PYTHONPATH=. pytest tests/integration/test_v3_real_small.py::TestV3IntegrationSmallScale::test_query_1_symbol_retriever_class -v

# Run performance tests only
PYTHONPATH=. pytest tests/integration/test_v3_real_small.py::TestV3IntegrationPerformance -v
```

### Skip Slow Tests

```bash
# Skip integration tests (they are marked as slow)
PYTHONPATH=. pytest tests/ -v --no-cov -m "not slow"
```

---

## Indexing Test Repository

Before running integration tests, the test repository must be indexed.

### Automatic Indexing

The `indexed_repo` fixture automatically indexes the repository on first run:

```python
@pytest.fixture(scope="session")
def indexed_repo(...) -> bool:
    """Ensure test repository is indexed before running tests."""
    # Checks if already indexed
    # If not, runs scripts/index_test_repo.py
```

### Manual Indexing

You can also index manually:

```bash
# Index src/retriever directory
python scripts/index_test_repo.py src/retriever

# Expected output:
# 🚀 Starting indexing of src/retriever
# 📂 Step 1: Loading files
#    ✅ Loaded 50 Python files
# 🧩 Step 2: Building chunks
#    ✅ Built 500 chunks
# 🕸️  Step 3: Building graph
#    ✅ Built graph with 200 nodes, 400 edges
# 📇 Step 4: Indexing into all indexes
#    ✅ Indexed 150 symbols
#    ✅ Indexed 500 vectors
#    ✅ Indexed 500 lexical entries
#    ✅ Indexed graph (200 nodes, 400 edges)
# ✅ Indexing complete!
```

---

## Test Structure

### Test File: `test_v3_real_small.py`

```python
@pytest.mark.integration
@pytest.mark.slow
class TestV3IntegrationSmallScale:
    """10 query tests + 3 validation tests."""

    def test_query_1_symbol_retriever_class(...):
        """Find RetrieverV3Service class."""
        # Tests: Symbol intent, exact class match

    def test_query_2_flow_who_calls(...):
        """Find callers of IntentClassifierV3."""
        # Tests: Flow intent, graph strategy, P1 flow boosting

    # ... 8 more query tests

    def test_explainability_features(...):
        """Validate explainability metadata."""
        # Tests: Strategies, consensus, weights, intent

    def test_consensus_boosting_applied(...):
        """Validate consensus boosting."""
        # Tests: Multi-strategy boost >= 1.15

    def test_p1_query_expansion_applied(...):
        """Validate P1 query expansion."""
        # Tests: Symbol/file path matching boost


@pytest.mark.integration
@pytest.mark.slow
class TestV3IntegrationPerformance:
    """2 performance tests."""

    def test_retrieval_latency_p50(...):
        """Measure p50 latency."""
        # Target: p50 < 500ms for real data

    def test_cache_effectiveness(...):
        """Validate cache speedup."""
        # Target: 20%+ speedup on repeated queries
```

### Fixtures: `conftest.py`

```python
@pytest.fixture(scope="session")
def container() -> Container:
    """DI container with real implementations."""

@pytest.fixture(scope="session")
def symbol_index(...) -> KuzuSymbolIndexAdapter:
    """Real Kuzu-based symbol index."""

@pytest.fixture(scope="session")
def vector_index(...) -> QdrantVectorIndexAdapter:
    """Real Qdrant-based vector index."""

@pytest.fixture(scope="session")
def lexical_index(...) -> ZoektLexicalIndexAdapter:
    """Real Zoekt-based lexical index."""

@pytest.fixture(scope="session")
def graph_store(...) -> KuzuGraphStore:
    """Real Kuzu-based graph store."""

@pytest.fixture(scope="session")
def retriever_v3_service(...) -> RetrieverV3Service:
    """V3 service with real indexes."""

@pytest.fixture(scope="session")
def indexed_repo(...) -> bool:
    """Ensure repository is indexed."""

@pytest.fixture
def golden_queries() -> dict:
    """10 golden queries with expected results."""
```

---

## Golden Query Dataset

10 representative queries covering all intent types:

| Query | Intent | Expected Symbols | Min Results |
|-------|--------|------------------|-------------|
| `find RetrieverV3Service class` | symbol | `class:RetrieverV3Service` | 1 |
| `who calls IntentClassifierV3` | flow | `class:RetrieverV3Service` | 1 |
| `how is fusion implemented` | code | `class:FusionEngineV3`, `func:fuse` | 2 |
| `weighted RRF normalization pattern` | concept | `class:RRFNormalizer` | 1 |
| `consensus boosting logic` | flow | `class:ConsensusEngine` | 2 |
| `intent classification with expansion` | symbol | `class:IntentClassifierV3` | 2 |
| `RetrieverV3Config dataclass` | symbol | `class:RetrieverV3Config` | 1 |
| `FusedResultV3 data model` | symbol | `class:FusedResultV3` | 1 |
| `feature vector generation for LTR` | code | `func:generate_feature_vectors` | 1 |
| `calculate intent-based weights` | code | `func:_calculate_intent_weights` | 1 |

---

## Expected Results

### Phase 1 Success Criteria

| Metric | Target | Status |
|--------|--------|--------|
| Test Pass Rate | 100% (15/15) | ⏳ Pending |
| Query Coverage | 10 representative queries | ✅ Ready |
| Intent Accuracy | 100% (correct dominant intent) | ⏳ Pending |
| p50 Latency | < 500ms | ⏳ Pending |
| Cache Speedup | > 20% | ⏳ Pending |
| P1 Features | Query expansion + intent boost | ⏳ Pending |

### Sample Output

```bash
tests/integration/test_v3_real_small.py::TestV3IntegrationSmallScale::test_query_1_symbol_retriever_class PASSED
✅ Query 1 passed: 10 results, intent=symbol

tests/integration/test_v3_real_small.py::TestV3IntegrationSmallScale::test_query_2_flow_who_calls PASSED
✅ Query 2 passed: 8 results, intent=flow, graph_weight=0.255

... (13 more tests)

📊 Performance metrics:
  - Queries: 10
  - p50: 285.34ms
  - Min: 142.67ms
  - Max: 421.89ms
✅ Performance test passed: p50 = 285.34ms

=============== 15 passed in 90.45s ===============
```

---

## Troubleshooting

### Services Not Running

```bash
# Error: Connection refused to Postgres/Redis/Kuzu/Qdrant/Zoekt
# Solution: Start all services
docker-compose up -d

# Verify services are running
docker-compose ps
```

### Indexing Failed

```bash
# Error: Failed to index repository
# Solution: Check service logs
docker-compose logs kuzu
docker-compose logs qdrant
docker-compose logs zoekt

# Retry indexing
python scripts/index_test_repo.py src/retriever
```

### Tests Timing Out

```bash
# Error: Tests taking too long
# Solution: Reduce test scope or check service performance
# Option 1: Run single test
PYTHONPATH=. pytest tests/integration/test_v3_real_small.py::TestV3IntegrationSmallScale::test_query_1_symbol_retriever_class -v

# Option 2: Check service health
curl http://localhost:6333/health  # Qdrant
curl http://localhost:6379/ping    # Redis
```

### Index Out of Date

```bash
# Error: Test fails due to stale index
# Solution: Re-index repository
python scripts/index_test_repo.py src/retriever --force

# Or clear all indexes
python scripts/clear_test_indexes.py
python scripts/index_test_repo.py src/retriever
```

---

## Next Steps

### Phase 2: Medium Scale
1. Index full `src/` directory (~500 files)
2. Run all 41 scenario queries
3. Validate against unit test expectations
4. Measure performance at scale

### Phase 3: Production Scale
1. Index external projects (Django, Flask)
2. Run production-like queries
3. Benchmark p50, p95, p99 latencies
4. Validate scalability and robustness

---

## Related Documentation

- [V3 Architecture](_RETRIEVER_V3_COMPLETE.md)
- [V3 Guide](_RETRIEVER_V3_GUIDE.md)
- [P1 Improvements](_RETRIEVER_V3_P1_IMPROVEMENTS_COMPLETE.md)
- [Performance Optimization](_RETRIEVER_V3_PERFORMANCE_OPTIMIZATION.md)
- [Unit Tests](../retriever/test_v3_scenarios.py)

---

**Status**: ✅ Phase 1 Setup Complete
**Last Updated**: 2025-11-25
**Next**: Run Phase 1 tests and validate
