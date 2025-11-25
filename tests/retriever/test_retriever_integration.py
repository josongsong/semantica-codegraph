"""
Retriever Layer Integration Tests

Tests for the complete retrieval pipeline.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Retriever integration pending Priority 2 work")


from src.retriever.intent import IntentKind, RuleBasedClassifier

pytestmark = pytest.mark.skip(reason="Retriever integration pending Priority 2 work")

class TestIntentClassifier:
    """Test intent classification."""

    def test_rule_based_code_search(self):
        """Test rule-based classification for code search."""
        classifier = RuleBasedClassifier()

        intent = classifier.classify("user registration implementation in auth.py")

        assert intent.kind == IntentKind.CODE_SEARCH
        assert "registration" in intent.symbol_names or "auth" in intent.file_paths
        assert intent.confidence > 0.0

    def test_rule_based_symbol_nav(self):
        """Test rule-based classification for symbol navigation."""
        classifier = RuleBasedClassifier()

        intent = classifier.classify("find the authenticate function")

        assert intent.kind == IntentKind.SYMBOL_NAV
        assert "authenticate" in intent.symbol_names
        assert intent.confidence > 0.0

    def test_rule_based_concept_search(self):
        """Test rule-based classification for concept search."""
        classifier = RuleBasedClassifier()

        intent = classifier.classify("how does the authentication system work?")

        assert intent.kind == IntentKind.CONCEPT_SEARCH
        assert intent.is_nl is True
        assert intent.confidence > 0.0

    def test_rule_based_flow_trace(self):
        """Test rule-based classification for flow trace."""
        classifier = RuleBasedClassifier()

        intent = classifier.classify("trace the call chain from login to database")

        assert intent.kind == IntentKind.FLOW_TRACE
        assert intent.confidence > 0.0

    def test_rule_based_repo_overview(self):
        """Test rule-based classification for repo overview."""
        classifier = RuleBasedClassifier()

        intent = classifier.classify("show me the main entry points")

        assert intent.kind == IntentKind.REPO_OVERVIEW
        assert intent.confidence > 0.0


class TestFusionWeights:
    """Test fusion weight profiles."""

    def test_weight_profiles_exist(self):
        """Test that weight profiles are defined for all intents."""
        from src.retriever.fusion.weights import get_weights_for_intent

        # All intent kinds should have weights
        for intent_kind in IntentKind:
            weights = get_weights_for_intent(intent_kind)
            assert isinstance(weights, dict)
            assert len(weights) > 0

    def test_priority_score_weights(self):
        """Test priority score weights sum to 1.0."""
        from src.retriever.fusion.weights import (
            PRIORITY_FUSED_WEIGHT,
            PRIORITY_REPOMAP_WEIGHT,
            PRIORITY_SYMBOL_WEIGHT,
        )

        total = PRIORITY_FUSED_WEIGHT + PRIORITY_REPOMAP_WEIGHT + PRIORITY_SYMBOL_WEIGHT

        assert abs(total - 1.0) < 0.01  # Allow small floating point error


class TestScoreNormalization:
    """Test score normalization."""

    def test_normalize_lexical_scores(self):
        """Test lexical score normalization."""
        from src.index.common.documents import SearchHit
        from src.retriever.fusion.normalizer import ScoreNormalizer

        normalizer = ScoreNormalizer()

        # Create test hits with varying scores
        hits = [
            SearchHit(
                chunk_id="chunk1", file_path="test.py", score=10.0, source="lexical", metadata={}
            ),
            SearchHit(
                chunk_id="chunk2", file_path="test.py", score=5.0, source="lexical", metadata={}
            ),
            SearchHit(
                chunk_id="chunk3", file_path="test.py", score=1.0, source="lexical", metadata={}
            ),
        ]

        normalized = normalizer.normalize_hits(hits, "lexical")

        # Check scores are in 0-1 range
        for hit in normalized:
            assert 0.0 <= hit.score <= 1.0

        # Check ordering is preserved (highest first)
        assert normalized[0].score > normalized[1].score > normalized[2].score

    def test_normalize_vector_scores(self):
        """Test vector score normalization."""
        from src.index.common.documents import SearchHit
        from src.retriever.fusion.normalizer import ScoreNormalizer

        normalizer = ScoreNormalizer()

        # Vector scores should already be 0-1 (cosine similarity)
        hits = [
            SearchHit(
                chunk_id="chunk1", file_path="test.py", score=0.95, source="vector", metadata={}
            ),
            SearchHit(
                chunk_id="chunk2", file_path="test.py", score=0.75, source="vector", metadata={}
            ),
        ]

        normalized = normalizer.normalize_hits(hits, "vector")

        # Scores should remain similar (already normalized)
        assert abs(normalized[0].score - 0.95) < 0.1
        assert abs(normalized[1].score - 0.75) < 0.1


class TestDeduplication:
    """Test chunk deduplication."""

    def test_dedup_overlapping_chunks(self):
        """Test deduplication of overlapping chunks."""
        from src.retriever.context_builder.dedup import Deduplicator
        from src.retriever.fusion.engine import FusedHit

        deduplicator = Deduplicator(overlap_threshold=0.5, drop_on_full_overlap=True)

        # Create overlapping chunks
        hits = [
            FusedHit(
                chunk_id="chunk1",
                file_path="test.py",
                symbol_id=None,
                fused_score=0.9,
                priority_score=0.9,
                metadata={"start_line": 10, "end_line": 20},
            ),
            FusedHit(
                chunk_id="chunk2",
                file_path="test.py",
                symbol_id=None,
                fused_score=0.8,
                priority_score=0.8,
                metadata={"start_line": 15, "end_line": 25},  # 50% overlap
            ),
            FusedHit(
                chunk_id="chunk3",
                file_path="test.py",
                symbol_id=None,
                fused_score=0.7,
                priority_score=0.7,
                metadata={"start_line": 12, "end_line": 18},  # Fully contained in chunk1
            ),
        ]

        deduplicated = deduplicator.deduplicate(hits)

        # chunk3 should be dropped (fully contained)
        chunk_ids = [hit.chunk_id for hit in deduplicated]
        assert "chunk1" in chunk_ids
        assert "chunk2" in chunk_ids  # Kept but penalized
        assert "chunk3" not in chunk_ids  # Dropped

        # chunk2 should have penalty applied
        chunk2 = next(h for h in deduplicated if h.chunk_id == "chunk2")
        assert chunk2.metadata.get("dedup_penalty") is not None


class TestChunkTrimming:
    """Test chunk trimming."""

    def test_trim_long_function(self):
        """Test trimming a long function to signature + docstring."""
        from src.retriever.context_builder.trimming import ChunkTrimmer

        trimmer = ChunkTrimmer(max_trimmed_tokens=200)

        content = '''def authenticate(username: str, password: str) -> bool:
    """
    Authenticate user with username and password.

    Args:
        username: User's username
        password: User's password

    Returns:
        True if authentication successful
    """
    # Validate inputs
    if not username or not password:
        return False

    # Hash password
    password_hash = hash_password(password)

    # Query database
    user = db.query(User).filter_by(username=username).first()

    # Check password
    if user and user.password_hash == password_hash:
        return True

    return False
'''

        trimmed_content, new_tokens, reason = trimmer.trim(content, 1000)

        # Should keep signature and docstring
        assert "def authenticate" in trimmed_content
        assert '"""' in trimmed_content
        assert "Authenticate user" in trimmed_content

        # Should be shorter
        assert new_tokens < 1000

        # Should have trimmed reason
        assert "trimmed" in reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
