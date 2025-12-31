"""TaintRuleExecutableIR - RFC-033 Section 12.

Fully compiled, optimized, executable rule.

This is the final form after all optimization passes (RFC-037).
This is what actually runs at matching time.
"""

from dataclasses import dataclass
from typing import Literal

from trcr.ir.generators import CandidatePlanIR
from trcr.ir.predicates import PredicateExecPlan
from trcr.ir.scoring import ConfidenceIR, EffectIR, SpecificityIR, TracePolicyIR


@dataclass
class GeneratorExecPlan:
    """Optimized generator execution plan.

    After optimization passes (RFC-037):
        - Best generator selected
        - Prefilters reordered
        - Cache policy optimized
    """

    candidate_plan: CandidatePlanIR
    estimated_candidates: int  # Expected number of candidates
    cache_hit_rate: float = 0.0  # Historical cache hit rate


@dataclass
class TaintRuleExecutableIR:
    """Fully compiled, optimized, executable rule.

    RFC-033 Section 12.

    Final form after all optimization passes (RFC-037).
    This is what actually runs at matching time.

    Naming: TaintRuleExecutableIR (not CompiledRule)
        - Avoids confusion with IRDocument
        - Clear intent: executable
        - Consistent with TaintRuleExecIR

    Execution model:
        1. Run generator_exec to get candidates
        2. Apply prefilters (cheap gates)
        3. Run predicate_exec (short-circuit on failure)
        4. Calculate confidence
        5. Check reporting threshold
        6. Emit trace if enabled

    Ordering:
        Rules are ordered by specificity for deterministic execution.
        See __lt__ for tie-breaking logic.
    """

    # Identity
    compiled_id: str  # Unique compiled ID
    rule_id: str
    atom_id: str
    tier: Literal["tier1", "tier2", "tier3"]

    # Execution plans (optimized!)
    generator_exec: GeneratorExecPlan
    predicate_exec: PredicateExecPlan

    # Scoring
    specificity: SpecificityIR
    confidence: ConfidenceIR

    # Effect
    effect: EffectIR

    # Debug
    trace: TracePolicyIR

    # Compilation metadata
    compilation_timestamp: float  # Unix timestamp
    optimizer_passes: list[str]  # Which passes were applied

    # === Security Metadata (for reporting) - optional ===
    cwe: list[str] | None = None  # CWE identifiers: ["CWE-89"]
    owasp: str | None = None  # OWASP category: "A03:2021-Injection"
    severity: Literal["low", "medium", "high", "critical"] | None = None
    tags: list[str] | None = None  # Tags: ["injection", "sql"]
    description: str = ""  # Human-readable description

    def __post_init__(self) -> None:
        """Validate executable IR."""
        # Compiled ID format
        if not self.compiled_id:
            raise ValueError("compiled_id required")

        # Execution plans required
        if not self.generator_exec:
            raise ValueError("generator_exec required")

        if not self.predicate_exec:
            raise ValueError("predicate_exec required")

    def __lt__(self, other: "TaintRuleExecutableIR") -> bool:
        """Deterministic ordering for rule execution.

        RFC-033: Rules are ordered by specificity.

        Tie-breaking order:
            1. specificity.final_score (higher better)
            2. specificity.wildcard_count (lower better)
            3. specificity.literal_length (higher better)
            4. rule_id (lexicographic)

        Higher specificity rules are executed first.
        """
        # 1. Compare specificity
        if self.specificity.final_score != other.specificity.final_score:
            return self.specificity.final_score > other.specificity.final_score

        # 2. Compare wildcard count (lower is better)
        if self.specificity.wildcard_count != other.specificity.wildcard_count:
            return self.specificity.wildcard_count < other.specificity.wildcard_count

        # 3. Compare literal length (higher is better)
        if self.specificity.literal_length != other.specificity.literal_length:
            return self.specificity.literal_length > other.specificity.literal_length

        # 4. Lexicographic by rule_id
        return self.rule_id < other.rule_id

    def estimate_cost(self) -> int:
        """Estimate execution cost.

        Returns:
            Total cost estimate
        """
        gen_cost = min(g.cost_hint for g in self.generator_exec.candidate_plan.generators)
        pred_cost = self.predicate_exec.best_case_cost

        return gen_cost + pred_cost

    def should_report(self) -> bool:
        """Check if this rule should report matches.

        Based on confidence threshold.
        """
        return self.confidence.should_report()
