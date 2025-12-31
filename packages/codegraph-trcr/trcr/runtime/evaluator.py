"""Predicate Evaluator - RFC-033 Section 6.

Evaluates predicates against entities.

Each predicate returns (passed: bool, confidence_adjustment: float).
"""

import logging

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
    PredicateIR,
    ReadPropertyPredicateIR,
    TypeMatchPredicateIR,
    ValueConstraintIR,
)
from trcr.runtime.matcher import wildcard_match
from trcr.types.entity import Entity
from trcr.types.match import MatchContext

logger = logging.getLogger(__name__)


class PredicateEvaluationError(Exception):
    """Predicate evaluation error."""

    pass


def evaluate_predicate(
    predicate: PredicateIR,
    entity: Entity,
    context: MatchContext,
) -> tuple[bool, float]:
    """Evaluate predicate against entity.

    RFC-033: Predicate evaluation with short-circuit support.

    Args:
        predicate: Predicate to evaluate
        entity: Entity to check
        context: Match context

    Returns:
        (passed, confidence_adjustment) tuple
            - passed: True if predicate passes
            - confidence_adjustment: Adjustment to add to confidence

    Raises:
        PredicateEvaluationError: If evaluation fails
    """
    if isinstance(predicate, TypeMatchPredicateIR):
        return _evaluate_type_match(predicate, entity)

    elif isinstance(predicate, CallMatchPredicateIR):
        return _evaluate_call_match(predicate, entity)

    elif isinstance(predicate, ReadPropertyPredicateIR):
        return _evaluate_read_property(predicate, entity)

    elif isinstance(predicate, ArgConstraintPredicateIR):
        return _evaluate_arg_constraint(predicate, entity)

    elif isinstance(predicate, KwargConstraintPredicateIR):
        return _evaluate_kwarg_constraint(predicate, entity)

    elif isinstance(predicate, GuardPredicateIR):
        return _evaluate_guard(predicate, entity, context)

    else:
        raise PredicateEvaluationError(f"Unknown predicate type: {type(predicate)}")


def _evaluate_type_match(
    predicate: TypeMatchPredicateIR,
    entity: Entity,
) -> tuple[bool, float]:
    """Evaluate type matching predicate.

    Args:
        predicate: Type match predicate
        entity: Entity to check

    Returns:
        (passed, confidence_adjustment)
    """
    if not entity.base_type:
        return (False, 0.0)

    if predicate.mode == "exact":
        matches = entity.base_type == predicate.pattern
        confidence_adj = 0.0  # Exact match, no adjustment

    elif predicate.mode == "wildcard":
        from trcr.config import DEFAULT_CONFIDENCE_CONFIG

        matches = wildcard_match(predicate.pattern, entity.base_type)
        confidence_adj = DEFAULT_CONFIDENCE_CONFIG.WILDCARD_ADJUSTMENT

    else:
        raise PredicateEvaluationError(f"Unknown mode: {predicate.mode}")

    if predicate.negate:
        matches = not matches

    return (matches, confidence_adj if matches else 0.0)


def _evaluate_call_match(
    predicate: CallMatchPredicateIR,
    entity: Entity,
) -> tuple[bool, float]:
    """Evaluate call matching predicate.

    Supports both simple call names and qualified call names:
        - Simple: "execute", "input"
        - Qualified: "sqlite3.Cursor.execute", "os.system"

    Args:
        predicate: Call match predicate
        entity: Entity to check

    Returns:
        (passed, confidence_adjustment)
    """
    if entity.kind != "call":
        return (False, 0.0)

    if not entity.call:
        return (False, 0.0)

    if predicate.mode == "exact":
        # P0-2 Fix: Check both simple call AND qualified_call
        # This enables matching rules like:
        #   - call: execute  → matches entity.call
        #   - call: sqlite3.Cursor.execute → matches entity.qualified_call
        matches = entity.call == predicate.pattern or entity.qualified_call == predicate.pattern
        confidence_adj = 0.0

    elif predicate.mode == "wildcard":
        from trcr.config import DEFAULT_CONFIDENCE_CONFIG

        # Check both call and qualified_call for wildcard patterns
        matches = wildcard_match(predicate.pattern, entity.call) or (
            entity.qualified_call and wildcard_match(predicate.pattern, entity.qualified_call)
        )
        confidence_adj = DEFAULT_CONFIDENCE_CONFIG.WILDCARD_ADJUSTMENT

    else:
        raise PredicateEvaluationError(f"Unknown mode: {predicate.mode}")

    if predicate.negate:
        matches = not matches

    return (matches, confidence_adj if matches else 0.0)


