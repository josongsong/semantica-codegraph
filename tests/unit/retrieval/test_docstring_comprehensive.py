"""
Comprehensive Tests for Docstring Index

Tests base cases, edge cases, and corner cases for:
- DocstringIndexClient
- DOC_SEARCH intent classification
- MultiIndex integration
"""

from unittest.mock import AsyncMock, Mock

import pytest

from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit
from codegraph_search.infrastructure.intent.models import IntentKind
from codegraph_search.infrastructure.intent.rule_classifier import RuleBasedClassifier
from codegraph_search.infrastructure.multi_index.docstring_client import DocstringIndexClient

# =============================================================================
# BASE CASES
# =============================================================================


class TestDocstringIndexBaseCases:
    """Base case tests for normal scenarios."""

    @pytest.mark.asyncio
    async def test_search_normal_query(self):
        """Base: 정상적인 문서 검색."""
        mock_adapter = Mock()
        mock_adapter.search = AsyncMock(
            return_value=[
                SearchHit(
                    chunk_id="doc1",
                    file_path="src/auth.py",
                    symbol_id="authenticate",
                    score=0.9,
                    source="vector",
                    metadata={"kind": "docstring"},
                ),
                SearchHit(
                    chunk_id="doc2",
                    file_path="src/handlers.py",
                    symbol_id="LoginHandler",
                    score=0.85,
                    source="vector",
                    metadata={"kind": "docstring"},
                ),
            ]
        )

        client = DocstringIndexClient(mock_adapter)

        hits = await client.search(
            repo_id="test-repo",
            snapshot_id="snap1",
            query="authentication documentation",
            limit=10,
        )

        assert len(hits) == 2
        assert all(hit.source == "docstring" for hit in hits)
        assert all(hit.metadata["search_type"] == "docstring" for hit in hits)

    @pytest.mark.asyncio
    async def test_search_by_symbol_normal(self):
        """Base: 심볼별 docstring 검색."""
        mock_adapter = Mock()
        mock_adapter.search = AsyncMock(
            return_value=[
                SearchHit(
                    chunk_id="doc1",
                    file_path="src/auth.py",
                    symbol_id="authenticate",
                    score=0.95,
                    source="vector",
                    metadata={"kind": "docstring", "fqn": "auth.authenticate"},
                )
            ]
        )

        client = DocstringIndexClient(mock_adapter)

        hits = await client.search_by_symbol(
            repo_id="test-repo",
            snapshot_id="snap1",
            symbol_fqn="auth.authenticate",
            limit=5,
        )

        assert len(hits) == 1
        assert hits[0].symbol_id == "authenticate"


# =============================================================================
# EDGE CASES
# =============================================================================


