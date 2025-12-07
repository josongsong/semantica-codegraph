"""
Integration test fixtures for Retriever V3 with real indexed data.

This module provides pytest fixtures that connect to real databases
and indexes, unlike the unit tests which use mocks.
"""

from pathlib import Path

import pytest

from src.container import container
from src.contexts.retrieval_search.infrastructure.v3.config import RetrieverV3Config
from src.contexts.retrieval_search.infrastructure.v3.service import RetrieverV3Service


@pytest.fixture(scope="session")
def test_repo_path() -> Path:
    """Path to the test repository to be indexed."""
    return Path(__file__).parent.parent.parent / "src" / "retriever"


@pytest.fixture(scope="session")
def symbol_index():
    """Real Kuzu-based symbol index."""
    return container.symbol_index


@pytest.fixture(scope="session")
def vector_index():
    """Real Qdrant-based vector index."""
    return container.vector_index


@pytest.fixture(scope="session")
def lexical_index():
    """Real Zoekt-based lexical index."""
    return container.lexical_index


@pytest.fixture(scope="session")
def graph_store():
    """Real Kuzu-based graph store for runtime relationships."""
    return container.graph_store


@pytest.fixture(scope="session")
def retriever_v3_config() -> RetrieverV3Config:
    """
    V3 configuration for integration tests.

    Uses default settings with query expansion enabled.
    """
    return RetrieverV3Config(
        # P1 improvements enabled
        enable_query_expansion=True,
        enable_explainability=True,
        enable_cache=True,
        # Cache TTL
        cache_ttl=300,
    )


@pytest.fixture(scope="session")
def retriever_v3_service(
    retriever_v3_config: RetrieverV3Config,
) -> RetrieverV3Service:
    """
    RetrieverV3Service for fusion.

    V3 only performs fusion - it doesn't search indexes directly.
    Tests should call indexes separately and pass results to V3.
    """
    return RetrieverV3Service(
        config=retriever_v3_config,
        cache_client=None,  # No cache for integration tests
    )


@pytest.fixture(scope="session")
def indexed_repo(
    test_repo_path: Path,
    symbol_index,
    vector_index,
    lexical_index,
    graph_store,
) -> bool:
    """
    Ensure test repository is indexed before running tests.

    For now, returns True to skip indexing (use mock data).
    TODO: Implement actual indexing once script is fixed.
    """
    # Skip indexing for now - tests will use mock/fixture data
    # Once indexing script is working, uncomment below:
    #
    # # Check if already indexed by querying for a known symbol
    # try:
    #     results = symbol_index.search("RetrieverV3Service", limit=1)
    #     if results and len(results) > 0:
    #         # Already indexed, skip
    #         return True
    # except Exception:
    #     pass
    #
    # # Not indexed, run indexing script
    # import subprocess
    # import sys
    #
    # script_path = Path(__file__).parent.parent.parent / "scripts" / "index_test_repo.py"
    # result = subprocess.run(
    #     [sys.executable, str(script_path), str(test_repo_path)],
    #     capture_output=True,
    #     text=True,
    # )
    #
    # if result.returncode != 0:
    #     pytest.fail(f"Failed to index test repository: {result.stderr}")

    return True


@pytest.fixture
def golden_queries() -> dict[str, dict]:
    """
    Golden query dataset with expected results.

    Each query has:
    - query: The search query string
    - expected_intent: Expected dominant intent
    - expected_top_symbols: Expected symbols in top results
    - min_results: Minimum number of results expected
    """
    return {
        "query_1_symbol": {
            "query": "find RetrieverV3Service class",
            "expected_intent": "symbol",
            "expected_top_symbols": ["class:RetrieverV3Service"],
            "min_results": 1,
        },
        "query_2_flow": {
            "query": "who calls IntentClassifierV3",
            "expected_intent": "flow",
            "expected_top_symbols": ["class:RetrieverV3Service"],
            "min_results": 1,
        },
        "query_3_code": {
            "query": "how is fusion implemented",
            "expected_intent": "code",
            "expected_top_symbols": ["class:FusionEngineV3", "func:fuse"],
            "min_results": 2,
        },
        "query_4_concept": {
            "query": "weighted RRF normalization pattern",
            "expected_intent": "concept",
            "expected_top_symbols": ["class:RRFNormalizer"],
            "min_results": 1,
        },
        "query_5_flow_boosting": {
            "query": "consensus boosting logic",
            "expected_intent": "flow",
            "expected_top_symbols": ["class:ConsensusEngine", "func:apply_consensus_boost"],
            "min_results": 2,
        },
        "query_6_symbol_expansion": {
            "query": "intent classification with expansion",
            "expected_intent": "symbol",
            "expected_top_symbols": ["class:IntentClassifierV3", "func:classify_with_expansion"],
            "min_results": 2,
        },
        "query_7_config": {
            "query": "RetrieverV3Config dataclass",
            "expected_intent": "symbol",
            "expected_top_symbols": ["class:RetrieverV3Config"],
            "min_results": 1,
        },
        "query_8_model": {
            "query": "FusedResultV3 data model",
            "expected_intent": "symbol",
            "expected_top_symbols": ["class:FusedResultV3"],
            "min_results": 1,
        },
        "query_9_feature_vector": {
            "query": "feature vector generation for LTR",
            "expected_intent": "code",
            "expected_top_symbols": ["func:generate_feature_vectors"],
            "min_results": 1,
        },
        "query_10_weights": {
            "query": "calculate intent-based weights",
            "expected_intent": "code",
            "expected_top_symbols": ["func:_calculate_intent_weights"],
            "min_results": 1,
        },
    }
