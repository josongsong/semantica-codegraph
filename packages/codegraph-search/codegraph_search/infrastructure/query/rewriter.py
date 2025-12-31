"""
Query Rewriter

Transforms natural language queries into optimized code search keywords.
Implements Phase 3 Action 14-1 from the retrieval execution plan.
"""

import re
from dataclasses import dataclass

from codegraph_shared.common.observability import get_logger
from codegraph_search.infrastructure.intent import IntentKind

logger = get_logger(__name__)


@dataclass
class RewrittenQuery:
    """Rewritten query with optimized keywords."""

    original: str
    rewritten: str
    keywords: list[str]
    removed_stopwords: list[str]
    domain_terms: dict[str, str]  # original → mapped term
    strategy: str  # "lexical_optimized", "symbol_focused", etc.


# Common code-related stop words (less aggressive than NLP stopwords)
CODE_STOPWORDS = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "should",
    "could",
    "may",
    "might",
    "can",
    "this",
    "that",
    "these",
    "those",
    "i",
    "you",
    "we",
    "they",
    "it",
    "what",
    "which",
    "who",
    "where",
    "when",
    "why",
    "how",
}

# Domain-specific term mappings (common natural language → code terms)
DOMAIN_MAPPINGS = {
    # Authentication/Authorization
    "login": ["authenticate", "login", "sign_in", "auth"],
    "logout": ["logout", "sign_out", "logoff"],
    "authentication": ["auth", "authenticate", "authentication", "verify"],
    "authorization": ["authz", "authorize", "permission", "access_control"],
    "password": ["password", "passwd", "credential", "secret"],
    "token": ["token", "jwt", "bearer", "session"],
    # Data operations
    "save": ["save", "store", "persist", "write", "insert"],
    "load": ["load", "fetch", "retrieve", "read", "get", "find"],
    "delete": ["delete", "remove", "destroy", "drop"],
    "update": ["update", "modify", "edit", "change", "patch"],
    "create": ["create", "add", "new", "insert", "make"],
    # HTTP/API
    "endpoint": ["endpoint", "route", "handler", "api", "path"],
    "request": ["request", "req", "http_request"],
    "response": ["response", "resp", "http_response"],
    "error": ["error", "exception", "failure", "err"],
    # Database
    "database": ["database", "db", "storage", "datastore"],
    "query": ["query", "sql", "search", "find"],
    "table": ["table", "model", "entity", "collection"],
    # Common patterns
    "configuration": ["config", "configuration", "settings", "options"],
    "initialize": ["init", "initialize", "setup", "start"],
    "validate": ["validate", "verify", "check", "ensure"],
    "process": ["process", "handle", "execute", "run"],
    "connection": ["connection", "conn", "link", "client"],
}

# Code-specific keywords that should be preserved
CODE_KEYWORDS = {
    "class",
    "function",
    "method",
    "def",
    "async",
    "await",
    "return",
    "import",
    "from",
    "raise",
    "try",
    "except",
    "if",
    "else",
    "for",
    "while",
    "with",
    "lambda",
    "yield",
}