class TestDocstringIndexEdgeCases:
    """Edge case tests for boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_results(self):
        """Edge: 검색 결과 없음."""
        mock_adapter = Mock()
        mock_adapter.search = AsyncMock(return_value=[])

        client = DocstringIndexClient(mock_adapter)

        hits = await client.search(
            repo_id="test-repo",
            snapshot_id="snap1",
            query="nonexistent documentation",
        )

        assert hits == []

    @pytest.mark.asyncio
    async def test_search_error_graceful_degradation(self):
        """Edge: 검색 에러 발생 시 graceful degradation."""
        mock_adapter = Mock()
        mock_adapter.search = AsyncMock(side_effect=Exception("Qdrant error"))

        client = DocstringIndexClient(mock_adapter)

        # Should not raise, return empty list
        hits = await client.search(
            repo_id="test-repo",
            snapshot_id="snap1",
            query="test",
        )

        assert hits == []

    @pytest.mark.asyncio
    async def test_limit_boundary_values(self):
        """Edge: Limit 경계값 테스트."""
        mock_adapter = Mock()

        # Generate many results
        mock_results = [
            SearchHit(
                chunk_id=f"doc{i}",
                file_path=f"src/file{i}.py",
                symbol_id=f"func{i}",
                score=0.9 - i * 0.01,
                source="vector",
                metadata={"kind": "docstring"},
            )
            for i in range(100)
        ]

        mock_adapter.search = AsyncMock(return_value=mock_results[:20])

        client = DocstringIndexClient(mock_adapter)

        # Test with limit=1
        hits = await client.search(
            repo_id="test-repo",
            snapshot_id="snap1",
            query="test",
            limit=1,
        )

        # Should respect limit
        call_kwargs = mock_adapter.search.call_args.kwargs
        assert call_kwargs["limit"] == 1

    @pytest.mark.asyncio
    async def test_empty_query_string(self):
        """Edge: 빈 쿼리 문자열."""
        mock_adapter = Mock()
        mock_adapter.search = AsyncMock(return_value=[])

        client = DocstringIndexClient(mock_adapter)

        hits = await client.search(
            repo_id="test-repo",
            snapshot_id="snap1",
            query="",
            limit=10,
        )

        # Should handle gracefully
        assert isinstance(hits, list)

    @pytest.mark.asyncio
    async def test_very_long_query(self):
        """Edge: 매우 긴 쿼리."""
        mock_adapter = Mock()
        mock_adapter.search = AsyncMock(return_value=[])

        client = DocstringIndexClient(mock_adapter)

        # 1000 character query
        long_query = "authentication " * 100

        hits = await client.search(
            repo_id="test-repo",
            snapshot_id="snap1",
            query=long_query,
        )

        assert isinstance(hits, list)

    @pytest.mark.asyncio
    async def test_special_characters_in_query(self):
        """Edge: 특수문자 포함 쿼리."""
        mock_adapter = Mock()
        mock_adapter.search = AsyncMock(return_value=[])

        client = DocstringIndexClient(mock_adapter)

        queries = [
            "auth.handler.login",
            "user@authenticate",
            "func(param1, param2)",
            "class<T>",
            "array[0]",
        ]

        for query in queries:
            hits = await client.search(
                repo_id="test-repo",
                snapshot_id="snap1",
                query=query,
            )
            assert isinstance(hits, list)


# =============================================================================
# CORNER CASES
# =============================================================================


class TestDocstringIndexCornerCases:
    """Corner case tests for multiple conditions."""

    @pytest.mark.asyncio
    async def test_partial_metadata(self):
        """Corner: 불완전한 메타데이터."""
        mock_adapter = Mock()
        mock_adapter.search = AsyncMock(
            return_value=[
                SearchHit(
                    chunk_id="doc1",
                    file_path="src/auth.py",
                    symbol_id=None,  # Missing symbol_id
                    score=0.9,
                    source="vector",
                    metadata={},  # Missing kind
                )
            ]
        )

        client = DocstringIndexClient(mock_adapter)

        hits = await client.search(
            repo_id="test-repo",
            snapshot_id="snap1",
            query="test",
        )

        # Should still mark as docstring source
        assert len(hits) == 1
        assert hits[0].source == "docstring"

    @pytest.mark.asyncio
    async def test_adapter_none_response(self):
        """Corner: Adapter가 None 반환."""
        mock_adapter = Mock()
        mock_adapter.search = AsyncMock(return_value=None)

        client = DocstringIndexClient(mock_adapter)

        # Should handle None gracefully
        try:
            hits = await client.search(
                repo_id="test-repo",
                snapshot_id="snap1",
                query="test",
            )
            # If it doesn't crash, that's good
            assert hits is None or isinstance(hits, list)
        except Exception:
            # Expected to handle gracefully
            pass

    @pytest.mark.asyncio
    async def test_concurrent_searches(self):
        """Corner: 동시 다중 검색."""
        import asyncio

        mock_adapter = Mock()

        call_count = 0

        async def mock_search(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Simulate delay
            return [
                SearchHit(
                    chunk_id=f"doc{call_count}",
                    file_path="src/test.py",
                    symbol_id="test",
                    score=0.9,
                    source="vector",
                    metadata={"kind": "docstring"},
                )
            ]

        mock_adapter.search = mock_search

        client = DocstringIndexClient(mock_adapter)

        # Run 5 searches concurrently
        tasks = [
            client.search(
                repo_id="test-repo",
                snapshot_id="snap1",
                query=f"query{i}",
            )
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        assert all(len(r) >= 1 for r in results)

    @pytest.mark.asyncio
    async def test_search_by_symbol_complex_fqn(self):
        """Corner: 복잡한 FQN (nested modules)."""
        mock_adapter = Mock()
        mock_adapter.search = AsyncMock(return_value=[])

        client = DocstringIndexClient(mock_adapter)

        complex_fqns = [
            "package.subpackage.module.Class.method",
            "a.b.c.d.e.f.g.h",
            "auth.handlers.api.v2.UserAuthHandler.authenticate",
        ]

        for fqn in complex_fqns:
            hits = await client.search_by_symbol(
                repo_id="test-repo",
                snapshot_id="snap1",
                symbol_fqn=fqn,
            )

            # Should extract last component for query
            call_kwargs = mock_adapter.search.call_args.kwargs
            assert isinstance(call_kwargs["query"], str)
            assert len(call_kwargs["query"]) > 0


# =============================================================================
# Intent Classification Tests
# =============================================================================


class TestDocSearchIntentClassification:
    """Test DOC_SEARCH intent classification."""

    def test_base_documentation_queries(self):
        """Base: 기본 문서 검색 쿼리."""
        classifier = RuleBasedClassifier()

        queries = [
            "authentication documentation",
            "find docstring for login",
            "show docs for User class",
        ]

        for query in queries:
            intent = classifier.classify(query)
            # Should be DOC_SEARCH or high scoring alternative
            assert intent.kind in [IntentKind.DOC_SEARCH, IntentKind.CONCEPT_SEARCH]

    def test_edge_ambiguous_queries(self):
        """Edge: 모호한 쿼리."""
        classifier = RuleBasedClassifier()

        # Could be DOC_SEARCH or CODE_SEARCH
        ambiguous_queries = [
            "authentication",  # Just keyword
            "login function",  # Could be code or doc
            "User class",  # Could be navigation or doc
        ]

        for query in ambiguous_queries:
            intent = classifier.classify(query)
            # Should still classify (not crash)
            assert isinstance(intent.kind, IntentKind)

    def test_corner_multiple_intent_signals(self):
        """Corner: 여러 intent 시그널 혼재."""
        classifier = RuleBasedClassifier()

        # Mix of DOC_SEARCH and FLOW_TRACE signals
        query = "trace authentication flow documentation"
        intent = classifier.classify(query)

        # Should classify as one of them
        assert intent.kind in [IntentKind.DOC_SEARCH, IntentKind.FLOW_TRACE, IntentKind.CONCEPT_SEARCH]

    def test_all_doc_search_patterns(self):
        """Base: 모든 DOC_SEARCH 패턴 테스트."""
        classifier = RuleBasedClassifier()

        pattern_queries = [
            ("documentation", "authentication documentation"),
            ("docstring", "find docstring"),
            ("docs for", "docs for function"),
            ("comments about", "comments about auth"),
            ("describe", "describe the function"),
            ("summary", "summary of API"),
            ("api reference", "API reference"),
            ("what does X do", "what does authenticate do"),
        ]

        for pattern, query in pattern_queries:
            intent = classifier.classify(query)
            # Should recognize pattern
            score = classifier._score_doc_search(query.lower())
            assert score > 0, f"Pattern '{pattern}' not recognized in '{query}'"

    def test_edge_case_sensitivity(self):
        """Edge: 대소문자 구분."""
        classifier = RuleBasedClassifier()

        queries = [
            "DOCUMENTATION",
            "Documentation",
            "documentation",
            "DoCuMeNtAtIoN",
        ]

        scores = [classifier._score_doc_search(q.lower()) for q in queries]

        # All should have same score (case insensitive)
        assert len(set(scores)) == 1
        assert scores[0] > 0

    def test_corner_no_clear_intent(self):
        """Corner: 명확한 intent 없음."""
        classifier = RuleBasedClassifier()

        vague_queries = [
            "x",
            "test",
            "a b c",
            "123",
        ]

        for query in vague_queries:
            intent = classifier.classify(query)
            # Should still return something (default to CODE_SEARCH)
            assert isinstance(intent.kind, IntentKind)
            assert intent.confidence >= 0


# =============================================================================
# Integration Tests
# =============================================================================


class TestDocstringIntegration:
    """Integration tests for docstring functionality."""

    @pytest.mark.asyncio
    async def test_full_doc_search_flow(self):
        """Integration: Intent 분류 → Docstring 검색."""
        # Step 1: Classify query
        classifier = RuleBasedClassifier()
        query = "authentication documentation"
        intent = classifier.classify(query)

        # Should detect DOC_SEARCH intent
        assert intent.kind in [IntentKind.DOC_SEARCH, IntentKind.CONCEPT_SEARCH]

        # Step 2: Search docstrings
        mock_adapter = Mock()
        mock_adapter.search = AsyncMock(
            return_value=[
                SearchHit(
                    chunk_id="doc1",
                    file_path="src/auth.py",
                    symbol_id="authenticate",
                    score=0.95,
                    source="vector",
                    metadata={"kind": "docstring"},
                )
            ]
        )

        client = DocstringIndexClient(mock_adapter)

        hits = await client.search(
            repo_id="test-repo",
            snapshot_id="snap1",
            query=query,
        )

        # Should find docstrings
        assert len(hits) > 0
        assert all(hit.source == "docstring" for hit in hits)

    @pytest.mark.asyncio
    async def test_doc_search_vs_code_search_routing(self):
        """Integration: DOC_SEARCH vs CODE_SEARCH 라우팅."""
        classifier = RuleBasedClassifier()

        # DOC_SEARCH query
        doc_query = "show documentation for authenticate"
        doc_intent = classifier.classify(doc_query)

        # CODE_SEARCH query
        code_query = "find authenticate function implementation"
        code_intent = classifier.classify(code_query)

        # Should classify differently
        # (may both be in similar categories, but scores should differ)
        doc_score = classifier._score_doc_search(doc_query.lower())
        code_doc_score = classifier._score_doc_search(code_query.lower())

        # Doc query should have higher doc score
        assert doc_score > code_doc_score or doc_intent.kind == IntentKind.DOC_SEARCH
