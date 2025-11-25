# Retriever V3 Integration Testing - Phase 1 Setup Complete

**Date**: 2025-11-25
**Status**: ✅ Setup Complete, Ready to Run
**Version**: V3.1.0
**Phase**: Phase 1 (Small Scale)

---

## 📊 Setup Overview

Phase 1 integration testing infrastructure has been fully implemented and is ready for execution.

### What Changed

**Before**:
- Only unit tests with mock data (41 scenarios)
- No real database integration
- No validation against actual indexed code

**After**:
- Complete integration test infrastructure
- Real database connections (5 services)
- Actual code indexing and retrieval
- 15 comprehensive integration tests
- Performance benchmarking

---

## 🎯 Phase 1 Scope

### Test Repository
- **Path**: `src/retriever` directory
- **Size**: ~50 Python files
- **Lines**: ~5,000 lines of code
- **Modules**: V3 service, intent classifier, fusion engine, models

### Test Queries
**10 Golden Queries**:
1. Symbol: "find RetrieverV3Service class"
2. Flow: "who calls IntentClassifierV3"
3. Code: "how is fusion implemented"
4. Concept: "weighted RRF normalization pattern"
5. Flow: "consensus boosting logic"
6. Symbol: "intent classification with expansion"
7. Symbol: "RetrieverV3Config dataclass"
8. Symbol: "FusedResultV3 data model"
9. Code: "feature vector generation for LTR"
10. Code: "calculate intent-based weights"

### Test Coverage
**15 Integration Tests**:
- 10 query tests (one per golden query)
- 3 feature validation tests (explainability, consensus, P1 expansion)
- 2 performance tests (latency, cache)

---

## 📂 Created Files

### 1. Test Configuration: `tests/integration/conftest.py`
**Purpose**: Pytest fixtures for real index clients

**Key Fixtures**:
```python
@pytest.fixture(scope="session")
def container() -> Container:
    """DI container with real implementations."""

@pytest.fixture(scope="session")
def symbol_index() -> KuzuSymbolIndexAdapter:
    """Real Kuzu-based symbol index."""

@pytest.fixture(scope="session")
def vector_index() -> QdrantVectorIndexAdapter:
    """Real Qdrant-based vector index."""

@pytest.fixture(scope="session")
def lexical_index() -> ZoektLexicalIndexAdapter:
    """Real Zoekt-based lexical index."""

@pytest.fixture(scope="session")
def graph_store() -> KuzuGraphStore:
    """Real Kuzu-based graph store."""

@pytest.fixture(scope="session")
def retriever_v3_service() -> RetrieverV3Service:
    """V3 service with real indexes."""

@pytest.fixture(scope="session")
def indexed_repo() -> bool:
    """Ensure repository is indexed before tests."""

@pytest.fixture
def golden_queries() -> dict[str, dict]:
    """10 golden queries with expected results."""
```

**Features**:
- Session-scoped fixtures (shared across tests)
- Automatic indexing via `indexed_repo` fixture
- Production-like V3 configuration with P1 improvements enabled
- Golden query dataset with expected intent and symbols

**Lines**: 140 lines

---

### 2. Integration Tests: `tests/integration/test_v3_real_small.py`
**Purpose**: 15 integration tests with real indexed data

**Test Classes**:

#### A. Query Tests (10 tests)
```python
class TestV3IntegrationSmallScale:
    def test_query_1_symbol_retriever_class(...):
        """Symbol intent: Find RetrieverV3Service class."""
        # Validates: Symbol intent, exact class match, top-1 accuracy

    def test_query_2_flow_who_calls(...):
        """Flow intent: Find callers of IntentClassifierV3."""
        # Validates: Flow intent, graph strategy, P1 flow boosting (1.3x)

    def test_query_3_code_fusion_implementation(...):
        """Code intent: Understand fusion implementation."""
        # Validates: Code intent, FusionEngineV3 class and methods

    # ... 7 more query tests
```

#### B. Feature Validation Tests (3 tests)
```python
    def test_explainability_features(...):
        """Validate explainability metadata in results."""
        # Validates: strategies, consensus, weights, intent_prob

    def test_consensus_boosting_applied(...):
        """Validate consensus boosting is working."""
        # Validates: Multi-strategy results have boost >= 1.15

    def test_p1_query_expansion_applied(...):
        """Validate P1 query expansion boosting."""
        # Validates: Symbol/file path matching, 10% boost applied
```

#### C. Performance Tests (2 tests)
```python
class TestV3IntegrationPerformance:
    def test_retrieval_latency_p50(...):
        """Measure p50 retrieval latency."""
        # Target: p50 < 500ms for real data

    def test_cache_effectiveness(...):
        """Validate cache speedup on repeated queries."""
        # Target: 20%+ speedup with warm cache
```

**Features**:
- Marked with `@pytest.mark.integration` and `@pytest.mark.slow`
- Comprehensive assertions (intent, symbols, strategies, weights)
- Performance benchmarking
- P1 improvements validation (expansion boost, intent boost)

