"""
Contextual Query Expansion

Expands user queries with repository-specific terminology.

Strategy:
1. Learn vocabulary from actual codebase (function names, class names, etc.)
2. Build embedding index of codebase terms
3. Find similar terms when user queries
4. Weight by term frequency and co-occurrence

Expected improvement: Precision +5-10%

Example:
- User: "authentication function"
- Expanded: ["authentication", "authenticate", "auth", "verify_user", "check_credentials"]
  (actual function names from the codebase)
"""

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from src.common.observability import get_logger

logger = get_logger(__name__)


@dataclass
class CodebaseTerm:
    """Term from codebase vocabulary."""

    term: str
    term_type: str  # function, class, variable, module
    frequency: int
    file_paths: list[str]
    embedding: np.ndarray | None = None


class CodebaseVocabulary:
    """
    Vocabulary learned from actual codebase.

    Learns:
    - Function names
    - Class names
    - Variable names
    - Module names
    - Common patterns
    """

    def __init__(self, embedding_model: Any = None):
        """
        Initialize codebase vocabulary.

        Args:
            embedding_model: Embedding model for similarity search
        """
        self.embedding_model = embedding_model
        self.terms: dict[str, CodebaseTerm] = {}
        self.term_embeddings: np.ndarray | None = None
        self.term_list: list[str] = []

        # Co-occurrence matrix (for context-aware expansion)
        self.cooccurrence: dict[str, Counter] = defaultdict(Counter)

    def learn_from_chunks(self, chunks: list[dict[str, Any]]) -> None:
        """
        Learn vocabulary from code chunks.

        Args:
            chunks: List of code chunks
        """
        logger.info(f"Learning vocabulary from {len(chunks)} chunks...")

        for chunk in chunks:
            content = chunk.get("content", "")
            file_path = chunk.get("file_path", "")

            # Extract terms
            terms = self._extract_terms(content)

            # Update vocabulary
            for term, term_type in terms:
                if term not in self.terms:
                    self.terms[term] = CodebaseTerm(
                        term=term,
                        term_type=term_type,
                        frequency=0,
                        file_paths=[],
                    )

                codebase_term = self.terms[term]
                codebase_term.frequency += 1

                if file_path not in codebase_term.file_paths:
                    codebase_term.file_paths.append(file_path)

            # Update co-occurrence
            for i, (term1, _) in enumerate(terms):
                for term2, _ in terms[i + 1 : i + 10]:  # Window of 10
                    self.cooccurrence[term1][term2] += 1
                    self.cooccurrence[term2][term1] += 1

        logger.info(f"Learned {len(self.terms)} unique terms")

        # Build embeddings
        if self.embedding_model:
            self._build_embeddings()

    def _extract_terms(self, content: str) -> list[tuple[str, str]]:
        """
        Extract terms from code content.

        Args:
            content: Code content

        Returns:
            List of (term, term_type) tuples
        """
        import re

        terms = []

        # Function definitions
        # Python: def function_name(
        func_defs = re.findall(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", content)
        terms.extend((name, "function") for name in func_defs)

        # TypeScript: function name( or const name = (
        ts_funcs = re.findall(
            r"(?:function\s+([a-zA-Z_][a-zA-Z0-9_]*)|const\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:async\s*)?\()",
            content,
        )
        terms.extend((name[0] or name[1], "function") for name in ts_funcs if name[0] or name[1])

        # Class definitions
        # Python: class ClassName
        class_defs = re.findall(r"class\s+([A-Z][a-zA-Z0-9_]*)", content)
        terms.extend((name, "class") for name in class_defs)

        # TypeScript: class ClassName or interface ClassName
        ts_classes = re.findall(r"(?:class|interface)\s+([A-Z][a-zA-Z0-9_]*)", content)
        terms.extend((name, "class") for name in ts_classes)

        # Variables (less reliable, limit to assignments)
        # Python: variable_name =
        var_assigns = re.findall(r"^\s*([a-z_][a-z0-9_]*)\s*=\s*", content, re.MULTILINE)
        terms.extend((name, "variable") for name in var_assigns[:20])  # Limit

        return terms

    def _build_embeddings(self) -> None:
        """Build embeddings for all terms."""
        if not self.embedding_model:
            return

        logger.info(f"Building embeddings for {len(self.terms)} terms...")

        self.term_list = list(self.terms.keys())
        embeddings = []

        for term in self.term_list:
            # Encode term
            try:
                emb = self.embedding_model.encode(term)
                embeddings.append(emb)
            except Exception as e:
                logger.warning(f"Failed to encode term '{term}': {e}")
                embeddings.append(np.zeros(384))  # Default dim

        self.term_embeddings = np.array(embeddings)
        logger.info(f"Built embeddings: shape={self.term_embeddings.shape}")

    def find_similar_terms(self, query: str, top_k: int = 10, threshold: float = 0.6) -> list[tuple[str, float]]:
        """
        Find similar terms from vocabulary.

        Args:
            query: User query
            top_k: Number of similar terms
            threshold: Similarity threshold (0-1)

        Returns:
            List of (term, similarity) tuples
        """
        if not self.embedding_model or self.term_embeddings is None:
            return []

        # Encode query
        try:
            query_emb = self.embedding_model.encode(query)
        except Exception as e:
            logger.warning(f"Failed to encode query: {e}")
            return []

        # Compute similarities
        query_emb = query_emb / (np.linalg.norm(query_emb) + 1e-8)
        term_embs_norm = self.term_embeddings / (np.linalg.norm(self.term_embeddings, axis=1, keepdims=True) + 1e-8)

        similarities = np.dot(term_embs_norm, query_emb)

        # Get top-k
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            similarity = float(similarities[idx])
            if similarity >= threshold:
                term = self.term_list[idx]
                results.append((term, similarity))

        return results

    def get_cooccurring_terms(self, term: str, top_k: int = 5) -> list[tuple[str, int]]:
        """
        Get terms that frequently co-occur with given term.

        Args:
            term: Input term
            top_k: Number of co-occurring terms

        Returns:
            List of (term, count) tuples
        """
        if term not in self.cooccurrence:
            return []

        cooccur = self.cooccurrence[term]
        return cooccur.most_common(top_k)

    def save(self, path: str) -> None:
        """Save vocabulary to disk."""
        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)

        # Save terms (without embeddings)
        terms_data = {
            term: {
                "term_type": ct.term_type,
                "frequency": ct.frequency,
                "file_paths": ct.file_paths,
            }
            for term, ct in self.terms.items()
        }

        with open(path, "w") as f:
            json.dump(
                {
                    "terms": terms_data,
                    "cooccurrence": {k: dict(v) for k, v in self.cooccurrence.items()},
                },
                f,
            )

        # Save embeddings separately
        if self.term_embeddings is not None:
            emb_path = Path(path).with_suffix(".emb.npy")
            np.save(emb_path, self.term_embeddings)

            # Save term list
            term_list_path = Path(path).with_suffix(".terms.json")
            with open(term_list_path, "w") as f:
                json.dump(self.term_list, f)

        logger.info(f"Vocabulary saved to {path}")

    def load(self, path: str) -> None:
        """Load vocabulary from disk."""
        with open(path) as f:
            data = json.load(f)

        # Load terms
        self.terms = {}
        for term, term_data in data["terms"].items():
            self.terms[term] = CodebaseTerm(
                term=term,
                term_type=term_data["term_type"],
                frequency=term_data["frequency"],
                file_paths=term_data["file_paths"],
            )

        # Load co-occurrence
        self.cooccurrence = defaultdict(Counter)
        for term, cooccur in data["cooccurrence"].items():
            self.cooccurrence[term] = Counter(cooccur)

        # Load embeddings
        emb_path = Path(path).with_suffix(".emb.npy")
        if emb_path.exists():
            self.term_embeddings = np.load(emb_path)

            # Load term list
            term_list_path = Path(path).with_suffix(".terms.json")
            with open(term_list_path) as f:
                self.term_list = json.load(f)

        logger.info(f"Vocabulary loaded from {path}")


