"""IR Types - RFC-033 Implementation Spec.

Complete IR type system for TRCR compiler.

Type hierarchy:
    YAML → TaintRuleSpec → TaintRuleExecIR → TaintRuleExecutableIR

Components:
    - spec: Input models (TaintRuleSpec, MatchClauseSpec)
    - generators: 7 candidate generators + prefilters
    - predicates: 6 predicates + value constraints
    - scoring: Specificity, Confidence, Effect, Trace
    - exec_ir: TaintRuleExecIR (intermediate IR)
    - executable: TaintRuleExecutableIR (final executable)
"""

# Input models
# IR types
from trcr.ir.exec_ir import SourceSpan, TaintRuleExecIR
from trcr.ir.executable import GeneratorExecPlan, TaintRuleExecutableIR

# Generators (7 types)
from trcr.ir.generators import (
    CachePolicyIR,
    CallPrefixGenIR,
    CandidateGeneratorIR,
    CandidatePlanIR,
    ExactCallGenIR,
    ExactTypeCallGenIR,
    FallbackGenIR,
    GeneratorKind,
    PrefilterCallStartsWithIR,
    PrefilterHasArgIndexIR,
    PrefilterIR,
    PrefilterTypeEndsWithIR,
    TokenGenIR,
    TypeSuffixGenIR,
    TypeTrigramGenIR,
)

# Optimizer (RFC-037)
from trcr.ir.optimizer import (
    MergePass,
    NormalizePass,
    OptimizationPipeline,
    PrunePass,
    ReorderPass,
    get_default_pipeline,
    optimize_ir,
)

# Predicates (6 types) + Value constraints
from trcr.ir.predicates import (
    ArgConstraintPredicateIR,
    CallMatchPredicateIR,
    GuardPredicateIR,
    IsConstIR,
    IsIntLikeIR,
    IsNotConstIR,
    IsStringLikeIR,
    KwargConstraintPredicateIR,
    LengthBoundIR,
    MatchesRegexIR,
    PredicateExecPlan,
    PredicateIR,
    ReadPropertyPredicateIR,
    TypeMatchPredicateIR,
    ValueConstraintIR,
)

# Scoring
from trcr.ir.scoring import (
    ConfidenceAdjustmentIR,
    ConfidenceIR,
    ConstraintAdjustmentIR,
    EffectIR,
    GuardAdjustmentIR,
    SpecificityIR,
    TierAdjustmentIR,
    TraceField,
    TracePolicyIR,
    VulnerabilityIR,
)
from trcr.ir.spec import ConstraintSpec, MatchClauseSpec, TaintRuleSpec

__all__ = [
    # Input models
    "TaintRuleSpec",
    "MatchClauseSpec",
    "ConstraintSpec",
    # Generators
    "CandidateGeneratorIR",
    "ExactTypeCallGenIR",
    "ExactCallGenIR",
    "CallPrefixGenIR",
    "TypeSuffixGenIR",
    "TypeTrigramGenIR",
    "TokenGenIR",
    "FallbackGenIR",
    "GeneratorKind",
    "CandidatePlanIR",
    "PrefilterIR",
    "PrefilterCallStartsWithIR",
    "PrefilterTypeEndsWithIR",
    "PrefilterHasArgIndexIR",
    "CachePolicyIR",
    # Predicates
    "PredicateIR",
    "TypeMatchPredicateIR",
    "CallMatchPredicateIR",
    "ReadPropertyPredicateIR",
    "ArgConstraintPredicateIR",
    "KwargConstraintPredicateIR",
    "GuardPredicateIR",
    "ValueConstraintIR",
    "IsConstIR",
    "IsNotConstIR",
    "IsStringLikeIR",
    "IsIntLikeIR",
    "MatchesRegexIR",
    "LengthBoundIR",
    "PredicateExecPlan",
    # Scoring
    "SpecificityIR",
    "ConfidenceIR",
    "ConfidenceAdjustmentIR",
    "GuardAdjustmentIR",
    "ConstraintAdjustmentIR",
    "TierAdjustmentIR",
    "EffectIR",
    "VulnerabilityIR",
    "TracePolicyIR",
    "TraceField",
    # IR types
    "TaintRuleExecIR",
    "SourceSpan",
    "TaintRuleExecutableIR",
    "GeneratorExecPlan",
    # Optimizer
    "optimize_ir",
    "OptimizationPipeline",
    "NormalizePass",
    "PrunePass",
    "ReorderPass",
    "MergePass",
    "get_default_pipeline",
]
