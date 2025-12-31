"""
codegraph-trcr: Taint Rule Compiler & Runtime

Integrated from: taint-rule-compiler v0.3.0
Purpose: Production-grade taint analysis with 488 atoms and CWE rules
"""

from trcr import (
    TaintRuleCompiler,
    TaintRuleExecutor,
    # Re-export key classes
)

__version__ = "0.3.0"
__all__ = ["TaintRuleCompiler", "TaintRuleExecutor"]
