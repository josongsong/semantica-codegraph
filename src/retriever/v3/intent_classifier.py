"""
Multi-label Intent Classifier for v3.

Classifies queries into soft multi-label intent probabilities (RFC section 3).
"""

import math
import re

from .models import IntentProbability


class IntentClassifierV3:
    """
    Multi-label intent classifier using rule-based softmax.

    Outputs probability distribution over intent types instead of single intent.
    """

    # Pattern weights for different intents
    SYMBOL_PATTERNS = [
        (r"\b(class|function|method|def)\s+\w+", 0.4),
        (r"\b(find|locate|show)\s+\w+", 0.3),
        (r"^[\w.]+$", 0.5),  # Single identifier
        (r"::", 0.4),  # C++/Rust style
        (r"\w+\.\w+", 0.3),  # Dotted notation
        (r"[A-Z][a-z]+(?:[A-Z][a-z]+)+", 0.3),  # CamelCase
        (r"\w+_\w+", 0.2),  # snake_case
        # P0 Enhancement: Type/enum keywords
        (r"\b(enum|interface|type|protocol|struct)\s+\w+", 0.4),
        (r"\b(enum|interface|type)\b", 0.3),
    ]

    FLOW_PATTERNS = [
        (r"\b(call|trace|flow)\b", 0.5),
        (r"\bwho\s+calls?\b", 0.6),  # P0: Increased from 0.5
        (r"\bwhere\s+used\b", 0.4),
        (r"\bcall\s+(chain|graph|path)\b", 0.5),
        (r"\bexecution\s+flow\b", 0.5),
        (r"\bdata\s+flow\b", 0.4),
        (r"\bfrom\s+\w+\s+to\s+\w+", 0.5),
        # P0 Enhancement: More caller/dependency patterns
        (r"\bcalls?\s+\w+", 0.4),
        (r"\bused\s+by\b", 0.4),
        (r"\bdepends?\s+on\b", 0.4),
    ]

    CONCEPT_PATTERNS = [
        (r"\bhow\s+(does|do|is)\b", 0.5),
        (r"\bwhat\s+(is|are)\b", 0.5),
        (r"\bexplain\b", 0.6),
        (r"\barchitecture\b", 0.5),
        (r"\bdesign\b", 0.4),
        (r"\bconcept\b", 0.5),
        (r"\bpattern\b", 0.3),
        (r"\bworks?\b", 0.3),
    ]

    CODE_PATTERNS = [
        (r"\bexample\b", 0.5),
        (r"\bimplement(ation)?\b", 0.5),
        (r"\bcode\s+(for|that)\b", 0.5),
        (r"\bloop\b", 0.3),
        (r"\bconditional\b", 0.3),
        (r"\balgorithm\b", 0.4),
        (r"\blogic\b", 0.3),
    ]

    def __init__(self):
        """Initialize classifier with compiled patterns."""
        self._symbol_re = [(re.compile(p, re.IGNORECASE), w) for p, w in self.SYMBOL_PATTERNS]
        self._flow_re = [(re.compile(p, re.IGNORECASE), w) for p, w in self.FLOW_PATTERNS]
        self._concept_re = [(re.compile(p, re.IGNORECASE), w) for p, w in self.CONCEPT_PATTERNS]
        self._code_re = [(re.compile(p, re.IGNORECASE), w) for p, w in self.CODE_PATTERNS]

    def classify(self, query: str) -> IntentProbability:
        """
        Classify query into multi-label intent probabilities.

        Args:
            query: User query string

        Returns:
            IntentProbability with softmax-normalized probabilities
        """
        # Calculate raw scores for each intent
        raw_scores = {
            "symbol": self._score_patterns(query, self._symbol_re),
            "flow": self._score_patterns(query, self._flow_re),
            "concept": self._score_patterns(query, self._concept_re),
            "code": self._score_patterns(query, self._code_re),
            "balanced": 0.3,  # Baseline
        }

        # Apply query-level heuristics
        self._apply_heuristics(query, raw_scores)

        # Softmax normalization
        probabilities = self._softmax(raw_scores)

        return IntentProbability(
            symbol=probabilities["symbol"],
            flow=probabilities["flow"],
            concept=probabilities["concept"],
            code=probabilities["code"],
            balanced=probabilities["balanced"],
        )

    def _score_patterns(self, query: str, patterns: list[tuple]) -> float:
        """
        Score query against a list of weighted patterns.

        Args:
            query: Query string
            patterns: List of (compiled_pattern, weight) tuples

        Returns:
            Accumulated score (0-1)
        """
        score = 0.0
        for pattern, weight in patterns:
            if pattern.search(query):
                score += weight

        return min(score, 1.0)

    def _apply_heuristics(self, query: str, scores: dict[str, float]):
        """
        Apply query-level heuristics to adjust scores.

        Modifies scores dict in-place.

        Args:
            query: Query string
            scores: Dict of intent → score
        """
        query_lower = query.lower().strip()
        words = query_lower.split()

        # Very short query with single identifier → symbol
        if len(words) <= 2 and re.match(r"^[\w.]+$", query):
            scores["symbol"] += 0.5

        # Question words → concept
        question_words = ["how", "what", "why", "when", "where"]
        if any(word in words for word in question_words):
            scores["concept"] += 0.3

        # Multiple verbs → code search
        verb_count = sum(
            1 for word in words if word in ["get", "set", "create", "delete", "update", "find"]
        )
        if verb_count >= 2:
            scores["code"] += 0.3

        # File paths → code search
        if re.search(r"\.(py|ts|js|go|java|rs)\b", query):
            scores["code"] += 0.4

        # Long natural language query → concept
        if len(words) > 8:
            scores["concept"] += 0.3

        # "from X to Y" pattern → flow
        if re.search(r"\bfrom\s+\w+\s+to\s+\w+", query_lower):
            scores["flow"] += 0.5

    def _softmax(self, scores: dict[str, float], temperature: float = 1.0) -> dict[str, float]:
        """
        Apply softmax normalization to scores.

        Args:
            scores: Dict of intent → score
            temperature: Softmax temperature (higher = more uniform)

        Returns:
            Dict of intent → probability (sum = 1.0)
        """
        # Apply temperature scaling
        scaled = {k: v / temperature for k, v in scores.items()}

        # Compute exp
        exp_scores = {k: math.exp(v) for k, v in scaled.items()}

        # Normalize
        total = sum(exp_scores.values())
        probabilities = {k: v / total for k, v in exp_scores.items()}

        return probabilities

    def classify_with_expansion(self, query: str) -> tuple[IntentProbability, dict[str, list[str]]]:
        """
        Classify query and extract potential query expansions.

        Args:
            query: User query string

        Returns:
            Tuple of (IntentProbability, expansion_dict)
            expansion_dict contains:
                - symbols: Extracted symbol names
                - file_paths: Extracted file paths
                - modules: Extracted module paths
        """
        intent_prob = self.classify(query)

        expansions = {
            "symbols": self._extract_symbols(query),
            "file_paths": self._extract_file_paths(query),
            "modules": self._extract_modules(query),
        }

        return intent_prob, expansions

    def _extract_symbols(self, query: str) -> list[str]:
        """Extract potential symbol names from query."""
        symbols = []

        # CamelCase
        camel_case = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", query)
        symbols.extend(camel_case)

        # snake_case
        snake_case = re.findall(r"\b[a-z_]+[a-z]\b", query)
        common_words = {
            "the",
            "and",
            "for",
            "from",
            "with",
            "how",
            "what",
            "why",
            "when",
            "where",
        }
        symbols.extend([s for s in snake_case if s not in common_words and len(s) > 2])

        return list(set(symbols))[:5]

    def _extract_file_paths(self, query: str) -> list[str]:
        """Extract file paths from query."""
        # Match full file paths with extensions (capture entire path, not just extension)
        paths = re.findall(r"([\w/]+\.(?:py|ts|js|go|java|rs|cpp|c|h))\b", query)
        return list(set(paths))[:3]

    def _extract_modules(self, query: str) -> list[str]:
        """Extract module/package paths from query."""
        modules = re.findall(r"\b[a-z_]+(?:\.[a-z_]+)+\b", query)
        return list(set(modules))[:3]