**Lines**: 450 lines

---

### 3. Indexing Script: `scripts/index_test_repo.py`
**Purpose**: Index a repository into all indexes

**Usage**:
```bash
python scripts/index_test_repo.py src/retriever
```

**Steps**:
1. Load files from repository (*.py, skip tests and cache)
2. Build chunks using ChunkBuilder
3. Build graph using GraphBuilder
4. Index into symbol index (Kuzu)
5. Index into vector index (Qdrant)
6. Index into lexical index (Zoekt)
7. Store graph (Kuzu)
8. Print statistics

**Example Output**:
```
🚀 Starting indexing of src/retriever
   Repository ID: test_repo

📂 Step 1: Loading files from src/retriever
   ✅ Loaded 50 Python files

🧩 Step 2: Building chunks
   ✅ Built 500 chunks

🕸️  Step 3: Building graph
   ✅ Built graph with 200 nodes, 400 edges

📇 Step 4: Indexing into all indexes
   📍 Indexing into symbol index...
   ✅ Indexed 150 symbols
   🔢 Indexing into vector index...
   ✅ Indexed 500 vectors
   📝 Indexing into lexical index...
   ✅ Indexed 500 lexical entries
   🕸️  Indexing graph...
   ✅ Indexed graph (200 nodes, 400 edges)

✅ Indexing complete!

📊 Summary:
   - Files: 50
   - Chunks: 500
   - Symbols: 150
   - Vectors: 500
   - Lexical: 500
   - Graph nodes: 200
   - Graph edges: 400
```

**Features**:
- Async/await for efficient indexing
- Error handling per file (continues on errors)
- Progress reporting
- Statistics summary
- Executable script (`chmod +x`)

**Lines**: 180 lines

---

### 4. Documentation: `tests/integration/README.md`
**Purpose**: Complete guide for integration testing

**Sections**:
1. Overview (phases, scope)
2. Prerequisites (5 services, dependencies)
3. Running Integration Tests (commands, examples)
4. Indexing Test Repository (automatic + manual)
5. Test Structure (fixtures, test classes)
6. Golden Query Dataset (10 queries with expectations)
7. Expected Results (success criteria, sample output)
8. Troubleshooting (common issues, solutions)
9. Next Steps (Phase 2-3 plans)

**Lines**: 280 lines

---

### 5. Summary Document: `_RETRIEVER_V3_INTEGRATION_PHASE1_SETUP.md`
**Purpose**: This document

---

## 🚀 How to Run

### Step 1: Start Required Services

```bash
# Option A: Docker Compose (recommended)
cd /path/to/codegraph
docker-compose up -d

# Option B: Individual containers
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15
docker run -d -p 6379:6379 redis:7
docker run -d -p 8000:8000 kuzudb/kuzu:latest
docker run -d -p 6333:6333 qdrant/qdrant:latest
docker run -d -p 6070:6070 sourcegraph/zoekt-webserver:latest

# Verify services
docker-compose ps
```

### Step 2: Index Test Repository

```bash
# Manual indexing (recommended for first run)
python scripts/index_test_repo.py src/retriever

# Expected: 50 files → 500 chunks → 150 symbols
# Duration: ~30-60 seconds
```

### Step 3: Run Integration Tests

```bash
# Run all Phase 1 tests
PYTHONPATH=. pytest tests/integration/test_v3_real_small.py -v --no-cov -m integration

# Expected output:
# - 15 tests executed
# - Duration: ~60-120 seconds
# - All tests should pass (15/15)
```

### Step 4: Review Results

