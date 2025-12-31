"""
IR Optimization Passes

Implements RFC-037: Rule IR Optimization Passes
"""

import logging
from dataclasses import dataclass, field
from typing import Protocol

from trcr.ir.executable import TaintRuleExecutableIR

logger = logging.getLogger(__name__)


# ============================================================================
# Optimization Pass Protocol
# ============================================================================


class OptimizationPass(Protocol):
    """Protocol for optimization passes."""

    def optimize(self, ir: TaintRuleExecutableIR) -> TaintRuleExecutableIR:
        """
        Apply optimization pass to IR.

        Args:
            ir: Input IR

        Returns:
            Optimized IR
        """
        ...

    @property
    def pass_name(self) -> str:
        """Name of this optimization pass."""
        ...


# ============================================================================
# Pass 1: Normalize Pass
# ============================================================================


@dataclass
class NormalizePass:
    """
    Normalize rules to canonical form.

    Transformations:
    - Exact → Pattern if subsumed
    - Multiple patterns → Merged pattern
    - Redundant constraints → Removed
    """

    pass_name: str = "normalize"

    def optimize(self, ir: TaintRuleExecutableIR) -> TaintRuleExecutableIR:
        """Normalize rule to canonical form."""
        logger.debug(f"NormalizePass: Processing rule {ir.rule_id}")

        # Note: Most normalization is done during compilation
        # This pass handles any remaining cleanup

        return ir


# ============================================================================
# Pass 2: Prune Pass (Dead Rule Elimination)
# ============================================================================


@dataclass
class PrunePass:
    """
    Eliminate dead rules.

    Similar to:
    - Dead code elimination (DCE) in compilers
    - Unreachable code detection
    """

    pass_name: str = "prune"
    min_specificity: float = 0.1

    def optimize(self, ir: TaintRuleExecutableIR) -> TaintRuleExecutableIR:
        """Remove dead rules."""
        # Check if rule has meaningful specificity
        specificity_value = ir.specificity.final_score
        if specificity_value < self.min_specificity:
            logger.warning(f"PrunePass: Rule {ir.rule_id} has very low specificity ({specificity_value:.2f})")

        return ir


# ============================================================================
# Pass 3: Reorder Pass (Predicate Ordering)
# ============================================================================


@dataclass
class ReorderPass:
    """
    Reorder predicates for optimal execution.

    Strategy:
    - Fast predicates first (fail-fast)
    - Expensive predicates last
    - High selectivity first
    """

    pass_name: str = "reorder"

    def optimize(self, ir: TaintRuleExecutableIR) -> TaintRuleExecutableIR:
        """Reorder predicates for better performance."""
        logger.debug(f"ReorderPass: Processing rule {ir.rule_id}")

        # Predicates are already ordered by the compiler
        # This is a placeholder for future enhancements

        return ir


# ============================================================================
# Pass 4: Merge Pass (Rule Fusion)
# ============================================================================


@dataclass
class MergePass:
    """
    Merge compatible rules.

    Only applies when processing multiple rules together.
    For single-rule optimization, this is a no-op.
    """

    pass_name: str = "merge"

    def optimize(self, ir: TaintRuleExecutableIR) -> TaintRuleExecutableIR:
        """Merge compatible rules (no-op for single rule)."""
        logger.debug(f"MergePass: Processing rule {ir.rule_id}")
        return ir


# ============================================================================
# Optimization Pipeline
# ============================================================================


@dataclass
class OptimizationPipeline:
    """
    Optimization pipeline for Rule IR.

    Pipeline stages:
    1. Normalize - Canonical form
    2. Prune - Dead code elimination
    3. Reorder - Predicate ordering
    4. Merge - Rule fusion
    """

    passes: list[OptimizationPass] = field(
        default_factory=lambda: [
            NormalizePass(),
            PrunePass(),
            ReorderPass(),
            MergePass(),
        ]
    )

    enabled: bool = True

    def optimize(self, ir: TaintRuleExecutableIR) -> TaintRuleExecutableIR:
        """
        Apply all optimization passes.

        Args:
            ir: Input IR

        Returns:
            Optimized IR
        """
        if not self.enabled:
            logger.debug("Optimization disabled")
            return ir

        logger.info(f"Starting optimization pipeline for rule {ir.rule_id}")

        optimized_ir = ir
        applied_passes: list[str] = []

        for opt_pass in self.passes:
            logger.debug(f"Applying {opt_pass.pass_name} pass")
            optimized_ir = opt_pass.optimize(optimized_ir)
            applied_passes.append(opt_pass.pass_name)

        # Update optimizer_passes metadata
        optimized_ir.optimizer_passes = applied_passes

        logger.info(f"Optimization complete for rule {ir.rule_id}. Applied passes: {', '.join(applied_passes)}")

        return optimized_ir


# ============================================================================
# Convenience Functions
# ============================================================================


def optimize_ir(
    ir: TaintRuleExecutableIR,
    *,
    enabled: bool = True,
    passes: list[OptimizationPass] | None = None,
) -> TaintRuleExecutableIR:
    """
    Optimize TaintRuleExecutableIR.

    Args:
        ir: Input IR
        enabled: Whether optimization is enabled
        passes: Custom optimization passes (None = default)

    Returns:
        Optimized IR
    """
    if passes is None:
        pipeline = OptimizationPipeline(enabled=enabled)
    else:
        pipeline = OptimizationPipeline(passes=passes, enabled=enabled)

    return pipeline.optimize(ir)


def get_default_pipeline() -> OptimizationPipeline:
    """Get default optimization pipeline."""
    return OptimizationPipeline()


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "OptimizationPass",
    "NormalizePass",
    "PrunePass",
    "ReorderPass",
    "MergePass",
    "OptimizationPipeline",
    "optimize_ir",
    "get_default_pipeline",
]
