"""Rule Runtime - Execution Engine.

RFC-033: Runtime execution of compiled rules.

Components:
    - executor: TaintRuleExecutor (main execution engine)
    - evaluator: Predicate evaluation
    - matcher: Pattern matching (wildcard support)
"""

from trcr.runtime.evaluator import PredicateEvaluationError, evaluate_predicate
from trcr.runtime.executor import ExecutionError, TaintRuleExecutor
from trcr.runtime.matcher import (
    compile_wildcard_pattern,
    extract_prefix,
    extract_substring,
    extract_suffix,
    is_contains_pattern,
    is_prefix_pattern,
    is_suffix_pattern,
    wildcard_match,
)

__all__ = [
    "TaintRuleExecutor",
    "ExecutionError",
    "evaluate_predicate",
    "PredicateEvaluationError",
    "wildcard_match",
    "compile_wildcard_pattern",
    "is_suffix_pattern",
    "is_prefix_pattern",
    "is_contains_pattern",
    "extract_suffix",
    "extract_prefix",
    "extract_substring",
]
