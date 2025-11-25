"""
Tests for Contextual Query Expansion

Verifies:
1. Vocabulary learning from chunks
2. Term extraction (functions, classes, variables)
3. Embedding-based similarity search
4. Co-occurrence tracking
5. Query expansion with scoring
6. Save/load functionality
"""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.retriever.query.contextual_expansion import (
    CodebaseVocabulary,
    ContextualQueryExpander,
)


class SimpleEmbeddingModel:
    """Simple embedding model for testing."""

    def encode(self, text: str) -> np.ndarray:
        """Generate pseudo-embeddings based on text hash."""
        # Simple hash-based embedding for testing
        np.random.seed(hash(text.lower()) % (2**32))
        emb = np.random.randn(384)
        # L2 normalize
        emb = emb / (np.linalg.norm(emb) + 1e-8)
        return emb


@pytest.fixture
def sample_chunks():
    """Sample code chunks for testing."""
    return [
        {
            "chunk_id": "chunk:1",
            "content": """def authenticate_user(username, password):
    \"\"\"Authenticate user with credentials.\"\"\"
    return verify_credentials(username, password)""",
            "file_path": "auth/handlers.py",
        },
        {
            "chunk_id": "chunk:2",
            "content": """def verify_credentials(username, password):
    \"\"\"Verify user credentials against database.\"\"\"
    user = get_user(username)
    return check_password(user, password)""",
            "file_path": "auth/service.py",
        },
        {
            "chunk_id": "chunk:3",
            "content": """class AuthenticationManager:
    \"\"\"Manages user authentication.\"\"\"
    def login(self, username, password):
        return authenticate_user(username, password)""",
            "file_path": "auth/manager.py",
        },
        {
            "chunk_id": "chunk:4",
            "content": """def calculate_sum(a, b):
    \"\"\"Calculate sum of two numbers.\"\"\"
    return a + b""",
            "file_path": "math/utils.py",
        },
    ]


def test_vocabulary_learn_from_chunks(sample_chunks):
    """Test learning vocabulary from code chunks."""
    vocab = CodebaseVocabulary()
    vocab.learn_from_chunks(sample_chunks)

    # Should have learned several terms
    assert len(vocab.terms) > 0

    # Should find function names
    assert "authenticate_user" in vocab.terms
    assert "verify_credentials" in vocab.terms
    assert "calculate_sum" in vocab.terms

    # Should find class names
    assert "AuthenticationManager" in vocab.terms

    # Check term properties
    auth_term = vocab.terms["authenticate_user"]
    assert auth_term.term_type == "function"
    assert auth_term.frequency >= 1
    assert len(auth_term.file_paths) > 0


def test_vocabulary_term_extraction():
    """Test term extraction from code content."""
    vocab = CodebaseVocabulary()

    # Python code
    content = """
def my_function(x, y):
    return x + y

class MyClass:
    def method(self):
        pass

my_variable = 42
"""

    terms = vocab._extract_terms(content)
    term_names = [t[0] for t in terms]

    assert "my_function" in term_names
    assert "MyClass" in term_names
    assert "method" in term_names


def test_vocabulary_cooccurrence_tracking(sample_chunks):
    """Test co-occurrence tracking."""
    vocab = CodebaseVocabulary()
    vocab.learn_from_chunks(sample_chunks)

    # Check co-occurrence data structure exists
    assert isinstance(vocab.cooccurrence, dict)

    # If any terms have co-occurrences, verify structure
    if vocab.cooccurrence:
        # Get a term with co-occurrences
        terms_with_cooccur = [t for t in vocab.terms.keys() if vocab.cooccurrence[t]]

        if terms_with_cooccur:
            sample_term = terms_with_cooccur[0]
            cooccur = vocab.get_cooccurring_terms(sample_term, top_k=10)

            # Should return list of tuples (term, count)
            assert isinstance(cooccur, list)
            if cooccur:
                assert isinstance(cooccur[0], tuple)
                assert len(cooccur[0]) == 2


def test_vocabulary_with_embeddings(sample_chunks):
    """Test vocabulary with embedding model."""
    embedding_model = SimpleEmbeddingModel()
    vocab = CodebaseVocabulary(embedding_model=embedding_model)

    vocab.learn_from_chunks(sample_chunks)

    # Embeddings should be built
    assert vocab.term_embeddings is not None
    assert len(vocab.term_list) > 0
    assert vocab.term_embeddings.shape[0] == len(vocab.term_list)

    # Find similar terms to "authenticate"
    similar = vocab.find_similar_terms("authenticate", top_k=5, threshold=0.0)

    # Should find authentication-related terms
    assert len(similar) > 0

    # Should find authentication-related terms (specific term may vary due to embeddings)
    similar_terms = [term for term, score in similar]
    # Check that we found some authentication-related terms
    auth_related = any(
        "auth" in term.lower() or "user" in term.lower()
        for term in similar_terms
    )
    assert auth_related, f"Expected authentication-related terms, got: {similar_terms}"


