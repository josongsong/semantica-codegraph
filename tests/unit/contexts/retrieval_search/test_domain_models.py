"""
Retrieval Search Domain Models Tests

Test Coverage:
- Enums: IntentType, IndexType
- Data Models: SearchQuery, SearchHit, SearchResult, Intent
- Edge cases: Validation, defaults
"""

import pytest

from codegraph_search.domain.models import (
    IndexType,
    Intent,
    IntentType,
    SearchHit,
    SearchQuery,
    SearchResult,
)


class TestIntentType:
    """IntentType enum tests"""

    def test_all_types_defined(self):
        """All intent types exist"""
        assert IntentType.SEMANTIC.value == "semantic"
        assert IntentType.LEXICAL.value == "lexical"
        assert IntentType.SYMBOL.value == "symbol"
        assert IntentType.HYBRID.value == "hybrid"

    def test_enum_count(self):
        """Expected number of intent types"""
        assert len(IntentType) == 4


class TestIndexType:
    """IndexType enum tests"""

    def test_all_types_defined(self):
        """All index types exist"""
        assert IndexType.LEXICAL.value == "lexical"
        assert IndexType.VECTOR.value == "vector"
        assert IndexType.SYMBOL.value == "symbol"
        assert IndexType.FUZZY.value == "fuzzy"
        assert IndexType.DOMAIN.value == "domain"

    def test_enum_count(self):
        """Expected number of index types"""
        assert len(IndexType) == 5


class TestSearchQuery:
    """SearchQuery model tests"""

    def test_create_basic_query(self):
        """Create basic search query"""
        query = SearchQuery(query="find auth", repo_id="repo_123")
        assert query.query == "find auth"
        assert query.repo_id == "repo_123"
        assert query.limit == 10  # default
        assert query.offset == 0  # default

    def test_create_query_with_pagination(self):
        """Create query with pagination"""
        query = SearchQuery(query="test", repo_id="repo", limit=50, offset=100)
        assert query.limit == 50
        assert query.offset == 100

    def test_empty_query(self):
        """Empty query string allowed"""
        query = SearchQuery(query="", repo_id="repo")
        assert query.query == ""


class TestSearchHit:
    """SearchHit model tests"""

    def test_create_basic_hit(self):
        """Create basic search hit"""
        hit = SearchHit(id="doc_1", score=0.95, content="def auth():")
        assert hit.id == "doc_1"
        assert hit.score == 0.95
        assert hit.content == "def auth():"
        assert hit.metadata == {}  # default
        assert hit.rank == 0  # default

    def test_hit_with_metadata(self):
        """Hit with metadata"""
        hit = SearchHit(
            id="doc_1",
            score=0.85,
            content="class User:",
            metadata={"file": "user.py", "line": 10, "boost": 1.5},
        )
        assert hit.metadata["file"] == "user.py"
        assert hit.metadata["line"] == 10
        assert hit.metadata["boost"] == 1.5

    def test_hit_with_rank(self):
        """Hit with rank"""
        hit = SearchHit(id="doc_1", score=0.9, content="code", rank=1)
        assert hit.rank == 1

    def test_score_range(self):
        """Score can be any float"""
        hit_high = SearchHit(id="1", score=1.0, content="")
        hit_low = SearchHit(id="2", score=0.0, content="")
        hit_negative = SearchHit(id="3", score=-0.5, content="")  # BM25 can be negative

        assert hit_high.score == 1.0
        assert hit_low.score == 0.0
        assert hit_negative.score == -0.5


class TestSearchResult:
    """SearchResult model tests"""

    def test_create_result(self):
        """Create search result"""
        hits = [
            SearchHit(id="1", score=0.9, content="a"),
            SearchHit(id="2", score=0.8, content="b"),
        ]
        result = SearchResult(query="test", hits=hits, total=100, took_ms=15.5)

        assert result.query == "test"
        assert len(result.hits) == 2
        assert result.total == 100
        assert result.took_ms == 15.5

    def test_empty_result(self):
        """Empty search result"""
        result = SearchResult(query="no match", hits=[], total=0, took_ms=1.0)
        assert len(result.hits) == 0
        assert result.total == 0

    def test_result_with_many_hits(self):
        """Result with many hits"""
        hits = [SearchHit(id=str(i), score=1.0 - i * 0.01, content=f"doc{i}") for i in range(100)]
        result = SearchResult(query="bulk", hits=hits, total=1000, took_ms=50.0)
        assert len(result.hits) == 100
        assert result.total == 1000


class TestIntent:
    """Intent model tests"""

    def test_create_intent(self):
        """Create search intent"""
        intent = Intent(type=IntentType.SEMANTIC, confidence=0.95)
        assert intent.type == IntentType.SEMANTIC
        assert intent.confidence == 0.95
        assert intent.weights == {}  # default

    def test_intent_with_weights(self):
        """Intent with index weights"""
        intent = Intent(
            type=IntentType.HYBRID,
            confidence=0.8,
            weights={
                IndexType.VECTOR: 0.6,
                IndexType.LEXICAL: 0.3,
                IndexType.SYMBOL: 0.1,
            },
        )
        assert intent.weights[IndexType.VECTOR] == 0.6
        assert sum(intent.weights.values()) == pytest.approx(1.0)

    def test_low_confidence_intent(self):
        """Low confidence intent"""
        intent = Intent(type=IntentType.LEXICAL, confidence=0.1)
        assert intent.confidence < 0.5


class TestEdgeCases:
    """Edge case tests"""

    def test_unicode_query(self):
        """Unicode in query"""
        query = SearchQuery(query="함수 검색 🔍", repo_id="repo")
        assert "함수" in query.query

    def test_special_chars_in_content(self):
        """Special characters in content"""
        hit = SearchHit(id="1", score=0.9, content='def foo(x: "bar") -> None:')
        assert '"bar"' in hit.content

    def test_very_long_content(self):
        """Very long content"""
        content = "x" * 100000
        hit = SearchHit(id="1", score=0.5, content=content)
        assert len(hit.content) == 100000

    def test_zero_ms_search(self):
        """Zero milliseconds (cached result)"""
        result = SearchResult(query="cached", hits=[], total=0, took_ms=0.0)
        assert result.took_ms == 0.0
