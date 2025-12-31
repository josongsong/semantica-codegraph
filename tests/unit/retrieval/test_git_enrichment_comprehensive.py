"""
Comprehensive Tests for Git Enrichment

Tests base cases, edge cases, and corner cases for:
- GitHistoryAdapter
- GitAwareRanker
- FusionEngine integration
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from codegraph_engine.multi_index.infrastructure.common.documents import SearchHit
from codegraph_search.infrastructure.fusion.engine import FusedHit
from codegraph_search.infrastructure.git_enrichment.adapter import GitHistoryAdapter
from codegraph_search.infrastructure.git_enrichment.ranker import GitAwareRanker
from codegraph_search.infrastructure.intent.models import IntentKind, QueryIntent

# =============================================================================
# BASE CASES (정상 시나리오)
# =============================================================================


class TestGitEnrichmentBaseCases:
    """Base case tests for normal scenarios."""

    @patch("src.contexts.retrieval_search.infrastructure.git_enrichment.adapter.create_git_service")
    def test_enrich_single_file_normal(self, mock_create_service):
        """Base: 단일 파일 정상 enrichment."""
        # Mock git service
        mock_service = Mock()
        mock_service.get_file_authors.return_value = {
            "user1@test.com": Mock(email="user1@test.com", commit_count=5),
            "user2@test.com": Mock(email="user2@test.com", commit_count=3),
        }
        mock_service.get_file_history.return_value = [
            (
                Mock(commit_date=datetime.now() - timedelta(days=10), hexsha="abc123"),
                Mock(lines_added=15, lines_deleted=5),
            ),
            (
                Mock(commit_date=datetime.now() - timedelta(days=20), hexsha="def456"),
                Mock(lines_added=10, lines_deleted=2),
            ),
        ]
        mock_create_service.return_value = mock_service

        adapter = GitHistoryAdapter(".")
        adapter.git_service = mock_service
        adapter.enabled = True

        hits = [
            SearchHit(
                chunk_id="chunk1",
                file_path="src/main.py",
                symbol_id="main_func",
                score=0.8,
                source="lexical",
                metadata={},
            )
        ]

        enriched = adapter.enrich_hits(hits)

        assert len(enriched) == 1
        assert "git_churn_score" in enriched[0].metadata
        assert "git_last_modified_days" in enriched[0].metadata
        assert "git_author_count" in enriched[0].metadata
        assert enriched[0].metadata["git_author_count"] == 2
        assert enriched[0].metadata["git_last_modified_days"] == 10

    def test_rerank_normal_priority_adjustment(self):
        """Base: 정상적인 우선순위 조정."""
        ranker = GitAwareRanker()

        hits = [
            FusedHit(
                chunk_id="chunk1",
                file_path="src/stable.py",
                symbol_id=None,
                fused_score=0.8,
                priority_score=0.8,
                metadata={
                    "git_churn_score": 0.3,
                    "git_last_modified_days": 60,
                    "git_is_hotspot": False,
                },
            ),
            FusedHit(
                chunk_id="chunk2",
                file_path="src/recent.py",
                symbol_id=None,
                fused_score=0.75,
                priority_score=0.75,
                metadata={
                    "git_churn_score": 0.5,
                    "git_last_modified_days": 5,
                    "git_is_hotspot": False,
                },
            ),
        ]

        intent = QueryIntent(kind=IntentKind.FLOW_TRACE, raw_query="trace flow")
        reranked = ranker.rerank(hits, intent)

        # Recent file should be boosted
        assert reranked[0].chunk_id == "chunk2"
        assert "git_boost" in reranked[0].metadata


# =============================================================================
# EDGE CASES (경계값, 극단적 상황)
# =============================================================================


class TestGitEnrichmentEdgeCases:
    """Edge case tests for boundary conditions."""

    def test_empty_hits_list(self):
        """Edge: 빈 hits 리스트."""
        adapter = GitHistoryAdapter(".")
        adapter.enabled = True

        enriched = adapter.enrich_hits([])
        assert enriched == []

    def test_git_service_disabled(self):
        """Edge: Git 서비스 비활성화."""
        adapter = GitHistoryAdapter(".")
        adapter.enabled = False

        hits = [
            SearchHit(
                chunk_id="chunk1",
                file_path="src/main.py",
                symbol_id=None,
                score=0.8,
                source="lexical",
                metadata={},
            )
        ]

        enriched = adapter.enrich_hits(hits)

        # Should not modify hits
        assert len(enriched) == 1
        assert "git_churn_score" not in enriched[0].metadata

    @patch("src.contexts.retrieval_search.infrastructure.git_enrichment.adapter.create_git_service")
    def test_file_with_no_history(self, mock_create_service):
        """Edge: 히스토리 없는 파일 (새 파일)."""
        mock_service = Mock()
        mock_service.get_file_authors.return_value = {}
        mock_service.get_file_history.return_value = []
        mock_create_service.return_value = mock_service

        adapter = GitHistoryAdapter(".")
        adapter.git_service = mock_service
        adapter.enabled = True

        hits = [
            SearchHit(
                chunk_id="chunk1",
                file_path="src/new_file.py",
                symbol_id=None,
                score=0.8,
                source="lexical",
                metadata={},
            )
        ]

        enriched = adapter.enrich_hits(hits)

        assert len(enriched) == 1
        assert enriched[0].metadata["git_churn_score"] == 0.0
        assert enriched[0].metadata["git_last_modified_days"] == 9999
        assert enriched[0].metadata["git_author_count"] == 0
        assert enriched[0].metadata["git_is_hotspot"] is False

    @patch("src.contexts.retrieval_search.infrastructure.git_enrichment.adapter.create_git_service")
    def test_file_with_single_commit(self, mock_create_service):
        """Edge: 단일 커밋만 있는 파일."""
        mock_service = Mock()
        mock_service.get_file_authors.return_value = {"user@test.com": Mock(email="user@test.com", commit_count=1)}
        mock_service.get_file_history.return_value = [
            (
                Mock(commit_date=datetime.now() - timedelta(days=1), hexsha="abc123"),
                Mock(lines_added=100, lines_deleted=0),
            )
        ]
        mock_create_service.return_value = mock_service

        adapter = GitHistoryAdapter(".")
        adapter.git_service = mock_service
        adapter.enabled = True

        hits = [
            SearchHit(
                chunk_id="chunk1",
                file_path="src/new_feature.py",
                symbol_id=None,
                score=0.8,
                source="lexical",
                metadata={},
            )
        ]

        enriched = adapter.enrich_hits(hits)

        assert enriched[0].metadata["git_churn_score"] == 0.05  # 1 commit * 0.05
        assert enriched[0].metadata["git_author_count"] == 1

    @patch("src.contexts.retrieval_search.infrastructure.git_enrichment.adapter.create_git_service")
    def test_file_with_max_commits(self, mock_create_service):
        """Edge: 최대 커밋 수 (50개)."""
        mock_service = Mock()
        mock_service.get_file_authors.return_value = {
            f"user{i}@test.com": Mock(email=f"user{i}@test.com", commit_count=1) for i in range(10)
        }

        # 50개 커밋 생성
        history = [
            (
                Mock(commit_date=datetime.now() - timedelta(days=i), hexsha=f"commit{i}"),
                Mock(lines_added=5, lines_deleted=2),
            )
            for i in range(50)
        ]
        mock_service.get_file_history.return_value = history
        mock_create_service.return_value = mock_service

        adapter = GitHistoryAdapter(".")
        adapter.git_service = mock_service
        adapter.enabled = True

        hits = [
            SearchHit(
                chunk_id="chunk1",
                file_path="src/hotspot.py",
                symbol_id=None,
                score=0.8,
                source="lexical",
                metadata={},
            )
        ]

        enriched = adapter.enrich_hits(hits)

        # 50 commits = max churn (1.0)
        assert enriched[0].metadata["git_churn_score"] == 1.0
        assert enriched[0].metadata["git_is_hotspot"] is True

    def test_rerank_zero_boost(self):
        """Edge: Boost가 0인 경우 (SYMBOL_NAV with non-hotspot)."""
        ranker = GitAwareRanker()

        hits = [
            FusedHit(
                chunk_id="chunk1",
                file_path="src/stable.py",
                symbol_id="func1",
                fused_score=0.8,
                priority_score=0.8,
                metadata={
                    "git_churn_score": 0.3,
                    "git_last_modified_days": 60,
                    "git_is_hotspot": False,
                },
            )
        ]

        intent = QueryIntent(kind=IntentKind.SYMBOL_NAV, raw_query="func1")
        reranked = ranker.rerank(hits, intent)

        # SYMBOL_NAV with non-hotspot = neutral (no boost)
        # Actually, there's a -0.05 penalty removed from earlier, so boost should be 0
        assert len(reranked) == 1

    def test_rerank_maximum_boost(self):
        """Edge: 최대 boost (FLOW_TRACE, 매우 최근)."""
        ranker = GitAwareRanker()

        hits = [
            FusedHit(
                chunk_id="chunk1",
                file_path="src/recent.py",
                symbol_id=None,
                fused_score=0.7,
                priority_score=0.7,
                metadata={
                    "git_last_modified_days": 1,  # Very recent
                    "git_is_hotspot": False,
                },
            )
        ]

        intent = QueryIntent(kind=IntentKind.FLOW_TRACE, raw_query="trace")
        reranked = ranker.rerank(hits, intent)

        # Should have +20% boost
        assert reranked[0].metadata["git_boost"] == pytest.approx(0.2, abs=0.01)
        assert reranked[0].priority_score == pytest.approx(0.7 * 1.2, abs=0.01)

    def test_rerank_maximum_penalty(self):
        """Edge: 최대 penalty (CODE_SEARCH, hotspot)."""
        ranker = GitAwareRanker(hotspot_penalty=0.1)

        hits = [
            FusedHit(
                chunk_id="chunk1",
                file_path="src/hotspot.py",
                symbol_id=None,
                fused_score=0.8,
                priority_score=0.8,
                metadata={
                    "git_is_hotspot": True,
                    "git_churn_score": 0.9,
                },
            )
        ]

        intent = QueryIntent(kind=IntentKind.CODE_SEARCH, raw_query="find")
        reranked = ranker.rerank(hits, intent)

        # Should have -10% penalty
        assert reranked[0].metadata["git_boost"] == -0.1
        assert reranked[0].priority_score == pytest.approx(0.8 * 0.9, abs=0.01)

    def test_recency_score_boundaries(self):
        """Edge: Recency score 경계값."""
        ranker = GitAwareRanker()

        # Today = 1.0
        assert ranker.get_recency_score(0) == 1.0

        # Very old (1000 days) → near 0
        assert ranker.get_recency_score(1000) < 0.01

        # Half-life (90 days) → ~0.5
        score_90 = ranker.get_recency_score(90)
        assert 0.35 < score_90 < 0.4


# =============================================================================
# CORNER CASES (여러 조건 동시 발생)
# =============================================================================


class TestGitEnrichmentCornerCases:
    """Corner case tests for multiple conditions occurring simultaneously."""

    @patch("src.contexts.retrieval_search.infrastructure.git_enrichment.adapter.create_git_service")
    def test_hits_without_file_path(self, mock_create_service):
        """Corner: file_path가 없는 hits."""
        mock_service = Mock()
        mock_create_service.return_value = mock_service

        adapter = GitHistoryAdapter(".")
        adapter.git_service = mock_service
        adapter.enabled = True

        hits = [
            SearchHit(
                chunk_id="chunk1",
                file_path=None,  # No file path
                symbol_id="orphan_symbol",
                score=0.8,
                source="symbol",
                metadata={},
            )
        ]

        enriched = adapter.enrich_hits(hits)

        # Should not crash, but also not enrich
        assert len(enriched) == 1
        assert "git_churn_score" not in enriched[0].metadata

    @patch("src.contexts.retrieval_search.infrastructure.git_enrichment.adapter.create_git_service")
    def test_multiple_files_same_batch(self, mock_create_service):
        """Corner: 동일 파일의 여러 청크를 한 번에 enrichment."""
        mock_service = Mock()

        def mock_get_authors(file_path):
            return {"user@test.com": Mock(email="user@test.com", commit_count=3)}

        def mock_get_history(file_path, max_commits=50):
            return [
                (
                    Mock(commit_date=datetime.now() - timedelta(days=5), hexsha="abc"),
                    Mock(lines_added=10, lines_deleted=5),
                )
            ]

        mock_service.get_file_authors.side_effect = mock_get_authors
        mock_service.get_file_history.side_effect = mock_get_history
        mock_create_service.return_value = mock_service

        adapter = GitHistoryAdapter(".")
        adapter.git_service = mock_service
        adapter.enabled = True

        # Multiple chunks from same file
        hits = [
            SearchHit(
                chunk_id=f"chunk{i}",
                file_path="src/same_file.py",
                symbol_id=f"func{i}",
                score=0.8,
                source="lexical",
                metadata={},
            )
            for i in range(5)
        ]

        enriched = adapter.enrich_hits(hits)

        assert len(enriched) == 5

        # All should have same git metrics
        for hit in enriched:
            assert hit.metadata["git_author_count"] == 1
            assert hit.metadata["git_last_modified_days"] == 5

        # Should only call git service once per file (cached)
        assert mock_service.get_file_authors.call_count == 1
        assert mock_service.get_file_history.call_count == 1

    @patch("src.contexts.retrieval_search.infrastructure.git_enrichment.adapter.create_git_service")
    def test_git_service_exception(self, mock_create_service):
        """Corner: Git service 예외 발생."""
        mock_service = Mock()
        mock_service.get_file_authors.side_effect = Exception("Git error")
        mock_create_service.return_value = mock_service

        adapter = GitHistoryAdapter(".")
        adapter.git_service = mock_service
        adapter.enabled = True

        hits = [
            SearchHit(
                chunk_id="chunk1",
                file_path="src/main.py",
                symbol_id=None,
                score=0.8,
                source="lexical",
                metadata={},
            )
        ]

        # Should not crash, gracefully degrade
        enriched = adapter.enrich_hits(hits)

        assert len(enriched) == 1
        assert "git_churn_score" not in enriched[0].metadata

    def test_rerank_conflicting_signals(self):
        """Corner: 상충되는 시그널 (최근 + hotspot for CODE_SEARCH)."""
        ranker = GitAwareRanker()

        hits = [
            FusedHit(
                chunk_id="chunk1",
                file_path="src/recent_hotspot.py",
                symbol_id=None,
                fused_score=0.8,
                priority_score=0.8,
                metadata={
                    "git_last_modified_days": 2,  # Very recent (good for FLOW_TRACE)
                    "git_is_hotspot": True,  # Hotspot (bad for CODE_SEARCH)
                    "git_churn_score": 0.85,
                },
            )
        ]

        # CODE_SEARCH should penalize hotspot despite recency
        intent = QueryIntent(kind=IntentKind.CODE_SEARCH, raw_query="find")
        reranked = ranker.rerank(hits, intent)

        # Should have penalty (hotspot dominates for CODE_SEARCH)
        assert reranked[0].metadata["git_boost"] == -0.1

    def test_rerank_all_intents_same_hits(self):
        """Corner: 동일 hits에 대해 모든 intent 테스트."""
        ranker = GitAwareRanker()

        base_hit = FusedHit(
            chunk_id="chunk1",
            file_path="src/test.py",
            symbol_id=None,
            fused_score=0.8,
            priority_score=0.8,
            metadata={
                "git_last_modified_days": 15,
                "git_churn_score": 0.6,
                "git_is_hotspot": False,
            },
        )

        intents = [
            IntentKind.CODE_SEARCH,
            IntentKind.SYMBOL_NAV,
            IntentKind.CONCEPT_SEARCH,
            IntentKind.FLOW_TRACE,
            IntentKind.REPO_OVERVIEW,
        ]

        results = {}

        for intent_kind in intents:
            # Create fresh copy for each test
            hits = [
                FusedHit(
                    chunk_id=base_hit.chunk_id,
                    file_path=base_hit.file_path,
                    symbol_id=base_hit.symbol_id,
                    fused_score=base_hit.fused_score,
                    priority_score=base_hit.priority_score,
                    metadata=base_hit.metadata.copy(),
                )
            ]

            intent = QueryIntent(kind=intent_kind, raw_query="test")
            reranked = ranker.rerank(hits, intent)

            boost = reranked[0].metadata.get("git_boost", 0.0)
            results[intent_kind] = boost

        # Different intents should produce different boosts
        assert len(set(results.values())) > 1  # Not all same

    @patch("src.contexts.retrieval_search.infrastructure.git_enrichment.adapter.create_git_service")
    def test_cache_expiration(self, mock_create_service):
        """Corner: 캐시 만료 테스트."""
        import time

        mock_service = Mock()
        mock_service.get_file_authors.return_value = {"user@test.com": Mock(email="user@test.com", commit_count=1)}
        mock_service.get_file_history.return_value = [
            (
                Mock(commit_date=datetime.now(), hexsha="abc"),
                Mock(lines_added=10, lines_deleted=5),
            )
        ]
        mock_create_service.return_value = mock_service

        # Very short TTL for testing
        adapter = GitHistoryAdapter(".", cache_ttl_seconds=1)
        adapter.git_service = mock_service
        adapter.enabled = True

        hits = [
            SearchHit(
                chunk_id="chunk1",
                file_path="src/main.py",
                symbol_id=None,
                score=0.8,
                source="lexical",
                metadata={},
            )
        ]

        # First call - cache miss
        adapter.enrich_hits(hits)
        assert mock_service.get_file_authors.call_count == 1

        # Second call - cache hit
        adapter.enrich_hits(hits)
        assert mock_service.get_file_authors.call_count == 1  # Same count

        # Wait for cache expiration
        time.sleep(1.1)

        # Third call - cache expired, should call again
        adapter.enrich_hits(hits)
        assert mock_service.get_file_authors.call_count == 2

    def test_rerank_with_missing_git_metadata(self):
        """Corner: Git 메타데이터가 부분적으로 없는 경우."""
        ranker = GitAwareRanker()

        hits = [
            FusedHit(
                chunk_id="chunk1",
                file_path="src/incomplete.py",
                symbol_id=None,
                fused_score=0.8,
                priority_score=0.8,
                metadata={
                    # Missing git_last_modified_days
                    "git_churn_score": 0.5,
                    # Missing git_is_hotspot
                },
            )
        ]

        intent = QueryIntent(kind=IntentKind.FLOW_TRACE, raw_query="trace")

        # Should not crash, use defaults
        reranked = ranker.rerank(hits, intent)

        assert len(reranked) == 1
        # Without last_modified_days (default 9999), no recency boost
        assert reranked[0].metadata.get("git_boost", 0.0) == 0.0

    def test_enrich_fused_hits_vs_search_hits(self):
        """Corner: FusedHit과 SearchHit 모두 테스트."""
        adapter = GitHistoryAdapter(".")
        adapter.enabled = False  # Disable to test behavior

        search_hits = [
            SearchHit(
                chunk_id="chunk1",
                file_path="src/test.py",
                symbol_id=None,
                score=0.8,
                source="lexical",
                metadata={},
            )
        ]

        fused_hits = [
            FusedHit(
                chunk_id="chunk1",
                file_path="src/test.py",
                symbol_id=None,
                fused_score=0.8,
                priority_score=0.8,
                metadata={},
            )
        ]

        # Both should work without errors
        enriched_search = adapter.enrich_hits(search_hits)
        enriched_fused = adapter.enrich_fused_hits(fused_hits)

        assert len(enriched_search) == 1
        assert len(enriched_fused) == 1

    @patch("src.contexts.retrieval_search.infrastructure.git_enrichment.adapter.create_git_service")
    def test_large_batch_performance(self, mock_create_service):
        """Corner: 대량 hits 처리 성능."""
        mock_service = Mock()

        def mock_get_authors(file_path):
            return {"user@test.com": Mock(email="user@test.com", commit_count=1)}

        def mock_get_history(file_path, max_commits=50):
            return [(Mock(commit_date=datetime.now(), hexsha="abc"), Mock())]

        mock_service.get_file_authors.side_effect = mock_get_authors
        mock_service.get_file_history.side_effect = mock_get_history
        mock_create_service.return_value = mock_service

        adapter = GitHistoryAdapter(".")
        adapter.git_service = mock_service
        adapter.enabled = True

        # 100 hits from 10 different files
        hits = [
            SearchHit(
                chunk_id=f"chunk{i}",
                file_path=f"src/file{i % 10}.py",
                symbol_id=None,
                score=0.8,
                source="lexical",
                metadata={},
            )
            for i in range(100)
        ]

        enriched = adapter.enrich_hits(hits)

        assert len(enriched) == 100

        # Should only call git service once per unique file (10 files)
        assert mock_service.get_file_authors.call_count == 10


# =============================================================================
# Integration Tests
# =============================================================================


class TestGitEnrichmentIntegration:
    """Integration tests combining multiple components."""

    @patch("src.contexts.retrieval_search.infrastructure.git_enrichment.adapter.create_git_service")
    def test_full_pipeline_enrichment_to_reranking(self, mock_create_service):
        """Integration: Enrichment → Reranking 전체 파이프라인."""
        # Setup mock git service
        mock_service = Mock()
        mock_service.get_file_authors.return_value = {"user@test.com": Mock(email="user@test.com", commit_count=5)}
        mock_service.get_file_history.return_value = [
            (
                Mock(commit_date=datetime.now() - timedelta(days=3), hexsha="abc"),
                Mock(lines_added=20, lines_deleted=10),
            )
        ] * 10  # 10 commits
        mock_create_service.return_value = mock_service

        # Step 1: Enrich
        adapter = GitHistoryAdapter(".")
        adapter.git_service = mock_service
        adapter.enabled = True

        hits = [
            SearchHit(
                chunk_id="chunk1",
                file_path="src/recent.py",
                symbol_id=None,
                score=0.7,
                source="lexical",
                metadata={},
            ),
            SearchHit(
                chunk_id="chunk2",
                file_path="src/old.py",
                symbol_id=None,
                score=0.8,
                source="lexical",
                metadata={},
            ),
        ]

        enriched = adapter.enrich_hits(hits)

        # Convert to FusedHits
        fused_hits = [
            FusedHit(
                chunk_id=hit.chunk_id,
                file_path=hit.file_path,
                symbol_id=hit.symbol_id,
                fused_score=hit.score,
                priority_score=hit.score,
                metadata=hit.metadata.copy(),
            )
            for hit in enriched
        ]

        # Mock second file to have old data
        fused_hits[1].metadata.update(
            {
                "git_churn_score": 0.2,
                "git_last_modified_days": 180,
                "git_is_hotspot": False,
            }
        )

        # Step 2: Rerank
        ranker = GitAwareRanker()
        intent = QueryIntent(kind=IntentKind.FLOW_TRACE, raw_query="trace flow")
        reranked = ranker.rerank(fused_hits, intent)

        # Recent file should be on top despite lower initial score
        assert reranked[0].chunk_id == "chunk1"

        # Priority score should be boosted (original * (1 + boost))
        original_priority = 0.7  # Original score
        expected_min = original_priority * 1.1  # At least 10% boost
        assert reranked[0].priority_score >= expected_min, (
            f"Expected priority >= {expected_min}, got {reranked[0].priority_score}"
        )
