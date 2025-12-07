"""
Semantic Patch Engine

SOTA 기능:
- AST-based structural transformation
- Pattern matching DSL (Comby-style)
- Idempotent patches
- Safety verification
"""

from .semantic_patch_engine import (
    ASTMatcher,
    MatchResult,
    PatchTemplate,
    PatternMatcher,
    PatternSyntax,
    RegexMatcher,
    SemanticPatchEngine,
    StructuralMatcher,
    TransformKind,
)

__all__ = [
    "SemanticPatchEngine",
    "PatchTemplate",
    "MatchResult",
    "PatternSyntax",
    "TransformKind",
    "PatternMatcher",
    "RegexMatcher",
    "StructuralMatcher",
    "ASTMatcher",
]
