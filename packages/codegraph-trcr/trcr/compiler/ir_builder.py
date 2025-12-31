"""IR Builder - MatchClauseSpec → TaintRuleExecIR.

RFC-033 Section 14: Compilation Flow.

This module builds TaintRuleExecIR from MatchClauseSpec.
"""

import logging
from typing import Literal

from trcr.compiler.tier_inference import infer_tier
from trcr.ir.exec_ir import TaintRuleExecIR
from trcr.ir.generators import (
    CachePolicyIR,
    CallPrefixGenIR,
    CandidateGeneratorIR,
    CandidatePlanIR,
    ExactCallGenIR,
    ExactTypeCallGenIR,
    FallbackGenIR,
    PrefilterCallStartsWithIR,
    PrefilterIR,
    PrefilterTypeEndsWithIR,
    TypeSuffixGenIR,
    TypeTrigramGenIR,
)
from trcr.ir.predicates import (
    ArgConstraintPredicateIR,
    CallMatchPredicateIR,
    IsConstIR,
    IsIntLikeIR,
    IsNotConstIR,
    IsStringLikeIR,
    PredicateIR,
    ReadPropertyPredicateIR,
    TypeMatchPredicateIR,
    ValueConstraintIR,
)
from trcr.ir.scoring import (
    ConfidenceAdjustmentIR,
    ConfidenceIR,
    ConstraintAdjustmentIR,
    EffectIR,
    SpecificityIR,
    TierAdjustmentIR,
    TracePolicyIR,
    VulnerabilityIR,
)
from trcr.ir.spec import MatchClauseSpec, TaintRuleSpec

logger = logging.getLogger(__name__)


class IRBuildError(Exception):
    """IR building error."""

    pass


def build_exec_ir(
    spec: TaintRuleSpec,
    clause: MatchClauseSpec,
    clause_index: int,
) -> TaintRuleExecIR:
    """Build TaintRuleExecIR from MatchClauseSpec.

    RFC-033 Section 14: Compilation Flow.

    Steps:
        1. Infer tier from clause patterns
        2. Build candidate plan (generators + prefilters)
        3. Build predicate chain
        4. Calculate specificity
        5. Calculate confidence
        6. Build effect
        7. Set trace policy

    Args:
        spec: TaintRuleSpec (parent)
        clause: MatchClauseSpec to compile
        clause_index: Index of clause in spec.match

    Returns:
        TaintRuleExecIR

    Raises:
        IRBuildError: If building fails
    """
    # 1. Infer tier
    tier = infer_tier(clause)

    # 2. Build IR ID
    ir_id = f"{spec.rule_id}:clause:{clause_index}"
    clause_id = f"clause:{clause_index}"

    # 3. Build candidate plan
    candidate_plan = _build_candidate_plan(clause, tier)

    # 4. Build predicate chain
    predicate_chain = _build_predicate_chain(clause, tier)

    # 5. Calculate specificity
    specificity = _calculate_specificity(clause, tier)

    # 6. Calculate confidence
    confidence = _calculate_confidence(clause, tier)

    # 7. Build effect
    effect = _build_effect(spec, clause)

    # 8. Trace policy (production default)
    trace = TracePolicyIR.production()

    # 9. Build TaintRuleExecIR
    exec_ir = TaintRuleExecIR(
        ir_id=ir_id,
        rule_id=spec.rule_id,
        atom_id=spec.atom_id,
        tier=tier,
        clause_id=clause_id,
        source_span=None,  # TODO: Add YAML source location
        # Security metadata (from TaintRuleSpec)
        cwe=spec.cwe,
        owasp=spec.owasp,
        severity=spec.severity,
        tags=spec.tags,
        description=spec.description,
        # Core components
        candidate_plan=candidate_plan,
        predicate_chain=predicate_chain,
        specificity=specificity,
        confidence=confidence,
        effect=effect,
        trace=trace,
    )

    logger.debug(f"Built TaintRuleExecIR: {ir_id} (tier={tier})")
    return exec_ir


