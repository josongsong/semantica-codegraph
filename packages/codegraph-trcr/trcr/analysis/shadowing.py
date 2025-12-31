"""Shadowing Analysis - RFC-035.

Build-time detection of rule shadowing and conflicts.

Key Concepts:
    - Shadowing: A more general rule makes a specific rule unreachable
    - Subsumption: Pattern A subsumes B if A matches everything B matches
    - Dead Rule: A rule that can never match due to shadowing

Usage:
    >>> analyzer = ShadowingAnalyzer()
    >>> warnings = analyzer.analyze(compiled_rules)
    >>> for w in warnings:
    ...     print(f"{w.shadowed_rule} shadowed by {w.shadowing_rule}")

RFC-035 Goals:
    1. Detect dead rules at build time
    2. Warn about specificity inversions
    3. Identify redundant rules
    4. NO build failures (warnings only)
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from trcr.analysis.patterns import compute_overlap_percentage, pattern_subsumes
from trcr.ir.executable import TaintRuleExecutableIR

logger = logging.getLogger(__name__)


@dataclass
class ShadowWarning:
    """Warning about rule shadowing.

    RFC-035: Build-time shadowing detection.

    Attributes:
        shadowed_rule: The rule being shadowed (more specific)
        shadowing_rule: The rule doing the shadowing (more general)
        severity: INFO, WARNING, or ERROR
        recommendation: How to fix
        overlap_percentage: How much overlap [0.0, 1.0]
        pattern_a: Pattern of shadowing rule
        pattern_b: Pattern of shadowed rule
    """

    shadowed_rule: str  # Rule being shadowed (victim)
    shadowing_rule: str  # Rule doing shadowing (aggressor)
    severity: Literal["INFO", "WARNING", "ERROR"]
    recommendation: str
    overlap_percentage: float  # 0.0-1.0

    # Pattern details for debugging
    pattern_a: str = ""  # Shadowing pattern
    pattern_b: str = ""  # Shadowed pattern

    def __str__(self) -> str:
        """Human-readable warning."""
        return (
            f"[{self.severity}] Rule '{self.shadowed_rule}' shadowed by '{self.shadowing_rule}' "
            f"({self.overlap_percentage:.0%} overlap). {self.recommendation}"
        )


@dataclass
class ShadowingReport:
    """Complete shadowing analysis report.

    Contains all warnings plus summary statistics.
    """

    warnings: list[ShadowWarning] = field(default_factory=list)
    rules_analyzed: int = 0
    pairs_checked: int = 0
    dead_rules: list[str] = field(default_factory=list)
    redundant_rules: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        """Check if any issues found."""
        return len(self.warnings) > 0

    @property
    def error_count(self) -> int:
        """Count ERROR severity warnings."""
        return sum(1 for w in self.warnings if w.severity == "ERROR")

    @property
    def warning_count(self) -> int:
        """Count WARNING severity warnings."""
        return sum(1 for w in self.warnings if w.severity == "WARNING")

    def summary(self) -> str:
        """Generate summary string."""
        return (
            f"Shadowing Analysis: {self.rules_analyzed} rules, "
            f"{self.pairs_checked} pairs checked, "
            f"{len(self.warnings)} issues "
            f"({self.error_count} errors, {self.warning_count} warnings)"
        )


class ShadowingAnalyzer:
    """Analyzer for rule shadowing detection.

    RFC-035: Build-time shadowing analysis.

    Algorithm:
        1. Group rules by call family (same call name)
        2. Sort by specificity (more specific first)
        3. For each pair, check subsumption
        4. Generate warnings (no build failures)

    Thresholds:
        - ERROR: 100% overlap (complete shadowing)
        - WARNING: 80-99% overlap (significant shadowing)
        - INFO: 50-79% overlap (partial overlap)

    Example:
        >>> analyzer = ShadowingAnalyzer()
        >>> rules = compiler.compile_specs(specs)
        >>> report = analyzer.analyze(rules)
        >>> for w in report.warnings:
        ...     logger.warning(str(w))
    """

    def __init__(
        self,
        overlap_warning_threshold: float = 0.8,
        overlap_info_threshold: float = 0.5,
    ) -> None:
        """Initialize analyzer.

        Args:
            overlap_warning_threshold: Minimum overlap for WARNING
            overlap_info_threshold: Minimum overlap for INFO
        """
        self.overlap_warning_threshold = overlap_warning_threshold
        self.overlap_info_threshold = overlap_info_threshold

    def analyze(self, rules: list[TaintRuleExecutableIR]) -> ShadowingReport:
        """Analyze rules for shadowing.

        Args:
            rules: Compiled executable rules

        Returns:
            ShadowingReport with all warnings
        """
        report = ShadowingReport(rules_analyzed=len(rules))

        if len(rules) < 2:
            return report

        # Group by call family
        families = self._group_by_call_family(rules)

        # Analyze each family
        for _call_key, family_rules in families.items():
            if len(family_rules) < 2:
                continue

            # Sort by specificity (highest first)
            sorted_rules = sorted(family_rules)

            # Check each pair
            for i, rule_a in enumerate(sorted_rules):
                for rule_b in sorted_rules[i + 1 :]:
                    report.pairs_checked += 1
                    warning = self._check_shadowing(rule_a, rule_b)
                    if warning:
                        report.warnings.append(warning)

                        # Track dead rules
                        if warning.overlap_percentage >= 1.0:
                            if warning.shadowed_rule not in report.dead_rules:
                                report.dead_rules.append(warning.shadowed_rule)

        # Identify redundant rules (same pattern, same effect)
        report.redundant_rules = self._find_redundant_rules(rules)

        logger.info(report.summary())
        return report

    def _group_by_call_family(self, rules: list[TaintRuleExecutableIR]) -> dict[str, list[TaintRuleExecutableIR]]:
        """Group rules by call name family.

        Rules with same base call name are in same family.

        Args:
            rules: All rules

        Returns:
            Dict mapping call key to rules
        """
        families: dict[str, list[TaintRuleExecutableIR]] = defaultdict(list)

        for rule in rules:
            # Extract call pattern from generator
            call_pattern = self._extract_call_pattern(rule)
            if call_pattern:
                # Normalize to family key
                family_key = self._get_family_key(call_pattern)
                families[family_key].append(rule)

        return families

    def _extract_call_pattern(self, rule: TaintRuleExecutableIR) -> str | None:
        """Extract call pattern from rule's generator.

        Args:
            rule: Compiled rule

        Returns:
            Call pattern string or None
        """
        # Get from generator plan
        generators = rule.generator_exec.candidate_plan.generators
        if not generators:
            return None

        # Use first generator's match_spec
        gen = generators[0]
        if hasattr(gen, "match_spec"):
            spec = gen.match_spec
            if hasattr(spec, "call"):
                return spec.call

        return None

    def _get_family_key(self, call_pattern: str) -> str:
        """Get family key from call pattern.

        Strips wildcards to get base family.

        Args:
            call_pattern: Call pattern (e.g., "execute", "execute*")

        Returns:
            Family key (e.g., "execute")
        """
        # Remove wildcards
        return call_pattern.replace("*", "").replace("?", "").strip(".")

    def _check_shadowing(self, rule_a: TaintRuleExecutableIR, rule_b: TaintRuleExecutableIR) -> ShadowWarning | None:
        """Check if rule_a shadows rule_b.

        rule_a should be higher specificity (checked first).
        If rule_a matches everything rule_b matches, rule_b is shadowed.

        Args:
            rule_a: Higher specificity rule
            rule_b: Lower specificity rule

        Returns:
            ShadowWarning if shadowing detected, None otherwise
        """
        pattern_a = self._get_full_pattern(rule_a)
        pattern_b = self._get_full_pattern(rule_b)

        if not pattern_a or not pattern_b:
            return None

        # Check if rule_a (higher specificity) subsumes rule_b (lower specificity)
        # This would be a specificity inversion problem
        if pattern_subsumes(pattern_a, pattern_b):
            # Higher specificity rule subsumes lower specificity - inversion!
            overlap = compute_overlap_percentage(pattern_a, pattern_b)

            severity = self._get_severity(overlap)
            if severity is None:
                return None

            return ShadowWarning(
                shadowed_rule=rule_b.rule_id,
                shadowing_rule=rule_a.rule_id,
                severity=severity,
                recommendation=self._get_recommendation(overlap, rule_a, rule_b),
                overlap_percentage=overlap,
                pattern_a=pattern_a,
                pattern_b=pattern_b,
            )

        # Also check reverse: lower specificity shadows higher
        # This is the more common case
        if pattern_subsumes(pattern_b, pattern_a):
            overlap = compute_overlap_percentage(pattern_b, pattern_a)

            if overlap < self.overlap_info_threshold:
                return None

            severity = self._get_severity(overlap)
            if severity is None:
                return None

            return ShadowWarning(
                shadowed_rule=rule_a.rule_id,
                shadowing_rule=rule_b.rule_id,
                severity=severity,
                recommendation=self._get_recommendation(overlap, rule_b, rule_a),
                overlap_percentage=overlap,
                pattern_a=pattern_b,
                pattern_b=pattern_a,
            )

        return None

    def _get_full_pattern(self, rule: TaintRuleExecutableIR) -> str | None:
        """Get full pattern string for a rule.

        Combines type and call patterns.

        Args:
            rule: Compiled rule

        Returns:
            Full pattern string or None
        """
        generators = rule.generator_exec.candidate_plan.generators
        if not generators:
            return None

        gen = generators[0]
        if hasattr(gen, "match_spec"):
            spec = gen.match_spec
            type_pat = getattr(spec, "base_type", "*")
            call_pat = getattr(spec, "call", "*")
            return f"{type_pat}.{call_pat}"

        return None

    def _get_severity(self, overlap: float) -> Literal["INFO", "WARNING", "ERROR"] | None:
        """Determine severity based on overlap percentage.

        Args:
            overlap: Overlap percentage [0.0, 1.0]

        Returns:
            Severity level or None if below threshold
        """
        if overlap >= 1.0:
            return "ERROR"
        elif overlap >= self.overlap_warning_threshold:
            return "WARNING"
        elif overlap >= self.overlap_info_threshold:
            return "INFO"
        return None

    def _get_recommendation(
        self,
        overlap: float,
        shadowing_rule: TaintRuleExecutableIR,
        shadowed_rule: TaintRuleExecutableIR,
    ) -> str:
        """Generate recommendation for fixing shadowing.

        Args:
            overlap: Overlap percentage
            shadowing_rule: Rule doing the shadowing
            shadowed_rule: Rule being shadowed

        Returns:
            Recommendation string
        """
        if overlap >= 1.0:
            return f"Consider removing '{shadowed_rule.rule_id}' (completely shadowed)"

        if overlap >= 0.9:
            return f"Consider merging '{shadowed_rule.rule_id}' into '{shadowing_rule.rule_id}' (90%+ overlap)"

        if overlap >= 0.8:
            return f"Review specificity of '{shadowed_rule.rule_id}' - may be partially redundant"

        return "Review pattern overlap and consider refactoring"

    def _find_redundant_rules(self, rules: list[TaintRuleExecutableIR]) -> list[str]:
        """Find rules that are redundant (same pattern AND effect).

        Args:
            rules: All rules

        Returns:
            List of redundant rule IDs
        """
        redundant: list[str] = []
        seen: dict[str, str] = {}  # pattern+effect -> first rule_id

        for rule in rules:
            pattern = self._get_full_pattern(rule)
            effect_key = f"{rule.effect.kind}:{','.join(map(str, rule.effect.arg_positions))}"
            key = f"{pattern}|{effect_key}"

            if key in seen:
                redundant.append(rule.rule_id)
                logger.debug(f"Redundant rule: {rule.rule_id} duplicates {seen[key]}")
            else:
                seen[key] = rule.rule_id

        return redundant


# Convenience function
def analyze_shadowing(rules: list[TaintRuleExecutableIR]) -> ShadowingReport:
    """Analyze rules for shadowing (convenience function).

    Args:
        rules: Compiled executable rules

    Returns:
        ShadowingReport
    """
    analyzer = ShadowingAnalyzer()
    return analyzer.analyze(rules)
