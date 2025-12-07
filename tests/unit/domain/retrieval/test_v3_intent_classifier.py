"""
Tests for Intent Classifier V3.
"""

import pytest
from src.retriever.v3.intent_classifier import IntentClassifierV3
from src.retriever.v3.models import IntentProbability


class TestIntentClassifierV3:
    """Test intent classifier v3."""

    @pytest.fixture
    def classifier(self):
        """Create classifier instance."""
        return IntentClassifierV3()

    def test_symbol_query(self, classifier):
        """Test symbol navigation intent."""
        query = "find function authenticate"
        intent = classifier.classify(query)

        assert isinstance(intent, IntentProbability)
        # Symbol should be high
        assert intent.symbol > 0.2
        # Probabilities should sum to ~1.0
        total = intent.symbol + intent.flow + intent.concept + intent.code + intent.balanced
        assert 0.99 <= total <= 1.01

    def test_flow_query(self, classifier):
        """Test flow trace intent."""
        query = "trace call chain from login to database"
        intent = classifier.classify(query)

        assert intent.flow > 0.3

    def test_concept_query(self, classifier):
        """Test concept search intent."""
        query = "how does the authentication system work?"
        intent = classifier.classify(query)

        assert intent.concept > 0.3

    def test_code_query(self, classifier):
        """Test code search intent."""
        query = "show me example implementation of login"
        intent = classifier.classify(query)

        assert intent.code > 0.2

    def test_balanced_query(self, classifier):
        """Test balanced intent."""
        query = "search for user management"
        intent = classifier.classify(query)

        # Should have reasonable distribution
        assert 0.1 <= intent.balanced <= 0.5

    def test_short_identifier(self, classifier):
        """Test short identifier query."""
        query = "authenticate"
        intent = classifier.classify(query)

        # Should strongly favor symbol
        assert intent.symbol > 0.4

    def test_dotted_notation(self, classifier):
        """Test dotted notation query."""
        query = "utils.auth.verify"
        intent = classifier.classify(query)

        # Should favor symbol
        assert intent.symbol > 0.3

    def test_dominant_intent(self, classifier):
        """Test dominant intent extraction."""
        query = "how does authentication work"
        intent = classifier.classify(query)

        dominant = intent.dominant_intent()
        assert dominant in ["symbol", "flow", "concept", "code", "balanced"]

    def test_query_expansion(self, classifier):
        """Test query expansion extraction."""
        query = "find AuthManager class in auth.py"
        intent, expansions = classifier.classify_with_expansion(query)

        # Should extract symbols
        assert "AuthManager" in expansions["symbols"] or len(expansions["symbols"]) > 0

        # Should extract file paths
        assert "auth.py" in expansions["file_paths"]

    def test_mixed_query(self, classifier):
        """Test query with mixed signals."""
        query = "explain how the LoginHandler class works"
        intent = classifier.classify(query)

        # Should have both concept and symbol signals
        assert intent.concept > 0.1
        assert intent.symbol > 0.1

    def test_probability_normalization(self, classifier):
        """Test that probabilities always sum to 1."""
        queries = [
            "authenticate",
            "how does auth work",
            "trace call flow",
            "example implementation",
            "search user module",
        ]

        for query in queries:
            intent = classifier.classify(query)
            total = intent.symbol + intent.flow + intent.concept + intent.code + intent.balanced
            assert 0.99 <= total <= 1.01, f"Query '{query}' has invalid sum: {total}"
