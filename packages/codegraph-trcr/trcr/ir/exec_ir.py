"""TaintRuleExecIR - RFC-033 Section 3.

Rule Execution IR (중간 표현).

NOTE: IRDocument (Program IR)와 완전히 다른 개념!
- IRDocument: Python code → AST → Program IR
- TaintRuleExecIR: YAML Rule → Execution Plan IR

Similar to:
- LLVM IR (compiler intermediate representation)
- JVM bytecode (executable intermediate form)
- SQL query plan (execution plan)
"""

from dataclasses import dataclass
from typing import Literal

from trcr.ir.generators import CandidatePlanIR
from trcr.ir.predicates import PredicateIR
from trcr.ir.scoring import ConfidenceIR, EffectIR, SpecificityIR, TracePolicyIR


@dataclass
class SourceSpan:
    """Source location in YAML file.

    For debugging and error messages.
    """

    file: str
    line_start: int
    col_start: int
    line_end: int
    col_end: int


@dataclass
class TaintRuleExecIR:
    """Rule Execution IR (중간 표현).

    RFC-033 Section 3.

    This is the "IR" for rule execution, similar to:
    - LLVM IR (compiler IR)
    - JVM bytecode
    - SQL query plan

    NOT to be confused with:
    - IRDocument: Python code → AST → Program IR

    One TaintRuleSpec with N match clauses → N TaintRuleExecIRs.
    Each IR represents ONE match clause execution plan.

    Components:
        1. candidate_plan: How to generate candidates
        2. predicate_chain: How to evaluate predicates
        3. specificity: How to rank this rule
        4. confidence: How confident we are
        5. effect: What happens when matched
        6. trace: Debug/explainability info
    """

    # Identity
    ir_id: str  # Stable internal ID: "{rule_id}:clause:{i}"
    rule_id: str
    atom_id: str
    tier: Literal["tier1", "tier2", "tier3"]
    clause_id: str  # Match clause identifier

    # Source location (for debugging)
    source_span: SourceSpan | None

    # === Core Components (RFC-033 Sections 4-10) ===

    # 1) Candidate generation plan
    candidate_plan: CandidatePlanIR

    # 2) Predicate evaluation chain
    predicate_chain: list[PredicateIR]

    # 3) Scoring
    specificity: SpecificityIR
    confidence: ConfidenceIR

    # 4) Effect on taint analysis
    effect: EffectIR

    # 5) Trace policy
    trace: TracePolicyIR

    # === Security Metadata (optional, from TaintRuleSpec) ===
    cwe: list[str] | None = None
    owasp: str | None = None
    severity: Literal["low", "medium", "high", "critical"] | None = None
    tags: list[str] | None = None
    description: str = ""

    def __post_init__(self) -> None:
        """Validate TaintRuleExecIR."""
        # IR ID format validation
        if not self.ir_id.startswith(f"{self.rule_id}:"):
            raise ValueError(f"ir_id must start with rule_id: {self.ir_id} vs {self.rule_id}")

        # Tier validation
        if self.tier not in ["tier1", "tier2", "tier3"]:
            raise ValueError(f"Invalid tier: {self.tier}")

        # Candidate plan required
        if not self.candidate_plan:
            raise ValueError("candidate_plan required")

        # At least one predicate (even if trivial)
        if not self.predicate_chain:
            raise ValueError("At least one predicate required")

    def estimate_cost(self) -> int:
        """Estimate execution cost.

        Returns:
            Total cost estimate (generator + predicates)
        """
        # Generator cost
        gen_cost = min(g.cost_hint for g in self.candidate_plan.generators)

        # Predicate cost (best case: first fails)
        pred_cost = self.predicate_chain[0].cost_hint if self.predicate_chain else 0

        return gen_cost + pred_cost