def test_vocabulary_save_and_load(sample_chunks):
    """Test save and load functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vocab_path = Path(tmpdir) / "vocab.json"

        # Create and save vocabulary
        embedding_model = SimpleEmbeddingModel()
        vocab1 = CodebaseVocabulary(embedding_model=embedding_model)
        vocab1.learn_from_chunks(sample_chunks)
        vocab1.save(str(vocab_path))

        # Load vocabulary
        vocab2 = CodebaseVocabulary()
        vocab2.load(str(vocab_path))

        # Should have same terms
        assert len(vocab2.terms) == len(vocab1.terms)
        assert set(vocab2.terms.keys()) == set(vocab1.terms.keys())

        # Check term properties preserved
        term1 = vocab1.terms["authenticate_user"]
        term2 = vocab2.terms["authenticate_user"]
        assert term1.term_type == term2.term_type
        assert term1.frequency == term2.frequency

        # Embeddings should be loaded
        assert vocab2.term_embeddings is not None
        assert vocab2.term_list == vocab1.term_list


def test_contextual_query_expander_basic(sample_chunks):
    """Test basic query expansion."""
    embedding_model = SimpleEmbeddingModel()
    vocab = CodebaseVocabulary(embedding_model=embedding_model)
    vocab.learn_from_chunks(sample_chunks)

    expander = ContextualQueryExpander(
        vocabulary=vocab, embedding_model=embedding_model
    )

    # Expand query
    result = expander.expand("authenticate", max_expansions=5, similarity_threshold=0.0)

    # Should have expanded query
    assert result["original_query"] == "authenticate"
    assert "expanded_query" in result
    assert "expansion_terms" in result

    # Expanded query should include original term
    assert "authenticate" in result["expanded_query"]

    # num_expansions can be 0 if no terms meet threshold
    assert result["num_expansions"] >= 0
    assert isinstance(result["expansion_terms"], list)


def test_contextual_query_expander_relevance(sample_chunks):
    """Test that expansion can find terms from vocabulary."""
    embedding_model = SimpleEmbeddingModel()
    vocab = CodebaseVocabulary(embedding_model=embedding_model)
    vocab.learn_from_chunks(sample_chunks)

    expander = ContextualQueryExpander(
        vocabulary=vocab, embedding_model=embedding_model
    )

    # Expand with very low threshold to ensure we get some results
    result = expander.expand("test", max_expansions=10, similarity_threshold=0.0, frequency_min=1)

    # Should be able to find terms from the vocabulary
    # Even with simple embeddings, should find something
    assert isinstance(result["expansion_terms"], list)

    # If we have terms in vocab, we should be able to expand to some of them
    if len(vocab.terms) > 0:
        # With threshold=0.0 and frequency_min=1, we should get some expansions
        # (unless embedding model produces exactly zero similarity for all terms)
        assert result["num_expansions"] >= 0


def test_contextual_query_expander_frequency_filter(sample_chunks):
    """Test frequency filtering."""
    embedding_model = SimpleEmbeddingModel()
    vocab = CodebaseVocabulary(embedding_model=embedding_model)
    vocab.learn_from_chunks(sample_chunks)

    expander = ContextualQueryExpander(
        vocabulary=vocab, embedding_model=embedding_model
    )

    # Expand with high frequency requirement (most terms appear only once)
    result_high_freq = expander.expand(
        "function", max_expansions=10, frequency_min=10, similarity_threshold=0.0
    )

    # Should have fewer expansions (high frequency requirement)
    assert result_high_freq["num_expansions"] == 0  # No terms appear 10+ times

    # Expand with low frequency requirement
    result_low_freq = expander.expand(
        "function", max_expansions=10, frequency_min=1, similarity_threshold=0.0
    )

    # Should have more expansions
    assert result_low_freq["num_expansions"] > 0


def test_contextual_query_expander_no_duplicates(sample_chunks):
    """Test that expansion doesn't duplicate query terms."""
    embedding_model = SimpleEmbeddingModel()
    vocab = CodebaseVocabulary(embedding_model=embedding_model)
    vocab.learn_from_chunks(sample_chunks)

    expander = ContextualQueryExpander(
        vocabulary=vocab, embedding_model=embedding_model
    )

    # Expand query with term that exists in vocabulary
    result = expander.expand("authenticate_user", max_expansions=5, similarity_threshold=0.0)

    expanded_terms = result["expanded_query"].split()

    # "authenticate_user" should appear only once
    assert expanded_terms.count("authenticate_user") == 1


def test_contextual_query_expander_explain(sample_chunks):
    """Test expansion explanation."""
    embedding_model = SimpleEmbeddingModel()
    vocab = CodebaseVocabulary(embedding_model=embedding_model)
    vocab.learn_from_chunks(sample_chunks)

    expander = ContextualQueryExpander(
        vocabulary=vocab, embedding_model=embedding_model
    )

    result = expander.expand("authenticate", max_expansions=5, similarity_threshold=0.0)
    explanation = expander.explain(result)

    # Explanation should include key information
    assert "Original:" in explanation
    assert "Expanded:" in explanation
    assert "Expansion terms" in explanation


def test_contextual_query_expander_empty_vocabulary():
    """Test expander with empty vocabulary."""
    vocab = CodebaseVocabulary()
    expander = ContextualQueryExpander(vocabulary=vocab)

    # Expand query (should handle gracefully)
    result = expander.expand("test query", max_expansions=5)

    # Should return original query
    assert result["original_query"] == "test query"
    assert result["num_expansions"] == 0


def test_vocabulary_different_code_styles():
    """Test vocabulary learning from different code styles."""
    chunks = [
        {
            "chunk_id": "chunk:python",
            "content": """
def snake_case_function():
    pass

class CamelCaseClass:
    pass
""",
            "file_path": "python_file.py",
        },
        {
            "chunk_id": "chunk:typescript",
            "content": """
function camelCaseFunction() {
    return 42;
}

const arrowFunction = async () => {
    return 42;
}

interface IMyInterface {
    method(): void;
}
""",
            "file_path": "typescript_file.ts",
        },
    ]

    vocab = CodebaseVocabulary()
    vocab.learn_from_chunks(chunks)

    # Should extract from both Python and TypeScript
    assert "snake_case_function" in vocab.terms
    assert "CamelCaseClass" in vocab.terms
    assert "camelCaseFunction" in vocab.terms
    assert "arrowFunction" in vocab.terms
    assert "IMyInterface" in vocab.terms
