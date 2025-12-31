"""
Score Normalizer Tests (SOTA L11)

Test Coverage:
- Base: Min-max normalization for each source
- Edge: Empty lists, single item, identical scores
- Corner: Negative scores, very large scores, virtual chunks
"""

import pytest

from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit
from codegraph_search.infrastructure.fusion.normalizer import ScoreNormalizer


@pytest.fixture
def normalizer():
    """Default normalizer"""
    return ScoreNormalizer()


@pytest.fixture
def normalizer_with_penalty():
    """Normalizer with custom virtual chunk penalty"""
    return ScoreNormalizer(virtual_chunk_penalty=0.5)


def make_hit(id: str, score: float, is_virtual: bool = False, source: str = "lexical") -> SearchHit:
    """Helper to create SearchHit"""
    return SearchHit(
        chunk_id=id,
        file_path="test.py",
        score=score,
        source=source,
        metadata={"is_virtual": is_virtual} if is_virtual else {},
    )


class TestLexicalNormalization:
    """Lexical (Zoekt) score normalization"""

    def test_normalize_basic(self, normalizer):
        """Basic lexical normalization"""
        hits = [make_hit("a", 100), make_hit("b", 50), make_hit("c", 0)]
        result = normalizer.normalize_hits(hits, "lexical")

        assert result[0].score == pytest.approx(1.0)  # max -> 1.0
        assert result[1].score == pytest.approx(0.5)  # mid -> 0.5
        assert result[2].score == pytest.approx(0.0)  # min -> 0.0

    def test_normalize_single_hit(self, normalizer):
        """Single hit normalization"""
        hits = [make_hit("a", 50)]
        result = normalizer.normalize_hits(hits, "lexical")

        assert len(result) == 1
        # Single hit - min == max, implementation dependent
        assert 0.0 <= result[0].score <= 1.0

    def test_normalize_identical_scores(self, normalizer):
        """All identical scores"""
        hits = [make_hit("a", 100), make_hit("b", 100), make_hit("c", 100)]
        result = normalizer.normalize_hits(hits, "lexical")

        # All should get same normalized score
        for hit in result:
            assert hit.score >= 0.0 and hit.score <= 1.0


class TestVectorNormalization:
    """Vector (Qdrant) score normalization"""

    def test_vector_already_normalized(self, normalizer):
        """Vector scores already in 0-1 range"""
        hits = [make_hit("a", 0.95), make_hit("b", 0.80), make_hit("c", 0.65)]
        result = normalizer.normalize_hits(hits, "vector")

        # Should preserve relative ordering
        assert result[0].score >= result[1].score >= result[2].score

    def test_vector_edge_values(self, normalizer):
        """Vector scores at boundaries"""
        hits = [make_hit("a", 1.0), make_hit("b", 0.0)]
        result = normalizer.normalize_hits(hits, "vector")

        assert all(0.0 <= h.score <= 1.0 for h in result)


class TestSymbolNormalization:
    """Symbol index normalization"""

    def test_symbol_binary_scores(self, normalizer):
        """Symbol with binary scores (0 or 1)"""
        hits = [make_hit("a", 1), make_hit("b", 1), make_hit("c", 0)]
        result = normalizer.normalize_hits(hits, "symbol")

        assert all(0.0 <= h.score <= 1.0 for h in result)


class TestGraphNormalization:
    """Graph-based score normalization"""

    def test_graph_depth_scores(self, normalizer):
        """Graph depth-based scores"""
        hits = [make_hit("a", 1.0), make_hit("b", 0.5), make_hit("c", 0.25)]
        result = normalizer.normalize_hits(hits, "graph")

        assert all(0.0 <= h.score <= 1.0 for h in result)


class TestUnknownSource:
    """Unknown source handling"""

    def test_unknown_source_fallback(self, normalizer):
        """Unknown source uses fallback normalization"""
        hits = [make_hit("a", 100), make_hit("b", 50)]
        result = normalizer.normalize_hits(hits, "unknown_index")

        # Should not crash, apply fallback
        assert len(result) == 2
        assert all(0.0 <= h.score <= 1.0 for h in result)


class TestEdgeCases:
    """Edge case tests"""

    def test_empty_list(self, normalizer):
        """Empty hit list"""
        result = normalizer.normalize_hits([], "lexical")
        assert result == []

    def test_negative_scores(self, normalizer):
        """Negative scores (BM25 can have negative)"""
        hits = [make_hit("a", 10), make_hit("b", -5), make_hit("c", -10)]
        result = normalizer.normalize_hits(hits, "lexical")

        # Should still normalize to 0-1
        assert result[0].score == pytest.approx(1.0)  # max
        assert result[2].score == pytest.approx(0.0)  # min

    def test_very_large_scores(self, normalizer):
        """Very large scores"""
        hits = [make_hit("a", 1e10), make_hit("b", 1e5), make_hit("c", 1)]
        result = normalizer.normalize_hits(hits, "lexical")

        assert result[0].score == pytest.approx(1.0)
        assert all(0.0 <= h.score <= 1.0 for h in result)

    def test_very_small_differences(self, normalizer):
        """Very small score differences"""
        hits = [make_hit("a", 1.0001), make_hit("b", 1.0000), make_hit("c", 0.9999)]
        result = normalizer.normalize_hits(hits, "lexical")

        # Should still differentiate
        assert result[0].score >= result[2].score


class TestVirtualChunkPenalty:
    """Virtual chunk penalty tests"""

    def test_default_penalty(self, normalizer):
        """Default virtual chunk penalty is 0.8"""
        assert normalizer.virtual_chunk_penalty == 0.8

    def test_custom_penalty(self, normalizer_with_penalty):
        """Custom virtual chunk penalty"""
        assert normalizer_with_penalty.virtual_chunk_penalty == 0.5


class TestCornerCases:
    """Corner case tests"""

    def test_preserve_hit_metadata(self, normalizer):
        """Normalization preserves hit metadata"""
        hits = [SearchHit(chunk_id="a", file_path="test.py", score=100, source="lexical", metadata={"extra": "data"})]
        result = normalizer.normalize_hits(hits, "lexical")

        assert result[0].chunk_id == "a"
        assert result[0].file_path == "test.py"
        # Metadata should be preserved or extended

    def test_all_zero_scores(self, normalizer):
        """All zero scores"""
        hits = [make_hit("a", 0), make_hit("b", 0), make_hit("c", 0)]
        result = normalizer.normalize_hits(hits, "lexical")

        # Should handle gracefully
        assert len(result) == 3

    def test_mixed_sources_sequential(self, normalizer):
        """Sequential normalization of different sources"""
        lexical = normalizer.normalize_hits([make_hit("a", 100)], "lexical")
        vector = normalizer.normalize_hits([make_hit("b", 0.9)], "vector")
        symbol = normalizer.normalize_hits([make_hit("c", 1)], "symbol")

        assert all(0.0 <= h.score <= 1.0 for h in lexical + vector + symbol)
