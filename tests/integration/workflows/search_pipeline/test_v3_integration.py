"""
Integration tests for Retriever V3.

Tests the complete end-to-end pipeline.
"""

import pytest

from src.index.common.documents import SearchHit
from src.retriever.v3.config import RetrieverV3Config
from src.retriever.v3.service import RetrieverV3Service


class TestRetrieverV3Integration:
    """Integration tests for v3 retriever."""

    @pytest.fixture
    def service(self):
        """Create retriever service."""
        config = RetrieverV3Config()
        return RetrieverV3Service(config=config)

    @pytest.fixture
    def sample_search_hits(self):
        """Create sample search hits from multiple strategies."""
        return {
            "vector": [
                SearchHit(
                    chunk_id="chunk1",
                    score=0.95,
                    source="vector",
                    file_path="src/auth/login.py",
                    symbol_id="func:login",
                    metadata={"chunk_size": 500},
                ),
                SearchHit(
                    chunk_id="chunk2",
                    score=0.85,
                    source="vector",
                    file_path="src/auth/verify.py",
                    metadata={"chunk_size": 300},
                ),
                SearchHit(
                    chunk_id="chunk3",
                    score=0.75,
                    source="vector",
                    file_path="src/utils/helpers.py",
                    metadata={"chunk_size": 200},
                ),
            ],
            "lexical": [
                SearchHit(
                    chunk_id="chunk1",
                    score=20.0,
                    source="lexical",
                    file_path="src/auth/login.py",
                    metadata={"chunk_size": 500},
                ),
                SearchHit(
                    chunk_id="chunk4",
                    score=15.0,
                    source="lexical",
                    file_path="src/auth/logout.py",
                    metadata={"chunk_size": 400},
                ),
            ],
            "symbol": [
                SearchHit(
                    chunk_id="chunk1",
                    score=1.0,
                    source="symbol",
                    file_path="src/auth/login.py",
                    symbol_id="func:login",
                    metadata={"symbol_type": "function"},
                ),
            ],
            "graph": [
                SearchHit(
                    chunk_id="chunk1",
                    score=0.8,
                    source="runtime",  # Graph expansion hits use runtime source
                    file_path="src/auth/login.py",
                    metadata={},
                ),
                SearchHit(
                    chunk_id="chunk5",
                    score=0.6,
                    source="runtime",  # Graph expansion hits use runtime source
                    file_path="src/db/connection.py",
                    metadata={},
                ),
            ],
        }

    def test_complete_pipeline_symbol_query(self, service, sample_search_hits):
        """Test complete pipeline with symbol query."""
        query = "login function"

        results, intent = service.retrieve(query=query, hits_by_strategy=sample_search_hits, enable_cache=False)

        # Should classify as symbol intent
        assert intent.symbol > 0.2

        # Should return results
        assert len(results) > 0

        # chunk1 should be top (appears in all 4 strategies)
        top_result = results[0]
        assert top_result.chunk_id == "chunk1"

        # Should have consensus boost
        assert top_result.consensus_stats.num_strategies == 4

        # Should have feature vector
        assert top_result.feature_vector is not None
        assert top_result.feature_vector.chunk_id == "chunk1"

    def test_complete_pipeline_concept_query(self, service, sample_search_hits):
        """Test complete pipeline with concept query."""
        query = "how does authentication work?"

        results, intent = service.retrieve(query=query, hits_by_strategy=sample_search_hits, enable_cache=False)

        # Should classify as concept intent
        assert intent.concept > 0.3

        # Should return results
        assert len(results) > 0

        # Should apply concept-specific cutoff (higher k)
        # With concept intent, k=60 (from config)
        assert len(results) <= 60

    def test_complete_pipeline_flow_query(self, service, sample_search_hits):
        """Test complete pipeline with flow query."""
        query = "trace call from login to database"

        results, intent = service.retrieve(query=query, hits_by_strategy=sample_search_hits, enable_cache=False)

        # Should classify as flow intent
        assert intent.flow > 0.2

        # Should apply flow-specific cutoff (lower k)
        # With flow intent, k=15 (from config)
        assert len(results) <= 15

    def test_consensus_boosting(self, service, sample_search_hits):
        """Test that consensus boosting works correctly."""
        query = "authentication"

        results, _ = service.retrieve(query=query, hits_by_strategy=sample_search_hits, enable_cache=False)

        # chunk1 appears in 4 strategies, others in fewer
        chunk1_result = next(r for r in results if r.chunk_id == "chunk1")

        # chunk1 should have high consensus
        assert chunk1_result.consensus_stats.num_strategies == 4
        assert chunk1_result.consensus_stats.consensus_factor > 1.0

    def test_feature_vector_generation(self, service, sample_search_hits):
        """Test that feature vectors are correctly generated."""
        query = "login"

        results, _ = service.retrieve(query=query, hits_by_strategy=sample_search_hits, enable_cache=False)

        # Check first result
        result = results[0]
        fv = result.feature_vector

        # Should have ranks set
        assert fv.rank_vec is not None
        assert fv.rank_lex is not None
        assert fv.rank_sym is not None
        assert fv.rank_graph is not None

        # Should have RRF scores
        assert fv.rrf_vec > 0
        assert fv.rrf_lex > 0
        assert fv.rrf_sym > 0
        assert fv.rrf_graph > 0

        # Should have weights
        assert fv.weight_vec > 0
        assert fv.weight_lex > 0
        assert fv.weight_sym >= 0
        assert fv.weight_graph >= 0

        # Should have consensus features
        assert fv.num_strategies > 0
        assert fv.consensus_factor > 0

    def test_explainability(self, service, sample_search_hits):
        """Test that explainability is generated."""
        query = "login function"

        results, _ = service.retrieve(query=query, hits_by_strategy=sample_search_hits, enable_cache=False)

        # Check explanation
        result = results[0]
        explanation = service.explain_result(result)

        assert len(explanation) > 0
        assert "chunk1" in explanation or "score" in explanation.lower()

    def test_ltr_feature_extraction(self, service, sample_search_hits):
        """Test LTR feature vector extraction."""
        query = "authentication"

        results, _ = service.retrieve(query=query, hits_by_strategy=sample_search_hits, enable_cache=False)

        # Extract feature vectors
        chunk_ids, feature_arrays = service.get_feature_vectors(results)

        assert len(chunk_ids) == len(results)
        assert len(feature_arrays) == len(results)

        # Each feature array should have consistent length
        first_array = feature_arrays[0]
        assert len(first_array) > 0
        assert all(len(arr) == len(first_array) for arr in feature_arrays)

    def test_empty_strategy_handling(self, service):
        """Test handling of empty strategy results."""
        hits = {
            "vector": [
                SearchHit(
                    chunk_id="chunk1",
                    score=0.9,
                    source="vector",
                    file_path="test.py",
                ),
            ],
            "lexical": [],  # Empty
            "symbol": [],  # Empty
            "graph": [],  # Empty
        }

        query = "test"
        results, _ = service.retrieve(query=query, hits_by_strategy=hits, enable_cache=False)

        # Should still work
        assert len(results) > 0

    def test_single_strategy_results(self, service):
        """Test with results from single strategy only."""
        hits = {
            "vector": [
                SearchHit(chunk_id="chunk1", score=0.9, source="vector", file_path="test.py"),
                SearchHit(chunk_id="chunk2", score=0.8, source="vector", file_path="test2.py"),
            ],
        }

        query = "test"
        results, _ = service.retrieve(query=query, hits_by_strategy=hits, enable_cache=False)

        assert len(results) == 2

        # No consensus boost (single strategy)
        for result in results:
            assert result.consensus_stats.num_strategies == 1

    def test_metadata_preservation(self, service):
        """Test that metadata is preserved through pipeline."""
        hits = {
            "vector": [
                SearchHit(
                    chunk_id="chunk1",
                    score=0.9,
                    source="vector",
                    file_path="test.py",
                    metadata={"custom_field": "custom_value", "chunk_size": 500},
                ),
            ],
        }

        metadata_map = {"chunk1": {"custom_field": "custom_value", "chunk_size": 500}}

        query = "test"
        results, _ = service.retrieve(
            query=query,
            hits_by_strategy=hits,
            metadata_map=metadata_map,
            enable_cache=False,
        )

        result = results[0]
        assert result.feature_vector.chunk_size == 500

    def test_ranking_by_final_score(self, service, sample_search_hits):
        """Test that results are ranked by final score."""
        query = "authentication"

        results, _ = service.retrieve(query=query, hits_by_strategy=sample_search_hits, enable_cache=False)

        # Results should be sorted by final_score descending
        for i in range(len(results) - 1):
            assert results[i].final_score >= results[i + 1].final_score

    def test_different_intents_different_weights(self, service, sample_search_hits):
        """Test that different intents produce different rankings."""
        symbol_query = "LoginHandler"
        concept_query = "how does login work"

        symbol_results, symbol_intent = service.retrieve(
            query=symbol_query, hits_by_strategy=sample_search_hits, enable_cache=False
        )

        concept_results, concept_intent = service.retrieve(
            query=concept_query, hits_by_strategy=sample_search_hits, enable_cache=False
        )

        # Intents should be different
        assert symbol_intent.dominant_intent() != concept_intent.dominant_intent()

        # Weights should be different
        # Symbol intent should favor symbol/lexical
        # Concept intent should favor vector

        symbol_top = symbol_results[0]
        concept_top = concept_results[0]

        # Feature vectors should have different weights
        assert (
            symbol_top.feature_vector.weight_sym != concept_top.feature_vector.weight_sym
            or symbol_top.feature_vector.weight_vec != concept_top.feature_vector.weight_vec
        )
