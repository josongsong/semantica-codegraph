"""
AST Pattern Matching Module

Semgrep-style AST 패턴 매칭 및 메타변수 지원.
"""

from trcr.ast.metavariable import Metavariable, MetavariableBinding
from trcr.ast.pattern_ir import ASTPatternIR, PatternMatch
from trcr.ast.pattern_matcher import ASTPatternMatcher

__all__ = [
    "ASTPatternMatcher",
    "ASTPatternIR",
    "PatternMatch",
    "Metavariable",
    "MetavariableBinding",
]
