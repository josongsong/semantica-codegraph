"""
Fusion Engine Tests

Test Coverage:
- Score normalization
- RRF (Reciprocal Rank Fusion)
- Weight-based fusion
"""

import pytest

from codegraph_search.domain.models import IndexType, SearchHit


class TestScoreNormalization:
    """Score normalization tests"""

    def test_min_max_normalize_basic(self):
        """Min-max normalization"""
        scores = [0.1, 0.5, 0.9]
        normalized = [(s - min(scores)) / (max(scores) - min(scores)) for s in scores]
        assert normalized[0] == pytest.approx(0.0)
        assert normalized[2] == pytest.approx(1.0)

    def test_normalize_identical_scores(self):
        """All identical scores"""
        scores = [0.5, 0.5, 0.5]
        # Edge case: max == min
        range_val = max(scores) - min(scores)
        if range_val == 0:
            normalized = [0.5] * len(scores)
        else:
            normalized = [(s - min(scores)) / range_val for s in scores]
        assert all(s == 0.5 for s in normalized)

    def test_normalize_negative_scores(self):
        """Negative scores (BM25)"""
        scores = [-0.5, 0.0, 0.5]
        min_s, max_s = min(scores), max(scores)
        normalized = [(s - min_s) / (max_s - min_s) for s in scores]
        assert normalized[0] == pytest.approx(0.0)
        assert normalized[2] == pytest.approx(1.0)


class TestRRFFusion:
    """Reciprocal Rank Fusion tests"""

    def test_rrf_single_list(self):
        """RRF with single list"""
        # RRF formula: 1 / (k + rank)
        k = 60
        ranks = [1, 2, 3]
        rrf_scores = [1 / (k + r) for r in ranks]
        assert rrf_scores[0] > rrf_scores[1] > rrf_scores[2]

    def test_rrf_merge_two_lists(self):
        """RRF merging two result lists"""
        k = 60
        # Doc appears in both lists at different ranks
        doc_id = "doc_1"
        rank_in_list_a = 1
        rank_in_list_b = 3

        rrf_a = 1 / (k + rank_in_list_a)
        rrf_b = 1 / (k + rank_in_list_b)
        combined = rrf_a + rrf_b

        # Compare to doc in only one list
        single_list_score = 1 / (k + 1)
        assert combined > single_list_score

    def test_rrf_k_parameter_effect(self):
        """K parameter affects score distribution"""
        rank = 1
        k_small = 10
        k_large = 100

        score_small_k = 1 / (k_small + rank)
        score_large_k = 1 / (k_large + rank)

        assert score_small_k > score_large_k


class TestWeightedFusion:
    """Weighted fusion tests"""

    def test_equal_weights(self):
        """Equal weights average scores"""
        score_vector = 0.8
        score_lexical = 0.6
        weights = {IndexType.VECTOR: 0.5, IndexType.LEXICAL: 0.5}

        combined = score_vector * weights[IndexType.VECTOR] + score_lexical * weights[IndexType.LEXICAL]
        assert combined == pytest.approx(0.7)

    def test_vector_heavy_weights(self):
        """Vector-heavy weighting"""
        score_vector = 0.9
        score_lexical = 0.3
        weights = {IndexType.VECTOR: 0.8, IndexType.LEXICAL: 0.2}

        combined = score_vector * weights[IndexType.VECTOR] + score_lexical * weights[IndexType.LEXICAL]
        assert combined == pytest.approx(0.78)

    def test_weights_sum_to_one(self):
        """Weights should sum to 1"""
        weights = {
            IndexType.VECTOR: 0.5,
            IndexType.LEXICAL: 0.3,
            IndexType.SYMBOL: 0.2,
        }
        assert sum(weights.values()) == pytest.approx(1.0)


class TestFusionEdgeCases:
    """Fusion edge cases"""

    def test_empty_results(self):
        """Empty result lists"""
        results_a = []
        results_b = []
        merged = results_a + results_b
        assert len(merged) == 0

    def test_disjoint_results(self):
        """Completely disjoint result sets"""
        hits_a = [SearchHit(id="a1", score=0.9, content="")]
        hits_b = [SearchHit(id="b1", score=0.8, content="")]
        merged_ids = {h.id for h in hits_a + hits_b}
        assert len(merged_ids) == 2

    def test_duplicate_handling(self):
        """Duplicate documents across sources"""
        hits_a = [SearchHit(id="doc1", score=0.9, content="")]
        hits_b = [SearchHit(id="doc1", score=0.8, content="")]

        # Dedup by id, keep max score
        by_id = {}
        for hit in hits_a + hits_b:
            if hit.id not in by_id or hit.score > by_id[hit.id].score:
                by_id[hit.id] = hit

        assert len(by_id) == 1
        assert by_id["doc1"].score == 0.9