```bash
# Expected output format:
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

## 📈 Expected Metrics

### Success Criteria

| Metric | Target | Status |
|--------|--------|--------|
| **Test Pass Rate** | 100% (15/15) | ⏳ To be measured |
| **Intent Accuracy** | 100% (10/10) | ⏳ To be measured |
| **Symbol Precision** | 90%+ (top-5) | ⏳ To be measured |
| **p50 Latency** | < 500ms | ⏳ To be measured |
| **p95 Latency** | < 1000ms | ⏳ To be measured |
| **Cache Speedup** | > 20% | ⏳ To be measured |
| **P1 Expansion Boost** | Applied (10%) | ⏳ To be measured |
| **P1 Flow Boost** | Applied (1.3x) | ⏳ To be measured |
| **Consensus Boost** | Applied (1.15-1.30x) | ⏳ To be measured |

### Baseline Expectations

Based on unit test performance (mock data):
- **Unit tests**: ~0.024s per scenario (mock)
- **Integration tests**: ~6s per scenario (real data, expected 250x slower)
- **Reason**: Real DB queries, embedding generation, graph traversal

**Expected Integration Test Performance**:
- Single query: ~5-10 seconds
- 10 queries: ~60 seconds
- 15 total tests: ~90-120 seconds

---

## 🔍 What Gets Validated

### 1. Core V3 Features
- ✅ Multi-label intent classification (5 intents)
- ✅ Multi-strategy fusion (vec, lex, sym, graph)
- ✅ Weighted RRF with strategy-specific k values
- ✅ Consensus-aware boosting (1.22-1.30x)
- ✅ Graph integration (runtime data flow)

### 2. P1 Improvements
- ✅ Query expansion utilization (10% boost)
- ✅ Flow intent non-linear boosting (1.3x graph weight)
- ✅ Symbol intent non-linear boosting (1.2x symbol weight)

### 3. Explainability Features
- ✅ Strategy list populated
- ✅ Consensus info available
- ✅ Weight profile calculated
- ✅ Intent probabilities provided
- ✅ Feature vectors generated

### 4. Performance
- ✅ Latency within acceptable range (< 500ms p50)
- ✅ Cache effectiveness (> 20% speedup)
- ✅ Throughput (10 queries in ~60s)

---

## 🎯 Next Steps

### Immediate (Week 1)
1. **Run Phase 1 Tests** ⏳
   - Start required services
   - Index test repository
   - Execute all 15 integration tests
   - Validate results against success criteria

2. **Document Results** ⏳
   - Create `_RETRIEVER_V3_INTEGRATION_PHASE1_RESULTS.md`
   - Include actual metrics (intent accuracy, latency, cache hit rate)
   - Compare against unit test performance
   - Identify any gaps or issues

### Short-term (Month 1)
3. **Phase 2: Medium Scale** ⏳
   - Index full `src/` directory (~500 files)
   - Run all 41 scenario queries
   - Validate against unit test expectations
   - Measure performance at scale

4. **Phase 3: Production Scale** ⏳
   - Index external projects (Django, Flask, ~10,000 files)
   - Run production-like queries
   - Benchmark p50, p95, p99 latencies
   - Validate scalability and robustness

---

## 📊 File Summary

| File | Lines | Purpose |
|------|-------|---------|
| `tests/integration/conftest.py` | 140 | Pytest fixtures for real indexes |
| `tests/integration/test_v3_real_small.py` | 450 | 15 integration tests |
| `scripts/index_test_repo.py` | 180 | Repository indexing script |
| `tests/integration/README.md` | 280 | Complete integration test guide |
| `_RETRIEVER_V3_INTEGRATION_PHASE1_SETUP.md` | 420 | This summary document |
| **Total** | **1,470** | **Phase 1 infrastructure** |

---

## ✅ Completion Checklist

### Setup ✅
- [x] Create integration test directory structure
- [x] Implement pytest fixtures for real indexes
- [x] Create 15 comprehensive integration tests
- [x] Write repository indexing script
- [x] Document setup and usage

### Ready to Run ⏳
- [ ] Start required services (Postgres, Redis, Kuzu, Qdrant, Zoekt)
- [ ] Index test repository (`src/retriever`)
- [ ] Run integration tests
- [ ] Validate results
- [ ] Document findings

### Phase 1 Complete ⏳
- [ ] 15/15 tests passing
- [ ] Intent accuracy 100%
- [ ] P1 improvements validated
- [ ] Performance metrics documented
- [ ] Phase 2 planning

---

## 🎉 Success Metrics

### Setup Completion (Current)
- ✅ **Infrastructure**: Complete (1,470 lines)
- ✅ **Test Coverage**: 15 integration tests ready
- ✅ **Documentation**: Comprehensive guide
- ✅ **Automation**: Indexing script + auto-indexing fixture

### Execution (Next)
- ⏳ **Test Pass Rate**: Target 100% (15/15)
- ⏳ **Intent Accuracy**: Target 100% (10/10)
- ⏳ **Performance**: Target p50 < 500ms
- ⏳ **P1 Features**: All validated

---

## 📚 Related Documentation

- [V3 Final Summary](_RETRIEVER_V3_FINAL_SUMMARY.md)
- [P1 Improvements](_RETRIEVER_V3_P1_IMPROVEMENTS_COMPLETE.md)
- [Performance Optimization](_RETRIEVER_V3_PERFORMANCE_OPTIMIZATION.md)
- [Production Checklist](_RETRIEVER_V3_PRODUCTION_CHECKLIST.md)
- [Unit Tests](tests/retriever/test_v3_scenarios.py)

---

**Generated**: 2025-11-25
**Status**: ✅ PHASE 1 SETUP COMPLETE
**Ready For**: Integration Test Execution
**Next**: Start services → Index repository → Run tests

---

## 🚦 Quick Start Command

```bash
# Complete Phase 1 execution in 3 commands:

# 1. Start services
docker-compose up -d

# 2. Index test repository
python scripts/index_test_repo.py src/retriever

# 3. Run integration tests
PYTHONPATH=. pytest tests/integration/test_v3_real_small.py -v --no-cov -m integration

# Expected: 15 passed in ~90-120 seconds
```
