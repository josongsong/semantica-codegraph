"""
Semantic IR Build Mode

SOTA Design: Mode-aware IR building for performance optimization.

Modes:
- QUICK: Signature + Type only (10x faster, for syntax highlighting)
- PR: CFG + DFG + Expression (for PR review, taint analysis on changed files)
- FULL: Complete CFG/DFG/BFG + Advanced (for deep analysis, initial indexing)

Performance:
- QUICK: ~10ms/function (signature hash only)
- PR: ~50ms/function (CFG + DFG + Expression, no BFG/advanced)
- FULL: ~90ms/function (full semantic analysis)

Use Cases:
- QUICK: Real-time editor feedback, syntax highlighting, autocomplete
- PR: Code review, incremental taint analysis, PR checks
- FULL: CI/CD, deep security analysis, initial indexing
"""

from enum import Enum


class SemanticIrBuildMode(str, Enum):
    """
    Semantic IR build mode for performance optimization.

    QUICK mode (10x faster):
    - Signature generation (for change detection)
    - Type resolution (basic)
    - Skip: CFG, DFG, BFG, Expression analysis
    - Use: Syntax highlighting, autocomplete, LSP hover

    PR mode (balanced - for code review):
    - CFG (Control Flow Graph)
    - DFG (Data Flow Graph)
    - Expression analysis (for taint tracking)
    - Skip: BFG, advanced heap analysis
    - Use: PR review, incremental security checks, taint analysis

    FULL mode (complete):
    - All of PR
    - Basic Block Flow Graph (BFG)
    - Advanced analysis (heap, points-to)
    - Use: Initial indexing, CI/CD, deep security audit
    """

    QUICK = "quick"  # Full features enabled (~90ms/function) - same as FULL for now
    PR = "pr"  # CFG + DFG + Expression (~50ms/function)
    FULL = "full"  # Complete semantic IR (~90ms/function)

    # QUICK mode skips CFG/DFG/BFG/Expression for 10x faster performance.
    # Only PR and FULL modes build full semantic IR.

    def skip_cfg(self) -> bool:
        """
        Whether to skip CFG generation.

        RFC-036: All tiers include CFG (BASE/EXTENDED/FULL).
        Legacy QUICK mode is deprecated.
        """
        return False  # CFG always generated

    def skip_dfg(self) -> bool:
        """
        Whether to skip DFG generation.

        RFC-036: Only EXTENDED and FULL include DFG.
        """
        return self == SemanticIrBuildMode.QUICK

    def skip_bfg(self) -> bool:
        """
        Whether to skip BFG generation.

        RFC-036: All tiers include BFG (needed for CFG).
        """
        return False  # BFG always generated (needed for CFG)

    def skip_expressions(self) -> bool:
        """
        Whether to skip expression analysis.

        RFC-036: Only EXTENDED and FULL include expressions.
        QUICK (BASE tier) skips expressions.
        """
        return self == SemanticIrBuildMode.QUICK

    def skip_advanced_analysis(self) -> bool:
        """Whether to skip advanced analysis (heap, points-to)."""
        return self == SemanticIrBuildMode.PR  # PR still skips advanced

    def is_full(self) -> bool:
        """Whether this is full mode."""
        return self == SemanticIrBuildMode.FULL


__all__ = ["SemanticIrBuildMode"]