def _evaluate_read_property(
    predicate: ReadPropertyPredicateIR,
    entity: Entity,
) -> tuple[bool, float]:
    """Evaluate property read predicate.

    Args:
        predicate: Read property predicate
        entity: Entity to check

    Returns:
        (passed, confidence_adjustment)
    """
    if entity.kind != "read":
        return (False, 0.0)

    if not entity.read:
        return (False, 0.0)

    matches = entity.read == predicate.property_name

    if predicate.negate:
        matches = not matches

    return (matches, 0.0)


def _evaluate_arg_constraint(
    predicate: ArgConstraintPredicateIR,
    entity: Entity,
) -> tuple[bool, float]:
    """Evaluate argument constraint predicate.

    RFC-033: Semantic argument constraints.

    Args:
        predicate: Argument constraint predicate
        entity: Entity to check

    Returns:
        (passed, confidence_adjustment)
    """
    if entity.kind != "call":
        return (False, 0.0)

    # Check if arg exists
    arg = entity.get_arg(predicate.arg_index)
    if arg is None:
        return (False, 0.0)

    # Evaluate all constraints
    total_adjustment = 0.0

    for constraint in predicate.constraints:
        passed, adj = _evaluate_value_constraint(constraint, entity, predicate.arg_index)
        if not passed:
            return (False, 0.0)  # Any constraint fails → predicate fails
        total_adjustment += adj

    return (True, total_adjustment)


def _evaluate_kwarg_constraint(
    predicate: KwargConstraintPredicateIR,
    entity: Entity,
) -> tuple[bool, float]:
    """Evaluate keyword argument constraint predicate.

    RFC-033: Kwarg constraints for dangerous patterns.

    Examples:
        - shell=True → very dangerous!
        - check_hostname=False → security risk!

    Args:
        predicate: Kwarg constraint predicate
        entity: Entity to check

    Returns:
        (passed, confidence_adjustment)
    """
    if entity.kind != "call":
        return (False, 0.0)

    # Check if kwarg exists
    kwarg_value = entity.get_kwarg(predicate.kwarg_name)
    if kwarg_value is None:
        return (False, 0.0)

    # Evaluate all constraints on kwarg value
    from trcr.config import DEFAULT_CONFIDENCE_CONFIG

    total_adjustment = 0.0

    for constraint in predicate.constraints:
        if isinstance(constraint, IsConstIR):
            # For kwargs, check if value is a constant (not a variable)
            # If it's a literal value (True, False, string, int), it's constant
            is_const = isinstance(kwarg_value, (bool, int, float, str, bytes, type(None)))
            if not is_const:
                return (False, 0.0)

        elif isinstance(constraint, IsNotConstIR):
            # Kwarg value is NOT constant (dynamic)
            is_const = isinstance(kwarg_value, (bool, int, float, str, bytes, type(None)))
            if is_const:
                return (False, 0.0)
            total_adjustment += DEFAULT_CONFIDENCE_CONFIG.NOT_CONST_ADJUSTMENT

        elif isinstance(constraint, IsStringLikeIR):
            if not isinstance(kwarg_value, (str, bytes)):
                return (False, 0.0)

        elif isinstance(constraint, IsIntLikeIR):
            if not isinstance(kwarg_value, int):
                return (False, 0.0)

    # Special cases: dangerous kwarg values
    # shell=True is VERY dangerous
    if predicate.kwarg_name == "shell" and kwarg_value is True:
        total_adjustment += 0.2  # High confidence boost for dangerous pattern

    # check_hostname=False is a security risk
    if predicate.kwarg_name == "check_hostname" and kwarg_value is False:
        total_adjustment += 0.15

    # verify=False (disable SSL verification)
    if predicate.kwarg_name == "verify" and kwarg_value is False:
        total_adjustment += 0.15

    return (True, total_adjustment)