def _build_candidate_plan(
    clause: MatchClauseSpec,
    tier: Literal["tier1", "tier2", "tier3"],
) -> CandidatePlanIR:
    """Build candidate generation plan.

    RFC-033 Section 4: CandidatePlanIR.

    Strategy:
        - tier1: Exact hash lookup
        - tier2: Prefix/suffix trie
        - tier3: Trigram or fallback

    Args:
        clause: Match clause
        tier: Inferred tier

    Returns:
        CandidatePlanIR
    """
    generators: list[CandidateGeneratorIR] = []
    prefilters: list[PrefilterIR] = []

    # Exact type + exact call → ExactTypeCallGenIR
    if clause.base_type and clause.call:
        generators.append(
            ExactTypeCallGenIR(
                key=(clause.base_type, clause.call),
            )
        )
        cache_policy = CachePolicyIR.no_cache()  # Exact doesn't need cache

    # Exact call only → ExactCallGenIR
    elif clause.call and not clause.base_type and not clause.base_type_pattern:
        generators.append(
            ExactCallGenIR(
                key=clause.call,
            )
        )
        cache_policy = CachePolicyIR.no_cache()

    # Wildcard patterns
    elif clause.base_type_pattern or clause.call_pattern:
        # Type suffix pattern (*.Cursor)
        if clause.base_type_pattern and clause.base_type_pattern.startswith("*"):
            suffix = clause.base_type_pattern[1:]  # Remove leading *
            generators.append(TypeSuffixGenIR(suffix=suffix))
            prefilters.append(PrefilterTypeEndsWithIR(value=suffix))

        # Type contains pattern (*mongo*)
        elif clause.base_type_pattern and "*" in clause.base_type_pattern:
            # Extract trigrams
            pattern = clause.base_type_pattern.replace("*", "")
            if len(pattern) >= 3:
                trigrams = _extract_trigrams(pattern)
                generators.append(
                    TypeTrigramGenIR(
                        key={
                            "trigrams": trigrams,
                            "policy": "all",
                        }
                    )
                )
            else:
                # Pattern too short for trigrams, use fallback
                generators.append(FallbackGenIR(pattern=clause.base_type_pattern))

        # Call prefix pattern (subprocess.*)
        elif clause.call_pattern and clause.call_pattern.endswith("*"):
            prefix = clause.call_pattern[:-1]  # Remove trailing *
            generators.append(CallPrefixGenIR(prefix=prefix))
            prefilters.append(PrefilterCallStartsWithIR(value=prefix))

        # Call pattern with wildcards
        elif clause.call_pattern:
            # Fallback for complex call patterns
            generators.append(FallbackGenIR(pattern=clause.call_pattern))

        cache_policy = CachePolicyIR.default_cache()

    # Property read (HTTP sources)
    elif clause.read:
        # For property reads, we need to find entities with that property
        # This is typically handled by exact type matching
        if clause.base_type:
            generators.append(
                ExactTypeCallGenIR(
                    key=(clause.base_type, f"<read:{clause.read}>"),
                )
            )
        else:
            # Fallback: search all entities
            generators.append(FallbackGenIR(pattern=f".*{clause.read}.*"))
        cache_policy = CachePolicyIR.default_cache()

    else:
        # No specific generator, use fallback
        generators.append(FallbackGenIR(pattern=".*"))
        cache_policy = CachePolicyIR.default_cache()

    # Validate: at least one generator
    if not generators:
        raise IRBuildError("No candidate generators built")

    return CandidatePlanIR(
        generators=generators,
        prefilters=prefilters,
        cache_policy=cache_policy,
    )


def _build_predicate_chain(
    clause: MatchClauseSpec,
    tier: Literal["tier1", "tier2", "tier3"],
) -> list[PredicateIR]:
    """Build predicate evaluation chain.

    RFC-033 Section 6: PredicateIR.

    Predicates are ordered by cost (cheap first).

    Args:
        clause: Match clause
        tier: Inferred tier

    Returns:
        List of predicates
    """
    predicates: list[PredicateIR] = []

    # Type matching predicate
    if clause.base_type:
        predicates.append(
            TypeMatchPredicateIR(
                mode="exact",
                pattern=clause.base_type,
                matcher_id=f"type_exact:{clause.base_type}",
            )
        )
    elif clause.base_type_pattern:
        predicates.append(
            TypeMatchPredicateIR(
                mode="wildcard",
                pattern=clause.base_type_pattern,
                matcher_id=f"type_wildcard:{clause.base_type_pattern}",
            )
        )

    # Call matching predicate
    if clause.call:
        predicates.append(
            CallMatchPredicateIR(
                mode="exact",
                pattern=clause.call,
                matcher_id=f"call_exact:{clause.call}",
            )
        )
    elif clause.call_pattern:
        predicates.append(
            CallMatchPredicateIR(
                mode="wildcard",
                pattern=clause.call_pattern,
                matcher_id=f"call_wildcard:{clause.call_pattern}",
            )
        )

    # Property read predicate
    if clause.read:
        predicates.append(
            ReadPropertyPredicateIR(
                property_name=clause.read,
            )
        )

    # Argument constraints
    if clause.constraints and clause.constraints.arg_type:
        # Build value constraints
        value_constraints: list[ValueConstraintIR] = []

        arg_type = clause.constraints.arg_type

        if arg_type == "not_const":
            value_constraints.append(IsNotConstIR())
        elif arg_type == "const":
            value_constraints.append(IsConstIR())
        elif arg_type == "const_string":
            # const_string = const + string
            value_constraints.append(IsConstIR())
            value_constraints.append(IsStringLikeIR())
        elif arg_type == "string":
            value_constraints.append(IsStringLikeIR())
        elif arg_type == "int":
            value_constraints.append(IsIntLikeIR())
        # "any" requires no constraints

        # Add arg constraint predicate for each arg position (only if constraints exist)
        if value_constraints:
            for arg_idx in clause.args or [0]:  # Default to arg 0 if not specified
                predicates.append(
                    ArgConstraintPredicateIR(
                        arg_index=arg_idx,
                        constraints=value_constraints,
                    )
                )

    # Validate: at least one predicate
    if not predicates:
        raise IRBuildError("No predicates built")

    # Sort by cost (cheap first)
    predicates.sort(key=lambda p: p.cost_hint)

    return predicates


