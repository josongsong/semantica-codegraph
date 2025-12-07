"""
Effect Analyzer - Side effect 분석

코드 statement의 side effect를 분석하여 relevance 점수 계산
"""

import ast
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EffectInfo:
    """Side effect 정보"""

    has_io: bool = False  # File/Network I/O
    has_db: bool = False  # Database access
    has_external_call: bool = False  # External API call
    modifies_global: bool = False  # Global state modification
    has_print: bool = False  # Console output

    def score(self) -> float:
        """
        Effect score (0.0 - 1.0)

        Returns:
            Higher score = more important side effects
        """
        score = 0.0

        if self.has_db:
            score += 0.4
        if self.has_io:
            score += 0.3
        if self.has_external_call:
            score += 0.2
        if self.modifies_global:
            score += 0.1
        if self.has_print:
            score += 0.05

        return min(score, 1.0)


class EffectAnalyzer:
    """
    실제 Effect Analyzer

    AST 분석 + heuristic으로 side effect 탐지
    """

    def __init__(self):
        # Known side-effect patterns
        self.io_keywords = {"open", "write", "read", "file", "save", "load"}
        self.db_keywords = {"query", "execute", "insert", "update", "delete", "select", "commit"}
        self.network_keywords = {"request", "post", "get", "fetch", "send", "http", "api"}
        self.print_keywords = {"print", "log", "debug", "info", "warn", "error"}

    def analyze_statement(self, statement: str) -> EffectInfo:
        """
        Statement의 side effect 분석

        Args:
            statement: Code statement

        Returns:
            EffectInfo
        """
        effect = EffectInfo()

        # Lowercase for case-insensitive matching
        stmt_lower = statement.lower()

        # Check I/O
        if any(kw in stmt_lower for kw in self.io_keywords):
            effect.has_io = True

        # Check DB
        if any(kw in stmt_lower for kw in self.db_keywords):
            effect.has_db = True

        # Check network
        if any(kw in stmt_lower for kw in self.network_keywords):
            effect.has_external_call = True

        # Check print/logging
        if any(kw in stmt_lower for kw in self.print_keywords):
            effect.has_print = True

        # Check global modification (heuristic)
        if "global " in stmt_lower or ".append(" in stmt_lower or ".extend(" in stmt_lower:
            effect.modifies_global = True

        # Try AST parsing for more accurate analysis
        try:
            tree = ast.parse(statement)

            for node in ast.walk(tree):
                # Function calls
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        func_name = node.func.id.lower()

                        if func_name in self.io_keywords:
                            effect.has_io = True
                        elif func_name in self.db_keywords:
                            effect.has_db = True
                        elif func_name in self.network_keywords:
                            effect.has_external_call = True
                        elif func_name in self.print_keywords:
                            effect.has_print = True

                # Global statements
                if isinstance(node, ast.Global):
                    effect.modifies_global = True

        except SyntaxError:
            # If AST parsing fails, rely on keyword matching
            pass

        logger.debug(f"Effect analysis for '{statement[:50]}...': score={effect.score():.2f}")

        return effect

    def is_pure(self, statement: str) -> bool:
        """
        Pure function 여부 (side effect 없음)

        Args:
            statement: Code statement

        Returns:
            True if pure (no side effects)
        """
        effect = self.analyze_statement(statement)
        return effect.score() == 0.0