def _evaluate_guard(
    predicate: GuardPredicateIR,
    entity: Entity,
    context: MatchContext,
) -> tuple[bool, float]:
    """Evaluate guard predicate.

    RFC-038: Guard-aware Execution.

    Guards are detected by CFG analysis in codegraph and provided via Entity.guards.
    This evaluator checks if a matching guard is present and adjusts confidence.

    Guard Types:
        - sanitizer: Input sanitization (escape, quote, parameterize)
        - validator: Input validation (type check, regex, length)
        - encoder: Output encoding (html_escape, url_encode)

    Args:
        predicate: Guard predicate
        entity: Entity to check
        context: Match context

    Returns:
        (passed, confidence_adjustment)
    """

    # Check if entity has guards (provided by codegraph via Entity protocol)
    guards = getattr(entity, "guards", [])

    if not guards:
        # No guards detected - proceed with normal confidence
        return (True, 0.0)

    # Check if any guard matches the predicate's guard_type
    for guard in guards:
        # RFC-038: Guard.kind contains the guard type (e.g., "sanitizer", "escape")
        guard_kind = getattr(guard, "kind", None)

        if guard_kind == predicate.guard_type:
            # Guard matches! Check pattern if specified
            # For SanitizerGuard: sanitizer_name, for EscapeGuard: escape_method
            guard_pattern = (
                getattr(guard, "sanitizer_name", "")
                or getattr(guard, "escape_method", "")
                or getattr(guard, "pattern", "")
            )

            if predicate.guard_pattern and predicate.guard_pattern not in guard_pattern:
                # Pattern doesn't match, continue checking
                continue

            # Guard found!
            if predicate.effect == "block":
                # Guard blocks the match entirely
                return (False, 0.0)

            elif predicate.effect == "reduce_confidence":
                # Guard reduces confidence
                # Adjustment is negative (reduces confidence)
                adjustment = -(1.0 - predicate.confidence_multiplier)
                return (True, adjustment)

    # No matching guard found - proceed normally
    return (True, 0.0)


def _evaluate_value_constraint(
    constraint: ValueConstraintIR,
    entity: Entity,
    arg_index: int,
) -> tuple[bool, float]:
    """Evaluate value constraint.

    Args:
        constraint: Value constraint
        entity: Entity
        arg_index: Argument index

    Returns:
        (passed, confidence_adjustment)
    """
    if isinstance(constraint, IsConstIR):
        passed = entity.is_constant(arg_index)
        return (passed, 0.0)

    elif isinstance(constraint, IsNotConstIR):
        from trcr.config import DEFAULT_CONFIDENCE_CONFIG

        passed = not entity.is_constant(arg_index)
        adj = DEFAULT_CONFIDENCE_CONFIG.NOT_CONST_ADJUSTMENT if passed else 0.0
        return (passed, adj)

    elif isinstance(constraint, IsStringLikeIR):
        # Check if argument is string-like (str or bytes)
        # Note: is_string_literal checks constant + type, we just check type
        arg = entity.get_arg(arg_index)
        passed = isinstance(arg, (str, bytes))
        return (passed, 0.0)

    elif isinstance(constraint, IsIntLikeIR):
        arg = entity.get_arg(arg_index)
        passed = isinstance(arg, int)
        return (passed, 0.0)

    elif isinstance(constraint, MatchesRegexIR):
        # Regex matching against argument value
        import re

        arg = entity.get_arg(arg_index)
        if arg is None:
            return (False, 0.0)

        # Only match string arguments
        if not isinstance(arg, str):
            return (False, 0.0)

        try:
            pattern = re.compile(constraint.pattern)
            passed = bool(pattern.search(arg))
            return (passed, 0.0)
        except re.error:
            # Invalid regex pattern
            return (False, 0.0)

    elif isinstance(constraint, LengthBoundIR):
        # Length bound checking
        arg = entity.get_arg(arg_index)
        if arg is None:
            return (False, 0.0)

        # Get length of argument
        try:
            length = len(arg)
        except TypeError:
            # Argument doesn't support len()
            return (False, 0.0)

        # Check bounds
        if constraint.min_length is not None and length < constraint.min_length:
            return (False, 0.0)

        if constraint.max_length is not None and length > constraint.max_length:
            return (False, 0.0)

        return (True, 0.0)

    else:
        raise PredicateEvaluationError(f"Unknown constraint type: {type(constraint)}")