class QueryRewriter:
    """
    Rewrites natural language queries into optimized code search keywords.

    Strategy varies by intent:
    - code_search: Extract keywords + domain mappings
    - symbol_nav: Preserve symbol names, remove natural language
    - concept_search: Keep semantic terms, light stopword removal
    - flow_trace: Focus on action verbs and function names
    """

    def __init__(self):
        """Initialize query rewriter."""
        self.stopwords = CODE_STOPWORDS
        self.domain_mappings = DOMAIN_MAPPINGS
        self.code_keywords = CODE_KEYWORDS

    def rewrite(self, query: str, intent: IntentKind, language_hint: str | None = None) -> RewrittenQuery:
        """
        Rewrite query based on intent.

        Args:
            query: Original query
            intent: Query intent kind
            language_hint: Programming language hint (e.g., "python")

        Returns:
            RewrittenQuery with optimized keywords
        """
        if intent == IntentKind.CODE_SEARCH:
            return self._rewrite_code_search(query)
        elif intent == IntentKind.SYMBOL_NAV:
            return self._rewrite_symbol_nav(query)
        elif intent == IntentKind.CONCEPT_SEARCH:
            return self._rewrite_concept_search(query)
        elif intent == IntentKind.FLOW_TRACE:
            return self._rewrite_flow_trace(query)
        elif intent == IntentKind.REPO_OVERVIEW:
            return self._rewrite_repo_overview(query)
        else:
            # Fallback: basic keyword extraction
            return self._rewrite_basic(query)

    def _rewrite_code_search(self, query: str) -> RewrittenQuery:
        """
        Rewrite for code_search intent.

        Strategy:
        - Extract keywords
        - Map natural language to code terms
        - Preserve CamelCase/snake_case identifiers
        - Remove stopwords
        """
        original = query
        tokens = self._tokenize(query)

        # Preserve code identifiers (CamelCase, snake_case)
        preserved = self._extract_code_identifiers(tokens)

        # Remove stopwords
        filtered = [t for t in tokens if t.lower() not in self.stopwords]
        removed_stopwords = [t for t in tokens if t.lower() in self.stopwords]

        # Apply domain mappings
        domain_terms = {}
        expanded = []
        for token in filtered:
            lower = token.lower()
            if lower in self.domain_mappings:
                domain_terms[token] = ", ".join(self.domain_mappings[lower][:3])
                expanded.extend(self.domain_mappings[lower][:3])
            else:
                expanded.append(token)

        # Combine preserved identifiers + expanded terms
        keywords = list(set(preserved + expanded))

        # Build rewritten query
        rewritten = " ".join(keywords)

        return RewrittenQuery(
            original=original,
            rewritten=rewritten,
            keywords=keywords,
            removed_stopwords=removed_stopwords,
            domain_terms=domain_terms,
            strategy="lexical_optimized",
        )

    def _rewrite_symbol_nav(self, query: str) -> RewrittenQuery:
        """
        Rewrite for symbol_nav intent.

        Strategy:
        - Extract symbol names (CamelCase, snake_case)
        - Remove all natural language
        - Preserve class/function keywords
        """
        original = query
        tokens = self._tokenize(query)

        # Extract code identifiers only
        identifiers = self._extract_code_identifiers(tokens)

        # Keep code keywords (class, function, def, etc.)
        code_keywords = [t for t in tokens if t.lower() in self.code_keywords]

        keywords = list(set(identifiers + code_keywords))
        rewritten = " ".join(keywords)

        return RewrittenQuery(
            original=original,
            rewritten=rewritten,
            keywords=keywords,
            removed_stopwords=[],
            domain_terms={},
            strategy="symbol_focused",
        )

    def _rewrite_concept_search(self, query: str) -> RewrittenQuery:
        """
        Rewrite for concept_search intent.

        Strategy:
        - Keep semantic terms (don't over-filter)
        - Light stopword removal
        - Preserve technical terms
        """
        original = query
        tokens = self._tokenize(query)

        # Less aggressive stopword removal for concept search
        light_stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "this",
            "that",
        }
        filtered = [t for t in tokens if t.lower() not in light_stopwords]
        removed = [t for t in tokens if t.lower() in light_stopwords]

        keywords = filtered
        rewritten = " ".join(keywords)

        return RewrittenQuery(
            original=original,
            rewritten=rewritten,
            keywords=keywords,
            removed_stopwords=removed,
            domain_terms={},
            strategy="semantic_preserved",
        )

    def _rewrite_flow_trace(self, query: str) -> RewrittenQuery:
        """
        Rewrite for flow_trace intent.

        Strategy:
        - Focus on action verbs (call, invoke, execute, etc.)
        - Extract function/method names
        - Keep directional terms (from, to, through)
        """
        original = query
        tokens = self._tokenize(query)

        # Action verbs to preserve
        action_verbs = {
            "call",
            "calls",
            "called",
            "invoke",
            "invokes",
            "execute",
            "executes",
            "run",
            "runs",
            "trigger",
            "triggers",
            "flow",
            "flows",
            "goes",
            "lead",
            "leads",
            "route",
            "routes",
        }

        # Directional terms
        directional = {"from", "to", "through", "via", "into", "before", "after"}

        # Extract identifiers + action verbs + directional terms
        identifiers = self._extract_code_identifiers(tokens)
        actions = [t for t in tokens if t.lower() in action_verbs]
        directions = [t for t in tokens if t.lower() in directional]

        keywords = list(set(identifiers + actions + directions))
        rewritten = " ".join(keywords)

        return RewrittenQuery(
            original=original,
            rewritten=rewritten,
            keywords=keywords,
            removed_stopwords=[],
            domain_terms={},
            strategy="flow_focused",
        )

    def _rewrite_repo_overview(self, query: str) -> RewrittenQuery:
        """
        Rewrite for repo_overview intent.

        Strategy:
        - Focus on structural terms (structure, architecture, overview)
        - Preserve module/package names
        """
        original = query
        tokens = self._tokenize(query)

        # Structural terms to preserve
        structural = {
            "structure",
            "architecture",
            "overview",
            "layout",
            "organization",
            "entry",
            "entrypoint",
            "main",
            "index",
            "root",
        }

        filtered = [t for t in tokens if t.lower() not in self.stopwords]
        structural_terms = [t for t in filtered if t.lower() in structural]
        identifiers = self._extract_code_identifiers(tokens)

        keywords = list(set(structural_terms + identifiers + filtered))
        rewritten = " ".join(keywords)

        return RewrittenQuery(
            original=original,
            rewritten=rewritten,
            keywords=keywords,
            removed_stopwords=[],
            domain_terms={},
            strategy="structural_focused",
        )

    def _rewrite_basic(self, query: str) -> RewrittenQuery:
        """Fallback rewriting strategy."""
        original = query
        tokens = self._tokenize(query)
        filtered = [t for t in tokens if t.lower() not in self.stopwords]
        removed = [t for t in tokens if t.lower() in self.stopwords]

        rewritten = " ".join(filtered)

        return RewrittenQuery(
            original=original,
            rewritten=rewritten,
            keywords=filtered,
            removed_stopwords=removed,
            domain_terms={},
            strategy="basic",
        )

    def _tokenize(self, text: str) -> list[str]:
        """
        Tokenize text while preserving code identifiers.

        Preserves:
        - CamelCase (e.g., UserAuthenticator)
        - snake_case (e.g., user_authenticator)
        - SCREAMING_SNAKE_CASE (e.g., MAX_RETRIES)
        - Qualified names (e.g., module.Class.method)
        """
        # Split on whitespace and common punctuation (but preserve _ and .)
        tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_.]*|[a-zA-Z]+", text)
        return [t for t in tokens if t]

    def _extract_code_identifiers(self, tokens: list[str]) -> list[str]:
        """
        Extract code identifiers (CamelCase, snake_case, etc.).

        Args:
            tokens: List of tokens

        Returns:
            List of code identifiers
        """
        identifiers = []

        for token in tokens:
            # CamelCase (at least one lowercase followed by uppercase)
            if re.match(r"[a-z]+[A-Z]", token):
                identifiers.append(token)
            # snake_case (contains underscore)
            elif "_" in token and token.replace("_", "").isalnum():
                identifiers.append(token)
            # SCREAMING_SNAKE_CASE
            elif "_" in token and token.isupper():
                identifiers.append(token)
            # Qualified names (contains .)
            elif "." in token and all(part.replace("_", "").isalnum() for part in token.split(".")):
                identifiers.append(token)

        return identifiers

    def explain(self, rewritten: RewrittenQuery) -> str:
        """
        Generate human-readable explanation of rewriting.

        Args:
            rewritten: Rewritten query

        Returns:
            Explanation string
        """
        parts = [f"Strategy: {rewritten.strategy}"]

        if rewritten.removed_stopwords:
            parts.append(f"Removed stopwords: {', '.join(rewritten.removed_stopwords[:5])}")

        if rewritten.domain_terms:
            parts.append("Domain mappings:")
            for orig, mapped in list(rewritten.domain_terms.items())[:3]:
                parts.append(f"  - '{orig}' → {mapped}")

        parts.append(f"Final keywords: {', '.join(rewritten.keywords[:10])}")

        return "\n".join(parts)
