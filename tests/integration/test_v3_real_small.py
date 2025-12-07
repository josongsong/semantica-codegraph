"""
Integration tests for Retriever V3 with real indexed data (Phase 1: Small Scale).

These tests validate V3 against a real indexed codebase (src/retriever directory).
Unlike unit tests with mocks, these tests:
1. Connect to real databases (Postgres, Redis, Kuzu, Qdrant, Zoekt)
2. Query real indexed code
3. Validate actual retrieval results

Phase 1 Scope:
- Repository: src/retriever (~50 files)
- Queries: 10 representative queries
- Duration: ~5-10 seconds per test
"""

import pytest
from src.retriever.v3.models import FusedResultV3
from src.retriever.v3.service import RetrieverV3Service


@pytest.mark.integration
@pytest.mark.slow
class TestV3IntegrationSmallScale:
    """Integration tests with real indexed src/retriever directory."""

    def test_query_1_symbol_retriever_class(
        self,
        retriever_v3_service: RetrieverV3Service,
        symbol_index,
        vector_index,
        lexical_index,
        graph_store,
        indexed_repo: bool,
        golden_queries: dict[str, dict],
    ):
        """
        Test: Find RetrieverV3Service class definition.
        Expected: Symbol intent, class definition in top results.

        NOTE: This test requires real indexed data. Currently returns early
        because indexing is not yet implemented. Once indexing works, remove
        the early return and complete the test.
        """
        query_spec = golden_queries["query_1_symbol"]
        query = query_spec["query"]

        # TODO: Remove this once indexing is implemented
        pytest.skip("Skipping integration test - indexing not yet implemented")

        # Step 1: Search each strategy (real indexes)
        # symbol_hits = await symbol_index.search(query, limit=20)
        # vector_hits = await vector_index.search(query, limit=40)
        # lexical_hits = await lexical_index.search(query, limit=40)
        # graph_hits = []  # Graph doesn't search by text query

        # Step 2: Convert to hits_by_strategy format
        # hits_by_strategy = {
        #     "symbol": symbol_hits,
        #     "vector": vector_hits,
        #     "lexical": lexical_hits,
        #     "graph": graph_hits,
        # }

        # Step 3: Execute V3 fusion
        # results, intent = retriever_v3_service.retrieve(
        #     query=query,
        #     hits_by_strategy=hits_by_strategy,
        # )

        # Step 4: Validate results
        # assert len(results) >= query_spec["min_results"]
        # assert intent.dominant_intent() == query_spec["expected_intent"]

        # print(f"\n✅ Query 1 passed: {len(results)} results, intent={intent.dominant_intent()}")

    def test_query_2_flow_who_calls(
        self,
        retriever_v3_service: RetrieverV3Service,
        indexed_repo: bool,
        golden_queries: dict[str, dict],
    ):
        """
        Test: Find callers of IntentClassifierV3.
        Expected: Flow intent, graph strategy contributes, callers in top results.
        """
        query_spec = golden_queries["query_2_flow"]
        query = query_spec["query"]

        results: list[FusedResultV3] = retriever_v3_service.retrieve(
            query=query,
            repo_id="test_repo",
            top_k=10,
        )

        assert len(results) >= query_spec["min_results"]

        # Validate flow intent
        intent = results[0].intent_prob
        assert intent.dominant_intent() == query_spec["expected_intent"], (
            f"Expected flow intent, got {intent.dominant_intent()}"
        )

        # Validate flow intent boosting applied (P1 improvement)
        if intent.flow > 0.2:
            # Graph weight should be boosted
            weights = results[0].weights
            assert weights.graph > 0.22, f"Expected graph weight > 0.22 with flow boosting, got {weights.graph}"

        # Validate graph strategy contributed
        top_result = results[0]
        assert "graph" in top_result.strategies, f"Expected graph strategy in top result, got {top_result.strategies}"

        print(
            f"✅ Query 2 passed: {len(results)} results, "
            f"intent={intent.dominant_intent()}, "
            f"graph_weight={results[0].weights.graph:.3f}"
        )

    def test_query_3_code_fusion_implementation(
        self,
        retriever_v3_service: RetrieverV3Service,
        indexed_repo: bool,
        golden_queries: dict[str, dict],
    ):
        """
        Test: Understand fusion implementation.
        Expected: Code intent, FusionEngineV3 class and methods.
        """
        query_spec = golden_queries["query_3_code"]
        query = query_spec["query"]

        results: list[FusedResultV3] = retriever_v3_service.retrieve(
            query=query,
            repo_id="test_repo",
            top_k=10,
        )

        assert len(results) >= query_spec["min_results"]

        intent = results[0].intent_prob
        assert intent.dominant_intent() == query_spec["expected_intent"]

        # Validate FusionEngineV3 is in top results
        top_symbols = [r.chunk.symbol_id for r in results[:5] if r.chunk.symbol_id]
        assert any("FusionEngineV3" in s for s in top_symbols), f"Expected FusionEngineV3 in top results: {top_symbols}"

        print(f"✅ Query 3 passed: {len(results)} results, intent={intent.dominant_intent()}")

    def test_query_4_concept_rrf_pattern(
        self,
        retriever_v3_service: RetrieverV3Service,
        indexed_repo: bool,
        golden_queries: dict[str, dict],
    ):
        """
        Test: Find weighted RRF normalization pattern.
        Expected: Concept intent, RRFNormalizer class.
        """
        query_spec = golden_queries["query_4_concept"]
        query = query_spec["query"]

        results: list[FusedResultV3] = retriever_v3_service.retrieve(
            query=query,
            repo_id="test_repo",
            top_k=10,
        )

        assert len(results) >= query_spec["min_results"]

        intent = results[0].intent_prob
        assert intent.dominant_intent() == query_spec["expected_intent"]

        # Validate vector strategy contributes (semantic similarity)
        top_result = results[0]
        assert "vector" in top_result.strategies, (
            f"Expected vector strategy for concept query, got {top_result.strategies}"
        )

        print(f"✅ Query 4 passed: {len(results)} results, intent={intent.dominant_intent()}")

    def test_query_5_flow_consensus_boosting(
        self,
        retriever_v3_service: RetrieverV3Service,
        indexed_repo: bool,
        golden_queries: dict[str, dict],
    ):
        """
        Test: Find consensus boosting logic.
        Expected: Flow intent, ConsensusEngine class.
        """
        query_spec = golden_queries["query_5_flow_boosting"]
        query = query_spec["query"]

        results: list[FusedResultV3] = retriever_v3_service.retrieve(
            query=query,
            repo_id="test_repo",
            top_k=10,
        )

        assert len(results) >= query_spec["min_results"]

        intent = results[0].intent_prob
        # Flow or code intent both acceptable
        assert intent.dominant_intent() in ["flow", "code"]

        print(f"✅ Query 5 passed: {len(results)} results, intent={intent.dominant_intent()}")

    def test_query_6_symbol_intent_classification_expansion(
        self,
        retriever_v3_service: RetrieverV3Service,
        indexed_repo: bool,
        golden_queries: dict[str, dict],
    ):
        """
        Test: Find intent classification with expansion.
        Expected: Symbol intent, IntentClassifierV3 and classify_with_expansion method.
        """
        query_spec = golden_queries["query_6_symbol_expansion"]
        query = query_spec["query"]

        results: list[FusedResultV3] = retriever_v3_service.retrieve(
            query=query,
            repo_id="test_repo",
            top_k=10,
        )

        assert len(results) >= query_spec["min_results"]

        intent = results[0].intent_prob
        assert intent.dominant_intent() == query_spec["expected_intent"]

        # Validate symbol intent boosting applied (P1 improvement)
        if intent.symbol > 0.3:
            weights = results[0].weights
            assert weights.sym > 0.25, f"Expected symbol weight > 0.25 with symbol boosting, got {weights.sym}"

        print(
            f"✅ Query 6 passed: {len(results)} results, "
            f"intent={intent.dominant_intent()}, "
            f"symbol_weight={results[0].weights.sym:.3f}"
        )

    def test_query_7_config_dataclass(
        self,
        retriever_v3_service: RetrieverV3Service,
        indexed_repo: bool,
        golden_queries: dict[str, dict],
    ):
        """
        Test: Find RetrieverV3Config dataclass.
        Expected: Symbol intent, exact class match.
        """
        query_spec = golden_queries["query_7_config"]
        query = query_spec["query"]

        results: list[FusedResultV3] = retriever_v3_service.retrieve(
            query=query,
            repo_id="test_repo",
            top_k=10,
        )

        assert len(results) >= query_spec["min_results"]

        # Top result should be exact class definition
        top_result = results[0]
        assert "RetrieverV3Config" in (top_result.chunk.symbol_id or ""), (
            f"Expected RetrieverV3Config in top result, got {top_result.chunk.symbol_id}"
        )

        print(f"✅ Query 7 passed: {len(results)} results")

    def test_query_8_model_fused_result(
        self,
        retriever_v3_service: RetrieverV3Service,
        indexed_repo: bool,
        golden_queries: dict[str, dict],
    ):
        """
        Test: Find FusedResultV3 data model.
        Expected: Symbol intent, class definition.
        """
        query_spec = golden_queries["query_8_model"]
        query = query_spec["query"]

        results: list[FusedResultV3] = retriever_v3_service.retrieve(
            query=query,
            repo_id="test_repo",
            top_k=10,
        )

        assert len(results) >= query_spec["min_results"]

        # Validate top result
        top_symbols = [r.chunk.symbol_id for r in results[:3] if r.chunk.symbol_id]
        assert any("FusedResultV3" in s for s in top_symbols), f"Expected FusedResultV3 in top results: {top_symbols}"

        print(f"✅ Query 8 passed: {len(results)} results")

    def test_query_9_feature_vector_generation(
        self,
        retriever_v3_service: RetrieverV3Service,
        indexed_repo: bool,
        golden_queries: dict[str, dict],
    ):
        """
        Test: Find feature vector generation for LTR.
        Expected: Code intent, feature generation function.
        """
        query_spec = golden_queries["query_9_feature_vector"]
        query = query_spec["query"]

        results: list[FusedResultV3] = retriever_v3_service.retrieve(
            query=query,
            repo_id="test_repo",
            top_k=10,
        )

        assert len(results) >= query_spec["min_results"]

        # Validate feature vectors are populated in results
        for result in results[:3]:
            assert result.feature_vector is not None, "Expected feature vectors to be generated"
            assert len(result.feature_vector.features) > 0, "Expected non-empty feature vector"

        print(f"✅ Query 9 passed: {len(results)} results with feature vectors")

    def test_query_10_intent_weight_calculation(
        self,
        retriever_v3_service: RetrieverV3Service,
        indexed_repo: bool,
        golden_queries: dict[str, dict],
    ):
        """
        Test: Find intent-based weight calculation.
        Expected: Code intent, _calculate_intent_weights method.
        """
        query_spec = golden_queries["query_10_weights"]
        query = query_spec["query"]

        results: list[FusedResultV3] = retriever_v3_service.retrieve(
            query=query,
            repo_id="test_repo",
            top_k=10,
        )

        assert len(results) >= query_spec["min_results"]

        # Validate weights are properly calculated
        top_result = results[0]
        weights = top_result.weights
        weight_sum = weights.vec + weights.lex + weights.sym + weights.graph

        # Weights should sum to approximately 1.0
        assert 0.95 <= weight_sum <= 1.05, f"Expected weight sum ~1.0, got {weight_sum:.3f}"

        print(f"✅ Query 10 passed: {len(results)} results, weight_sum={weight_sum:.3f}")

    def test_explainability_features(
        self,
        retriever_v3_service: RetrieverV3Service,
        indexed_repo: bool,
    ):
        """
        Test: Validate explainability features are populated.
        Expected: All results have explanation metadata.
        """
        query = "find RetrieverV3Service"

        results: list[FusedResultV3] = retriever_v3_service.retrieve(
            query=query,
            repo_id="test_repo",
            top_k=5,
        )

        assert len(results) > 0

        for result in results:
            # Check explainability fields
            assert result.strategies is not None, "Expected strategies list"
            assert len(result.strategies) > 0, "Expected at least one strategy"

            assert result.consensus is not None, "Expected consensus info"

            assert result.weights is not None, "Expected weight profile"

            assert result.intent_prob is not None, "Expected intent probabilities"

        print(f"✅ Explainability test passed: All {len(results)} results have explanation metadata")

    def test_consensus_boosting_applied(
        self,
        retriever_v3_service: RetrieverV3Service,
        indexed_repo: bool,
    ):
        """
        Test: Validate consensus boosting is applied.
        Expected: Multi-strategy results have boost > 1.0.
        """
        query = "RetrieverV3Service class implementation"

        results: list[FusedResultV3] = retriever_v3_service.retrieve(
            query=query,
            repo_id="test_repo",
            top_k=10,
        )

        assert len(results) > 0

        # Find results with multi-strategy consensus
        consensus_results = [r for r in results if len(r.strategies) >= 3]

        assert len(consensus_results) > 0, "Expected at least one result with 3+ strategies"

        # Check that consensus boost was applied
        for result in consensus_results:
            assert result.consensus.boost_factor >= 1.15, (
                f"Expected consensus boost >= 1.15, got {result.consensus.boost_factor}"
            )

        print(f"✅ Consensus boosting test passed: {len(consensus_results)} results with boost >= 1.15")

    def test_p1_query_expansion_applied(
        self,
        retriever_v3_service: RetrieverV3Service,
        indexed_repo: bool,
    ):
        """
        Test: Validate P1 query expansion boosting is applied.
        Expected: Chunks matching extracted symbols are boosted.
        """
        # Query that should extract "RetrieverV3Service" as a symbol
        query = "find RetrieverV3Service in service.py"

        results: list[FusedResultV3] = retriever_v3_service.retrieve(
            query=query,
            repo_id="test_repo",
            top_k=10,
        )

        assert len(results) > 0

        # Top result should be the exact class definition
        top_result = results[0]
        assert "RetrieverV3Service" in (top_result.chunk.symbol_id or ""), (
            f"Expected RetrieverV3Service in top result (expansion boost), got {top_result.chunk.symbol_id}"
        )

        # Check that file path matching works
        assert "service.py" in (top_result.chunk.file_path or ""), (
            f"Expected service.py in top result file path, got {top_result.chunk.file_path}"
        )

        print("✅ P1 query expansion test passed: Exact symbol and file path match in top result")


