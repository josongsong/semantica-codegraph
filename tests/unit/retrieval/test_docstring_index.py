"""
Unit tests for Docstring Index Client

Tests docstring-only search functionality.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit
from codegraph_search.infrastructure.multi_index.docstring_client import DocstringIndexClient


class TestDocstringIndexClient:
    """Test DocstringIndexClient."""

    @pytest.mark.asyncio
    async def test_search_docstrings_only(self):
        """Test searching only docstring chunks."""
        # Mock vector adapter
        mock_adapter = Mock()
        mock_adapter.search = AsyncMock(
            return_value=[
                SearchHit(
                    chunk_id="doc1",
                    file_path="src/auth.py",
                    symbol_id="func1",
                    score=0.9,
                    source="vector",
                    metadata={"kind": "docstring"},
                )
            ]
        )

        client = DocstringIndexClient(mock_adapter)

        hits = await client.search(
            repo_id="test-repo",
            snapshot_id="snap1",
            query="authentication documentation",
            limit=20,
        )

        assert len(hits) == 1
        assert hits[0].source == "docstring"
        assert hits[0].metadata["search_type"] == "docstring"

        # Verify filter was applied
        mock_adapter.search.assert_called_once()
        call_kwargs = mock_adapter.search.call_args.kwargs
        assert "filter_conditions" in call_kwargs
        assert call_kwargs["filter_conditions"]["must"][0]["key"] == "kind"

    @pytest.mark.asyncio
    async def test_search_by_symbol(self):
        """Test searching docstrings for specific symbol."""
        mock_adapter = Mock()
        mock_adapter.search = AsyncMock(return_value=[])

        client = DocstringIndexClient(mock_adapter)

        hits = await client.search_by_symbol(
            repo_id="test-repo",
            snapshot_id="snap1",
            symbol_fqn="auth.handlers.authenticate",
            limit=5,
        )

        # Should construct query with symbol name
        mock_adapter.search.assert_called_once()
        call_kwargs = mock_adapter.search.call_args.kwargs
        assert "authenticate" in call_kwargs["query"]

        # Should filter by FQN
        filters = call_kwargs["filter_conditions"]["must"]
        assert any(f["key"] == "fqn" for f in filters)

    @pytest.mark.asyncio
    async def test_search_error_handling(self):
        """Test error handling in docstring search."""
        mock_adapter = Mock()
        mock_adapter.search = AsyncMock(side_effect=Exception("Search failed"))

        client = DocstringIndexClient(mock_adapter)

        # Should return empty list on error (graceful degradation)
        hits = await client.search(
            repo_id="test-repo",
            snapshot_id="snap1",
            query="test",
        )

        assert hits == []


class TestDocSearchIntent:
    """Test DOC_SEARCH intent classification."""

    def test_doc_search_patterns(self):
        """Test rule-based classification for doc search."""
        from codegraph_search.infrastructure.intent.models import IntentKind
        from codegraph_search.infrastructure.intent.rule_classifier import RuleBasedClassifier

        classifier = RuleBasedClassifier()

        # Test documentation keywords
        queries = [
            "authentication documentation",
            "find docstring for authenticate",
            "show docs for User class",
            "what does authenticate function do",
            "describe the login process",
            "API reference for handlers",
        ]

        for query in queries:
            intent = classifier.classify(query)
            # Should classify as DOC_SEARCH or at least have high doc score
            assert intent.kind in [IntentKind.DOC_SEARCH, IntentKind.CONCEPT_SEARCH]
