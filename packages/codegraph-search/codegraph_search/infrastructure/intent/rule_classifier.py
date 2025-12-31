"""
Rule-based Intent Classifier

Fallback classifier when LLM-based classification fails or times out.
Uses heuristic patterns to determine query intent.
"""

import re

from codegraph_search.infrastructure.intent.models import IntentKind, QueryIntent


class RuleBasedClassifier:
    """
    Rule-based intent classifier using pattern matching.

    This serves as a fast, reliable fallback when LLM classification
    fails or times out.
    """

    # Patterns for different intent types
    SYMBOL_PATTERNS = [
        r"\b(function|class|method|variable|constant)\s+(\w+)",  # "function authenticate"
        r"\b(find|show|locate)\s+(\w+)\s+(function|class|method)",  # "find authenticate function"
        r"\b(\w+)\s+(definition|implementation|declaration)",  # "authenticate definition"
        r"^[\w.]+$",  # Single identifier like "authenticate" or "utils.auth"
    ]

    CONCEPT_PATTERNS = [
        r"\bhow\s+(does|do|is)\b",  # "how does authentication work"
        r"\bwhat\s+(is|are)\b",  # "what is the authentication system"
        r"\bexplain\b",  # "explain the authentication flow"
        r"\barchitecture\b",  # "authentication architecture"
        r"\bdesign\s+pattern\b",  # "design pattern for authentication"
        r"\bconcept\b",  # "authentication concept"
        r"\bsystem\b.*\bwork",  # "how does the system work"
    ]

    FLOW_TRACE_PATTERNS = [
        r"\btrace\b",  # "trace the call chain"
        r"\bcall\s+(chain|graph|flow|path)\b",  # "call chain from X to Y"
        r"\bexecution\s+(flow|path)\b",  # "execution flow"
        r"\bdata\s+flow\b",  # "data flow"
        r"\bfrom\s+(\w+)\s+to\s+(\w+)",  # "from login to database"
        r"\bpath\s+from\b",  # "path from X to Y"
    ]

    REPO_OVERVIEW_PATTERNS = [
        r"\bentry\s+point",  # "entry points"
        r"\bmain\s+(file|function|module)",  # "main function"
        r"\brepository\s+structure\b",  # "repository structure"
        r"\bproject\s+structure\b",  # "project structure"
        r"\boverview\b",  # "repository overview"
        r"\borganization\b",  # "code organization"
        r"^\s*structure\s*$",  # Just "structure"
    ]

    DOC_SEARCH_PATTERNS = [
        r"\bdocumentation\b",  # "authentication documentation"
        r"\bdocstring",  # "find docstring"
        r"\bdocs?\s+(for|of|about)\b",  # "docs for function"
        r"\bcomments?\s+(for|on|about)\b",  # "comments about authentication"
        r"\b(describe|describes|description)\b",  # "describe the function"
        r"\b(summarize|summary)\b",  # "summarize the API"
        r"\bapi\s+reference\b",  # "API reference"
        r"\bwhat\s+does\s+.+\s+do\b",  # "what does authenticate do" or "what does X function do"
        r"\bexplain\s+(\w+)\b.*\b(function|method|class)\b",  # "explain authenticate function"
    ]

    PATH_PATTERNS = [
        r"\b[\w/]+\.(py|ts|js|go|java|rs|cpp|c|h)\b",  # File extensions
        r"\bsrc/\w+",  # src/ paths
        r"\blib/\w+",  # lib/ paths
        r"\bin\s+([\w/]+\.[\w]+)",  # "in auth.py"
    ]

    def __init__(self):
        """Initialize rule-based classifier."""
        self._symbol_re = [re.compile(p, re.IGNORECASE) for p in self.SYMBOL_PATTERNS]
        self._concept_re = [re.compile(p, re.IGNORECASE) for p in self.CONCEPT_PATTERNS]
        self._flow_re = [re.compile(p, re.IGNORECASE) for p in self.FLOW_TRACE_PATTERNS]
        self._overview_re = [re.compile(p, re.IGNORECASE) for p in self.REPO_OVERVIEW_PATTERNS]
        self._doc_re = [re.compile(p, re.IGNORECASE) for p in self.DOC_SEARCH_PATTERNS]
        self._path_re = [re.compile(p, re.IGNORECASE) for p in self.PATH_PATTERNS]

    def classify(self, query: str) -> QueryIntent:
        """
        Classify query using rule-based patterns.

        Args:
            query: User query string

        Returns:
            QueryIntent with best-match intent kind
        """
        query_lower = query.lower().strip()

        # Extract features
        symbol_names = self._extract_symbols(query)
        file_paths = self._extract_paths(query)
        module_paths = self._extract_modules(query)

        # Score each intent type
        scores = {
            IntentKind.REPO_OVERVIEW: self._score_overview(query_lower),
            IntentKind.FLOW_TRACE: self._score_flow_trace(query_lower),
            IntentKind.CONCEPT_SEARCH: self._score_concept(query_lower),
            IntentKind.SYMBOL_NAV: self._score_symbol_nav(query_lower, symbol_names),
            IntentKind.DOC_SEARCH: self._score_doc_search(query_lower),
            IntentKind.CODE_SEARCH: 0.3,  # Default baseline
        }

        # Boost scores based on extracted features
        if symbol_names and len(symbol_names) == 1 and len(query.split()) <= 3:
            # Short query with single symbol → likely symbol navigation
            # BUT: Don't boost if query contains doc/concept patterns
            if scores[IntentKind.DOC_SEARCH] < 0.3 and scores[IntentKind.CONCEPT_SEARCH] < 0.3:
                scores[IntentKind.SYMBOL_NAV] += 0.4

        if file_paths:
            # Explicit file path → code search
            scores[IntentKind.CODE_SEARCH] += 0.3

        # Select best intent (with tie-breaking priority)
        # Priority order for ties: DOC_SEARCH > CONCEPT_SEARCH > CODE_SEARCH > others
        intent_priority = {
            IntentKind.DOC_SEARCH: 0,
            IntentKind.CONCEPT_SEARCH: 1,
            IntentKind.CODE_SEARCH: 2,
            IntentKind.FLOW_TRACE: 3,
            IntentKind.REPO_OVERVIEW: 4,
            IntentKind.SYMBOL_NAV: 5,
        }
        best_intent = max(scores, key=lambda k: (scores[k], -intent_priority.get(k, 99)))
        confidence = min(scores[best_intent], 1.0)

        # Determine if natural language
        is_nl = self._is_natural_language(query)

        return QueryIntent(
            kind=best_intent,
            symbol_names=symbol_names,
            file_paths=file_paths,
            module_paths=module_paths,
            is_nl=is_nl,
            confidence=confidence,
            raw_query=query,
        )

    def _score_symbol_nav(self, query: str, symbols: list[str]) -> float:
        """Score likelihood of symbol navigation intent."""
        score = 0.0

        for pattern in self._symbol_re:
            if pattern.search(query):
                score += 0.3

        # Boost if symbols extracted
        if symbols:
            score += 0.2

        return min(score, 1.0)

    def _score_concept(self, query: str) -> float:
        """Score likelihood of concept search intent."""
        score = 0.0

        for pattern in self._concept_re:
            if pattern.search(query):
                score += 0.35

        return min(score, 1.0)

    def _score_flow_trace(self, query: str) -> float:
        """Score likelihood of flow trace intent."""
        score = 0.0

        for pattern in self._flow_re:
            if pattern.search(query):
                score += 0.4

        return min(score, 1.0)

    def _score_overview(self, query: str) -> float:
        """Score likelihood of repository overview intent."""
        score = 0.0

        for pattern in self._overview_re:
            if pattern.search(query):
                score += 0.45

        return min(score, 1.0)

    def _score_doc_search(self, query: str) -> float:
        """Score likelihood of documentation search intent."""
        score = 0.0

        for pattern in self._doc_re:
            if pattern.search(query):
                score += 0.5  # Strong signal for doc search

        return min(score, 1.0)

    def _extract_symbols(self, query: str) -> list[str]:
        """Extract potential symbol names from query."""
        symbols = []

        # CamelCase identifiers
        camel_case = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", query)
        symbols.extend(camel_case)

        # snake_case identifiers
        snake_case = re.findall(r"\b[a-z_]+[a-z]\b", query)
        # Filter out common words
        common_words = {"the", "and", "for", "from", "with", "how", "what", "why", "when", "where"}
        symbols.extend([s for s in snake_case if s not in common_words and len(s) > 2])

        # Remove duplicates while preserving order
        seen = set()
        unique_symbols = []
        for sym in symbols:
            if sym not in seen:
                seen.add(sym)
                unique_symbols.append(sym)

        return unique_symbols[:5]  # Limit to top 5

    def _extract_paths(self, query: str) -> list[str]:
        """Extract file paths from query."""
        paths = []

        for pattern in self._path_re:
            matches = pattern.findall(query)
            if matches:
                if isinstance(matches[0], tuple):
                    paths.extend([m for m in matches if isinstance(m, str)])
                    paths.extend([m[0] for m in matches if isinstance(m, tuple)])
                else:
                    paths.extend(matches)

        return list(set(paths))[:3]  # Limit to top 3

    def _extract_modules(self, query: str) -> list[str]:
        """Extract module/package paths from query."""
        modules = []

        # Dotted paths like "auth.handlers.login"
        dotted = re.findall(r"\b[a-z_]+(?:\.[a-z_]+)+\b", query)
        modules.extend(dotted)

        return list(set(modules))[:3]

    def _is_natural_language(self, query: str) -> bool:
        """
        Determine if query is primarily natural language.

        Heuristic: presence of question words, articles, or multiple verbs.
        """
        nl_indicators = [
            r"\bhow\b",
            r"\bwhat\b",
            r"\bwhy\b",
            r"\bwhen\b",
            r"\bwhere\b",
            r"\bthe\b",
            r"\ban?\b",
            r"\bdoes\b",
            r"\bdo\b",
            r"\bis\b",
            r"\bare\b",
        ]

        matches = sum(1 for pattern in nl_indicators if re.search(pattern, query.lower()))

        return matches >= 2 or len(query.split()) > 5
