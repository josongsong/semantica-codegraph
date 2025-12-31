"""Rule Compiler - RFC-033 Implementation.

Complete compilation pipeline:
    YAML → TaintRuleSpec → TaintRuleExecIR → TaintRuleExecutableIR

Modules:
    - compiler: Main TaintRuleCompiler orchestration
    - ir_builder: MatchClauseSpec → TaintRuleExecIR
    - tier_inference: Automatic tier classification
"""

from trcr.compiler.compiler import CompilationError, TaintRuleCompiler
from trcr.compiler.ir_builder import IRBuildError, build_exec_ir
from trcr.compiler.tier_inference import (
    calculate_specificity_score,
    infer_tier,
    infer_tier_batch,
)

__all__ = [
    "TaintRuleCompiler",
    "CompilationError",
    "build_exec_ir",
    "IRBuildError",
    "infer_tier",
    "infer_tier_batch",
    "calculate_specificity_score",
]