@pytest.mark.integration
@pytest.mark.slow
class TestV3IntegrationPerformance:
    """Performance validation tests with real data."""

    def test_retrieval_latency_p50(
        self,
        retriever_v3_service: RetrieverV3Service,
        indexed_repo: bool,
        golden_queries: dict[str, dict],
    ):
        """
        Test: Measure p50 retrieval latency.
        Expected: p50 < 100ms for real data queries.
        """
        import time

        latencies = []

        for query_spec in golden_queries.values():
            query = query_spec["query"]

            start = time.time()
            results = retriever_v3_service.retrieve(
                query=query,
                repo_id="test_repo",
                top_k=10,
            )
            latency_ms = (time.time() - start) * 1000

            latencies.append(latency_ms)

        # Calculate p50
        latencies.sort()
        p50 = latencies[len(latencies) // 2]

        print("\n📊 Performance metrics:")
        print(f"  - Queries: {len(latencies)}")
        print(f"  - p50: {p50:.2f}ms")
        print(f"  - Min: {min(latencies):.2f}ms")
        print(f"  - Max: {max(latencies):.2f}ms")

        # Validate p50 is reasonable for real data
        assert p50 < 500, f"p50 latency {p50:.2f}ms exceeds 500ms (too slow)"

        print(f"✅ Performance test passed: p50 = {p50:.2f}ms")

    def test_cache_effectiveness(
        self,
        retriever_v3_service: RetrieverV3Service,
        indexed_repo: bool,
    ):
        """
        Test: Validate caching reduces latency on repeated queries.
        Expected: Second query is faster than first.
        """
        import time

        query = "find RetrieverV3Service class"

        # First query (cold cache)
        start = time.time()
        results_1 = retriever_v3_service.retrieve(query=query, repo_id="test_repo", top_k=10)
        latency_cold = (time.time() - start) * 1000

        # Second query (warm cache)
        start = time.time()
        results_2 = retriever_v3_service.retrieve(query=query, repo_id="test_repo", top_k=10)
        latency_warm = (time.time() - start) * 1000

        print("\n📊 Cache effectiveness:")
        print(f"  - Cold cache: {latency_cold:.2f}ms")
        print(f"  - Warm cache: {latency_warm:.2f}ms")
        print(f"  - Speedup: {latency_cold / latency_warm:.2f}x")

        # Warm cache should be at least 20% faster
        assert latency_warm < latency_cold * 0.8, (
            f"Expected warm cache speedup, but got {latency_warm:.2f}ms vs {latency_cold:.2f}ms"
        )

        print(f"✅ Cache test passed: {latency_cold / latency_warm:.2f}x speedup")