class ContextualQueryExpander:
    """
    Expands queries with repository-specific terms.

    Two-stage expansion:
    1. Embedding similarity: Find semantically similar terms
    2. Co-occurrence boost: Boost terms that co-occur with query terms
    """

    def __init__(
        self,
        vocabulary: CodebaseVocabulary | None = None,
        embedding_model: Any = None,
    ):
        """
        Initialize contextual query expander.

        Args:
            vocabulary: Codebase vocabulary (if None, will create empty)
            embedding_model: Embedding model
        """
        self.vocabulary = vocabulary or CodebaseVocabulary(embedding_model)
        self.embedding_model = embedding_model

    def expand(
        self,
        query: str,
        max_expansions: int = 10,
        similarity_threshold: float = 0.6,
        frequency_min: int = 2,
    ) -> dict[str, Any]:
        """
        Expand query with codebase-specific terms.

        Args:
            query: User query
            max_expansions: Max number of expansion terms
            similarity_threshold: Similarity threshold for semantic matching
            frequency_min: Minimum frequency for term to be included

        Returns:
            Expansion result with terms and scores
        """
        # Find similar terms via embeddings
        similar_terms = self.vocabulary.find_similar_terms(
            query, top_k=max_expansions * 2, threshold=similarity_threshold
        )

        # Filter by frequency
        similar_terms = [
            (term, sim) for term, sim in similar_terms if self.vocabulary.terms[term].frequency >= frequency_min
        ]

        # Get co-occurring terms for each similar term
        cooccur_boost = Counter()
        for term, sim in similar_terms[:5]:  # Top 5
            cooccur = self.vocabulary.get_cooccurring_terms(term, top_k=5)
            for cooccur_term, count in cooccur:
                cooccur_boost[cooccur_term] += count * sim  # Weight by similarity

        # Combine similarity and co-occurrence
        final_scores = {}

        for term, sim in similar_terms:
            # Base score from similarity
            score = sim

            # Boost from co-occurrence
            if term in cooccur_boost:
                cooccur_score = cooccur_boost[term] / max(cooccur_boost.values())
                score = 0.7 * sim + 0.3 * cooccur_score

            final_scores[term] = score

        # Sort by final score
        ranked_terms = sorted(final_scores.items(), key=lambda x: x[1], reverse=True)[:max_expansions]

        # Build expanded query
        original_terms = query.lower().split()
        expansion_terms = [term for term, _ in ranked_terms]

        # Combine (avoid duplicates)
        combined = original_terms + [
            t for t in expansion_terms if t.lower() not in {ot.lower() for ot in original_terms}
        ]

        expanded_query = " ".join(combined)

        return {
            "original_query": query,
            "expanded_query": expanded_query,
            "expansion_terms": ranked_terms,
            "num_expansions": len(ranked_terms),
        }

    def explain(self, expansion_result: dict[str, Any]) -> str:
        """
        Generate explanation of expansion.

        Args:
            expansion_result: Result from expand()

        Returns:
            Human-readable explanation
        """
        lines = ["Contextual Query Expansion:"]
        lines.append(f"Original: {expansion_result['original_query']}")
        lines.append(f"Expanded: {expansion_result['expanded_query']}")
        lines.append(f"\nExpansion terms ({expansion_result['num_expansions']}):")

        for term, score in expansion_result["expansion_terms"][:5]:
            term_info = self.vocabulary.terms[term]
            lines.append(f"  - {term} (score: {score:.3f}, freq: {term_info.frequency}, type: {term_info.term_type})")

        return "\n".join(lines)
