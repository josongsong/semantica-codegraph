"""
Statement Analyzer

Base interface for analyzing statements to extract variable reads/writes.
"""

from abc import ABC, abstractmethod


class BaseStatementAnalyzer(ABC):
    """
    Base interface for statement analysis.

    Language-specific analyzers implement this interface to extract
    variable reads and writes from AST nodes.
    """

    @abstractmethod
    def analyze(self, node) -> tuple[list[str], list[str]]:
        """
        Analyze a statement/expression node to extract variable usage.

        Args:
            node: AST node (tree-sitter node)

        Returns:
            (reads, writes): Lists of variable names read and written
        """
        raise NotImplementedError


class AnalyzerRegistry:
    """
    Registry for language-specific statement analyzers.
    """

    def __init__(self):
        self._analyzers: dict[str, BaseStatementAnalyzer] = {}

    def register(self, language: str, analyzer: BaseStatementAnalyzer):
        """Register analyzer for a language"""
        self._analyzers[language] = analyzer

    def get(self, language: str) -> BaseStatementAnalyzer:
        """Get analyzer for a language"""
        if language not in self._analyzers:
            raise ValueError(f"No analyzer registered for language: {language}")
        return self._analyzers[language]

    def has(self, language: str) -> bool:
        """Check if analyzer exists for language"""
        return language in self._analyzers