def _calculate_specificity(
    clause: MatchClauseSpec,
    tier: Literal["tier1", "tier2", "tier3"],
) -> SpecificityIR:
    """Calculate specificity for clause.

    RFC-033 Section 7: SpecificityIR.

    Args:
        clause: Match clause
        tier: Inferred tier

    Returns:
        SpecificityIR
    """
    # Count wildcards
    wildcard_count = 0
    if clause.base_type_pattern:
        wildcard_count += clause.base_type_pattern.count("*")
    if clause.call_pattern:
        wildcard_count += clause.call_pattern.count("*")

    # Count literal characters
    literal_length = 0
    if clause.base_type:
        literal_length += len(clause.base_type)
    elif clause.base_type_pattern:
        literal_length += len(clause.base_type_pattern.replace("*", ""))

    if clause.call:
        literal_length += len(clause.call)
    elif clause.call_pattern:
        literal_length += len(clause.call_pattern.replace("*", ""))

    return SpecificityIR.from_tier(
        tier=tier,
        wildcard_count=wildcard_count,
        literal_length=literal_length,
    )


def _calculate_confidence(
    clause: MatchClauseSpec,
    tier: Literal["tier1", "tier2", "tier3"],
) -> ConfidenceIR:
    """Calculate confidence for clause.

    RFC-033 Section 8: ConfidenceIR.

    Args:
        clause: Match clause
        tier: Inferred tier

    Returns:
        ConfidenceIR
    """
    # Base confidence from tier
    tier_adj = TierAdjustmentIR.from_tier(tier)
    base_confidence = tier_adj.value

    # Adjustments
    adjustments: list[ConfidenceAdjustmentIR] = [tier_adj]

    # Constraint satisfaction adds confidence
    if clause.constraints and clause.constraints.arg_type == "not_const":
        adjustments.append(
            ConstraintAdjustmentIR(
                op="add",
                value=0.05,
                reason="not_const",
            )
        )

    return ConfidenceIR(
        base_confidence=base_confidence,
        adjustments=adjustments,
        min_report_threshold=0.7,
    )


def _infer_category_from_tags(tags: list[str]) -> str:
    """Infer vulnerability category from tags.

    Args:
        tags: List of tags

    Returns:
        Inferred category
    """
    tag_to_category = {
        "injection": "Injection",
        "sql": "SQL Injection",
        "command": "Command Injection",
        "xss": "Cross-Site Scripting",
        "path": "Path Traversal",
        "deserialize": "Deserialization",
        "ssrf": "Server-Side Request Forgery",
        "xxe": "XML External Entity",
        "buffer": "Buffer Overflow",
        "format": "Format String",
        "memory": "Memory Safety",
        "crypto": "Cryptography",
        "auth": "Authentication",
        "access": "Access Control",
    }

    for tag in tags:
        if tag in tag_to_category:
            return tag_to_category[tag]

    return "Unknown"


def _build_effect(
    spec: TaintRuleSpec,
    clause: MatchClauseSpec,
) -> EffectIR:
    """Build effect for clause.

    RFC-033 Section 9: EffectIR.

    Args:
        spec: TaintRuleSpec (parent)
        clause: Match clause

    Returns:
        EffectIR
    """
    # Build vulnerability info for sinks
    vulnerability = None
    if spec.kind == "sink":
        vulnerability = VulnerabilityIR(
            cwe=spec.cwe[0] if spec.cwe else None,
            category=_infer_category_from_tags(spec.tags),
            severity=spec.severity or "medium",
        )

    return EffectIR(
        kind=spec.kind,
        arg_positions=clause.args or [],
        read_property=clause.read,
        write_target="return" if spec.kind == "source" else None,
        vulnerability=vulnerability,
    )


def _extract_trigrams(text: str) -> list[str]:
    """Extract trigrams from text.

    RFC-034: Trigram Index.

    Args:
        text: Text to extract trigrams from

    Returns:
        List of trigrams

    Examples:
        >>> _extract_trigrams("mongo")
        ['mon', 'ong', 'ngo']
    """
    if len(text) < 3:
        return []

    trigrams = []
    for i in range(len(text) - 2):
        trigrams.append(text[i : i + 3])

    return trigrams
