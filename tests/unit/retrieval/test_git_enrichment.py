"""
Unit tests for Git History Enrichment

Tests git adapter and git-aware ranker integration.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit
from codegraph_search.infrastructure.fusion.engine import FusedHit
from codegraph_search.infrastructure.git_enrichment.adapter import GitHistoryAdapter
from codegraph_search.infrastructure.git_enrichment.ranker import GitAwareRanker
from codegraph_search.infrastructure.intent.models import IntentKind, QueryIntent


class TestGitHistoryAdapter:
    """Test GitHistoryAdapter."""

    def test_init_no_git_service(self, tmp_path):
        """Test initialization when git service is unavailable."""
        # Non-git directory
        adapter = GitHistoryAdapter(tmp_path)
        assert adapter.enabled is False

    def test_enrich_hits_disabled(self):
        """Test enrichment when disabled."""
        adapter = GitHistoryAdapter(".")
        adapter.enabled = False

        hits = [
            SearchHit(
                chunk_id="chunk1",
                file_path="src/main.py",
                symbol_id=None,
                score=0.9,
                source="lexical",
                metadata={},
            )
        ]

        enriched = adapter.enrich_hits(hits)
        assert len(enriched) == 1
        assert "git_churn_score" not in enriched[0].metadata

    @patch("src.contexts.retrieval_search.infrastructure.git_enrichment.adapter.create_git_service")
    def test_enrich_hits_with_metrics(self, mock_create_service):
        """Test enrichment with git metrics."""
        # Mock git service
        mock_service = Mock()
        mock_service.get_file_authors.return_value = {
            "user@example.com": Mock(email="user@example.com", commit_count=5)
        }
        mock_service.get_file_history.return_value = [
            (
                Mock(
                    commit_date=datetime.now() - timedelta(days=3),
                    hexsha="abc123",
                ),
                Mock(lines_added=10, lines_deleted=5),
            )
        ]
        mock_create_service.return_value = mock_service

        adapter = GitHistoryAdapter(".")
        adapter.git_service = mock_service
        adapter.enabled = True

        hits = [
            SearchHit(
                chunk_id="chunk1",
                file_path="src/main.py",
                symbol_id=None,
                score=0.9,
                source="lexical",
                metadata={},
            )
        ]

        enriched = adapter.enrich_hits(hits)

        assert len(enriched) == 1
        assert "git_churn_score" in enriched[0].metadata
        assert "git_last_modified_days" in enriched[0].metadata
        assert "git_author_count" in enriched[0].metadata
        assert enriched[0].metadata["git_last_modified_days"] == 3
        assert enriched[0].metadata["git_author_count"] == 1


class TestGitAwareRanker:
    """Test GitAwareRanker."""

    def test_rerank_flow_trace_recency_boost(self):
        """Test recency boost for FLOW_TRACE intent."""
        ranker = GitAwareRanker(recency_days_threshold=30)

        hits = [
            FusedHit(
                chunk_id="chunk1",
                file_path="src/old.py",
                symbol_id=None,
                fused_score=0.8,
                priority_score=0.8,
                metadata={"git_last_modified_days": 100},
            ),
            FusedHit(
                chunk_id="chunk2",
                file_path="src/recent.py",
                symbol_id=None,
                fused_score=0.7,
                priority_score=0.7,
                metadata={"git_last_modified_days": 3},
            ),
        ]

        intent = QueryIntent(kind=IntentKind.FLOW_TRACE, raw_query="trace flow")

        reranked = ranker.rerank(hits, intent)

        # Recent file should be boosted to top
        assert reranked[0].chunk_id == "chunk2"
        assert "git_boost" in reranked[0].metadata
        assert reranked[0].metadata["git_boost"] > 0

    def test_rerank_code_search_hotspot_penalty(self):
        """Test hotspot penalty for CODE_SEARCH intent."""
        ranker = GitAwareRanker(hotspot_penalty=0.1)

        hits = [
            FusedHit(
                chunk_id="chunk1",
                file_path="src/hotspot.py",
                symbol_id=None,
                fused_score=0.9,
                priority_score=0.9,
                metadata={"git_is_hotspot": True, "git_churn_score": 0.8},
            ),
            FusedHit(
                chunk_id="chunk2",
                file_path="src/stable.py",
                symbol_id=None,
                fused_score=0.8,
                priority_score=0.8,
                metadata={"git_is_hotspot": False, "git_churn_score": 0.2},
            ),
        ]

        intent = QueryIntent(kind=IntentKind.CODE_SEARCH, raw_query="find function")

        reranked = ranker.rerank(hits, intent)

        # Hotspot should be penalized, stable should be boosted
        assert reranked[0].chunk_id == "chunk2"  # Stable code on top

    def test_get_recency_score(self):
        """Test recency score calculation."""
        ranker = GitAwareRanker()

        assert ranker.get_recency_score(0) == 1.0  # Today = max score
        # Exponential decay with time constant = 90 days
        # exp(-90/90) = exp(-1) ≈ 0.368
        assert 0.3 < ranker.get_recency_score(90) < 0.4
        assert ranker.get_recency_score(365) < 0.02  # Very old (exp(-365/90) ≈ 0.017)


class TestFusionEngineGitIntegration:
    """Test FusionEngine with git enrichment."""

    @patch("src.contexts.retrieval_search.infrastructure.git_enrichment.adapter.GitHistoryAdapter")
    @patch("src.contexts.retrieval_search.infrastructure.git_enrichment.ranker.GitAwareRanker")
    def test_fusion_with_git_enrichment(self, mock_ranker_class, mock_adapter_class):
        """Test fusion engine with git enrichment enabled."""
        from codegraph_search.infrastructure.fusion.engine import FusionEngine
        from codegraph_search.infrastructure.multi_index.orchestrator import MultiIndexResult

        # Mock git components
        mock_adapter = Mock()
        mock_adapter.enrich_fused_hits.return_value = []
        mock_adapter_class.return_value = mock_adapter

        mock_ranker = Mock()
        mock_ranker.rerank.return_value = []
        mock_ranker_class.return_value = mock_ranker

        # Create engine with git enrichment
        engine = FusionEngine(repo_path="/fake/repo", enable_git_enrichment=True)

        # Verify git components initialized
        assert engine.git_adapter is not None
        assert engine.git_ranker is not None

        # Test fusion
        multi_result = MultiIndexResult(
            lexical_hits=[],
            vector_hits=[],
            symbol_hits=[],
            graph_hits=[],
        )

        intent = QueryIntent(kind=IntentKind.CODE_SEARCH, raw_query="test")

        result = engine.fuse(multi_result, intent)

        # Verify git enrichment was called
        mock_adapter.enrich_fused_hits.assert_called_once()
        mock_ranker.rerank.assert_called_once()
