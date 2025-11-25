"""
ML Intent Classifier

Lightweight ML-based intent classifier as an alternative to LLM classification.
Implements Phase 2 Action 12-1 from the retrieval execution plan.

Uses a small, fast model (e.g., MiniLM, FastText) for intent classification
with much lower latency than LLM calls.
"""

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from src.retriever.intent.models import IntentKind, QueryIntent

logger = logging.getLogger(__name__)


@dataclass
class MLIntentFeatures:
    """Features extracted from query for ML classification."""

    # Token-based features
    has_camelcase: bool
    has_snake_case: bool
    has_path: bool
    has_code_keywords: bool

    # Length features
    query_length: int
    word_count: int
    avg_word_length: float

    # Syntactic features
    has_quotes: bool
    has_punctuation: bool
    question_words: int

    # Semantic features (if embedding available)
    embedding: np.ndarray | None = None


class MLIntentClassifier:
    """
    Lightweight ML-based intent classifier.

    Much faster than LLM classification (~10-50ms vs 500-1500ms).
    Can be trained on user interaction data for continuous improvement.
    """

    def __init__(
        self,
        model_path: str | None = None,
        embedding_model_name: str = "all-MiniLM-L6-v2",
    ):
        """
        Initialize ML intent classifier.

        Args:
            model_path: Path to trained model (optional)
            embedding_model_name: Name of sentence embedding model
        """
        self.model_path = model_path
        self.embedding_model_name = embedding_model_name
        self.model = None
        self.embedding_model = None

        # Load model if path provided
        if model_path and Path(model_path).exists():
            self.load_model(model_path)

        # Initialize embedding model (lazy load)
        self._embedding_available = False

    def classify(self, query: str) -> QueryIntent:
        """
        Classify query intent using ML model.

        Args:
            query: User query

        Returns:
            QueryIntent with classification
        """
        # Extract features
        features = self._extract_features(query)

        # If model is loaded, use it
        if self.model is not None:
            intent_kind, confidence = self._predict_with_model(features)
        else:
            # Fallback to heuristic-based classification
            intent_kind, confidence = self._heuristic_classify(query)

        # Extract metadata
        symbol_names = self._extract_symbols(query)
        file_paths = self._extract_paths(query)
        module_paths = self._extract_modules(query)

        return QueryIntent(
            kind=intent_kind,
            confidence=confidence,
            symbol_names=symbol_names,
            file_paths=file_paths,
            module_paths=module_paths,
            is_nl=(not features.has_code_keywords),
            has_symbol=features.has_camelcase or features.has_snake_case,
            has_path_hint=features.has_path,
        )

    def _extract_features(self, query: str) -> MLIntentFeatures:
        """
        Extract features from query.

        Args:
            query: User query

        Returns:
            Extracted features
        """
        import re

        tokens = query.split()

        # Token-based features
        has_camelcase = bool(re.search(r"[a-z][A-Z]", query))
        has_snake_case = bool(re.search(r"[a-z_][a-z_]+[a-z]", query))
        has_path = bool(
            re.search(r"[./\\]", query) or any(".py" in t or ".ts" in t for t in tokens)
        )
        code_keywords = {"class", "def", "function", "method", "import", "from"}
        has_code_keywords = any(kw in query.lower() for kw in code_keywords)

        # Length features
        query_length = len(query)
        word_count = len(tokens)
        avg_word_length = sum(len(t) for t in tokens) / max(word_count, 1)

        # Syntactic features
        has_quotes = '"' in query or "'" in query
        has_punctuation = bool(re.search(r"[?!.,;:]", query))
        question_words = sum(
            1
            for qw in ["what", "where", "when", "how", "why", "which", "who"]
            if qw in query.lower()
        )

        # Embedding (if model available)
        embedding = self._get_embedding(query) if self._embedding_available else None

        return MLIntentFeatures(
            has_camelcase=has_camelcase,
            has_snake_case=has_snake_case,
            has_path=has_path,
            has_code_keywords=has_code_keywords,
            query_length=query_length,
            word_count=word_count,
            avg_word_length=avg_word_length,
            has_quotes=has_quotes,
            has_punctuation=has_punctuation,
            question_words=question_words,
            embedding=embedding,
        )

    def _predict_with_model(
        self, features: MLIntentFeatures
    ) -> tuple[IntentKind, float]:
        """
        Predict intent using trained ML model.

        Args:
            features: Extracted features

        Returns:
            (intent_kind, confidence)
        """
        # Convert features to numpy array
        feature_vector = self._featurize(features)

        # Predict
        try:
            proba = self.model.predict_proba([feature_vector])[0]
            predicted_class = np.argmax(proba)
            confidence = float(proba[predicted_class])

            # Map class index to IntentKind
            intent_kind = self._index_to_intent(predicted_class)

            return intent_kind, confidence
        except Exception as e:
            logger.warning(f"ML prediction failed: {e}, falling back to heuristic")
            return self._heuristic_classify("")

    def _heuristic_classify(self, query: str) -> tuple[IntentKind, float]:
        """
        Heuristic-based classification (fallback).

        Args:
            query: User query

        Returns:
            (intent_kind, confidence)
        """
        query_lower = query.lower()

        # Symbol navigation patterns
        if any(
            pattern in query_lower
            for pattern in [
                "definition",
                "where is",
                "find class",
                "find function",
                "go to",
            ]
        ):
            return IntentKind.SYMBOL_NAV, 0.7

        # Flow trace patterns
        if any(
            pattern in query_lower
            for pattern in [
                "call",
                "flow",
                "trace",
                "from",
                "to",
                "invokes",
                "executes",
            ]
        ):
            return IntentKind.FLOW_TRACE, 0.7

        # Repo overview patterns
        if any(
            pattern in query_lower
            for pattern in [
                "structure",
                "overview",
                "architecture",
                "entry",
                "main",
            ]
        ):
            return IntentKind.REPO_OVERVIEW, 0.7

        # Concept search (high-level, natural language)
        if len(query.split()) > 5 and not any(
            c in query for c in ["(", ")", "{", "}", "[", "]"]
        ):
            return IntentKind.CONCEPT_SEARCH, 0.6

        # Default: code search
        return IntentKind.CODE_SEARCH, 0.5

    def _featurize(self, features: MLIntentFeatures) -> np.ndarray:
        """
        Convert features to numpy array.

        Args:
            features: Extracted features

        Returns:
            Feature vector
        """
        vec = [
            float(features.has_camelcase),
            float(features.has_snake_case),
            float(features.has_path),
            float(features.has_code_keywords),
            features.query_length / 100.0,  # Normalize
            features.word_count / 20.0,  # Normalize
            features.avg_word_length / 10.0,  # Normalize
            float(features.has_quotes),
            float(features.has_punctuation),
            features.question_words / 3.0,  # Normalize
        ]

        # Add embedding if available
        if features.embedding is not None:
            vec.extend(features.embedding.tolist())

        return np.array(vec)

    def _index_to_intent(self, index: int) -> IntentKind:
        """Map class index to IntentKind."""
        mapping = {
            0: IntentKind.CODE_SEARCH,
            1: IntentKind.SYMBOL_NAV,
            2: IntentKind.CONCEPT_SEARCH,
            3: IntentKind.FLOW_TRACE,
            4: IntentKind.REPO_OVERVIEW,
        }
        return mapping.get(index, IntentKind.CODE_SEARCH)

    def _get_embedding(self, query: str) -> np.ndarray | None:
        """
        Get query embedding.

        Args:
            query: User query

        Returns:
            Embedding vector or None
        """
        if not self._embedding_available:
            try:
                from sentence_transformers import SentenceTransformer

                self.embedding_model = SentenceTransformer(self.embedding_model_name)
                self._embedding_available = True
            except ImportError:
                logger.warning(
                    "sentence-transformers not available, embeddings disabled"
                )
                return None

        try:
            return self.embedding_model.encode(query)
        except Exception as e:
            logger.warning(f"Embedding generation failed: {e}")
            return None

    def _extract_symbols(self, query: str) -> list[str]:
        """Extract symbol names from query."""
        import re

        # CamelCase
        camel = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", query)
        # snake_case
        snake = re.findall(r"\b[a-z_]+[a-z]\b", query)
        return list(set(camel + snake))

    def _extract_paths(self, query: str) -> list[str]:
        """Extract file paths from query."""
        import re

        # Simple path extraction
        paths = re.findall(r"[\w/\\.-]+\.(py|ts|js|go|java|cpp|c|h)", query)
        return paths

    def _extract_modules(self, query: str) -> list[str]:
        """Extract module paths from query."""
        import re

        # Dotted module names
        modules = re.findall(r"\b[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)+\b", query)
        return modules

    def load_model(self, model_path: str) -> None:
        """
        Load trained model from disk.

        Args:
            model_path: Path to model file
        """
        try:
            with open(model_path, "rb") as f:
                self.model = pickle.load(f)
            logger.info(f"Loaded ML intent model from {model_path}")
        except Exception as e:
            logger.error(f"Failed to load model from {model_path}: {e}")
            self.model = None

    def save_model(self, model_path: str) -> None:
        """
        Save trained model to disk.

        Args:
            model_path: Path to save model
        """
        if self.model is None:
            raise ValueError("No model to save")

        with open(model_path, "wb") as f:
            pickle.dump(self.model, f)
        logger.info(f"Saved ML intent model to {model_path}")

    def train(
        self,
        training_data: list[tuple[str, IntentKind]],
        model_type: str = "logistic_regression",
    ) -> dict[str, Any]:
        """
        Train ML model on labeled data.

        Args:
            training_data: List of (query, intent_kind) pairs
            model_type: Type of model to train

        Returns:
            Training metrics
        """
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, classification_report
        from sklearn.model_selection import train_test_split

        # Extract features and labels
        X = []
        y = []
        for query, intent_kind in training_data:
            features = self._extract_features(query)
            X.append(self._featurize(features))
            y.append(self._intent_to_index(intent_kind))

        X = np.array(X)
        y = np.array(y)

        # Split train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        # Train model
        if model_type == "logistic_regression":
            self.model = LogisticRegression(max_iter=1000, random_state=42)
        else:
            raise ValueError(f"Unknown model type: {model_type}")

        self.model.fit(X_train, y_train)

        # Evaluate
        y_pred = self.model.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        report = classification_report(y_test, y_pred)

        logger.info(f"Model trained with accuracy: {accuracy:.3f}")
        logger.info(f"Classification report:\n{report}")

        return {
            "accuracy": accuracy,
            "report": report,
            "train_size": len(X_train),
            "test_size": len(X_test),
        }

    def _intent_to_index(self, intent: IntentKind) -> int:
        """Map IntentKind to class index."""
        mapping = {
            IntentKind.CODE_SEARCH: 0,
            IntentKind.SYMBOL_NAV: 1,
            IntentKind.CONCEPT_SEARCH: 2,
            IntentKind.FLOW_TRACE: 3,
            IntentKind.REPO_OVERVIEW: 4,
        }
        return mapping[intent]
