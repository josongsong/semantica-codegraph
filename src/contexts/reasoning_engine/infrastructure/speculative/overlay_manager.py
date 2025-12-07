"""
OverlayManager - Multi-patch Stack Management

여러 패치를 스택으로 관리하고 rollback 지원
"""

import logging
import time
from collections import deque
from typing import Any

from ...domain.speculative_models import RiskReport, SpeculativePatch
from .delta_graph import DeltaGraph
from .exceptions import SimulationError
from .graph_simulator import GraphSimulator
from .risk_analyzer import RiskAnalyzer

logger = logging.getLogger(__name__)


class PatchLayer:
    """Single patch layer in the stack"""

    def __init__(self, patch: SpeculativePatch, delta_graph: DeltaGraph, risk: RiskReport):
        self.patch = patch
        self.delta_graph = delta_graph
        self.risk = risk
        self.timestamp = time.time()

    def __repr__(self) -> str:
        return f"PatchLayer(patch={self.patch.patch_id}, risk={self.risk.risk_level.name})"


class OverlayManager:
    """
    Multi-patch stack manager

    Manages stack of speculative patches with rollback support

    Example:
        manager = OverlayManager(base_graph)

        # Apply patches
        manager.apply_patch(patch1)
        manager.apply_patch(patch2)

        # Check risk
        if manager.current_risk().is_breaking():
            manager.rollback(1)

        # Get current state
        current = manager.current_graph()
    """

    def __init__(self, base_graph: Any, max_stack_depth: int = 100, auto_reject_breaking: bool = False):
        """
        Initialize OverlayManager

        Args:
            base_graph: Base graph (immutable)
            max_stack_depth: Max patch stack depth
            auto_reject_breaking: Auto-reject BREAKING patches
        """
        if base_graph is None:
            raise SimulationError("Base graph cannot be None")

        self.base = base_graph
        self.max_stack_depth = max_stack_depth
        self.auto_reject_breaking = auto_reject_breaking

        self._stack: deque[PatchLayer] = deque()
        self._current_delta: DeltaGraph | None = None

        self._simulator = GraphSimulator(base_graph)
        self._analyzer = RiskAnalyzer()

        self._total_patches_applied = 0
        self._total_patches_rejected = 0
        self._total_rollbacks = 0

        logger.info(f"OverlayManager initialized: max_depth={max_stack_depth}, auto_reject={auto_reject_breaking}")

    def apply_patch(self, patch: SpeculativePatch, force: bool = False) -> bool:
        """
        Apply patch to stack

        Args:
            patch: Speculative patch
            force: Force apply even if risky

        Returns:
            True if applied, False if rejected

        Raises:
            SimulationError: Stack overflow or simulation error
        """
        if len(self._stack) >= self.max_stack_depth:
            raise SimulationError(f"Stack overflow: {len(self._stack)} >= {self.max_stack_depth}")

        try:
            # Simulate on current state
            current = self.current_graph()
            delta_graph = self._simulator.simulate_patch(patch)

            # Analyze risk
            risk = self._analyzer.analyze_risk(patch, delta_graph, current)

            # Rejection logic
            if not force:
                if self.auto_reject_breaking and risk.is_breaking():
                    logger.warning(f"Auto-rejected BREAKING patch: {patch.patch_id}")
                    self._total_patches_rejected += 1
                    return False

            # Create layer
            layer = PatchLayer(patch, delta_graph, risk)

            # Push to stack
            self._stack.append(layer)
            self._current_delta = delta_graph
            self._total_patches_applied += 1

            logger.info(f"Applied patch {patch.patch_id}: risk={risk.risk_level.name}, stack_depth={len(self._stack)}")

            return True

        except Exception as e:
            logger.error(f"Failed to apply patch {patch.patch_id}: {e}")
            raise SimulationError(f"Apply failed: {e}")

    def apply_patches(self, patches: list[SpeculativePatch], stop_on_breaking: bool = True) -> int:
        """
        Apply multiple patches

        Args:
            patches: List of patches
            stop_on_breaking: Stop if BREAKING encountered

        Returns:
            Number of patches applied
        """
        applied_count = 0

        for i, patch in enumerate(patches):
            try:
                success = self.apply_patch(patch)

                if success:
                    applied_count += 1

                    # Check if breaking
                    if stop_on_breaking:
                        current_risk = self.current_risk()
                        if current_risk and current_risk.is_breaking():
                            logger.warning(f"Stopped at patch {i + 1}/{len(patches)}: BREAKING")
                            break
                else:
                    # Rejected
                    if stop_on_breaking:
                        break

            except Exception as e:
                logger.error(f"Failed at patch {i + 1}/{len(patches)}: {e}")
                break

        logger.info(f"Applied {applied_count}/{len(patches)} patches")
        return applied_count

    def rollback(self, steps: int = 1) -> int:
        """
        Rollback patches

        Args:
            steps: Number of patches to rollback

        Returns:
            Actual number of steps rolled back
        """
        actual_steps = min(steps, len(self._stack))

        for _ in range(actual_steps):
            if self._stack:
                layer = self._stack.pop()
                logger.debug(f"Rolled back patch: {layer.patch.patch_id}")

        # Update current delta
        if self._stack:
            self._current_delta = self._stack[-1].delta_graph
        else:
            self._current_delta = None

        self._total_rollbacks += actual_steps

        logger.info(f"Rolled back {actual_steps} patch(es), depth={len(self._stack)}")
        return actual_steps

    def rollback_to_safe(self) -> int:
        """
        Rollback until SAFE state

        Returns:
            Number of patches rolled back
        """
        rollback_count = 0

        while self._stack:
            current_risk = self.current_risk()
            if current_risk and current_risk.is_safe():
                break

            self.rollback(1)
            rollback_count += 1

        logger.info(f"Rolled back to safe: {rollback_count} patches")
        return rollback_count

    def current_graph(self) -> Any:
        """Current graph state (base or delta)"""
        if self._current_delta:
            return self._current_delta
        return self.base

    def current_risk(self) -> RiskReport | None:
        """Current risk report"""
        if self._stack:
            return self._stack[-1].risk
        return None

    def current_patch(self) -> SpeculativePatch | None:
        """Current patch"""
        if self._stack:
            return self._stack[-1].patch
        return None

    def stack_depth(self) -> int:
        """Current stack depth"""
        return len(self._stack)

    def is_empty(self) -> bool:
        """Is stack empty?"""
        return len(self._stack) == 0

    def clear(self) -> None:
        """Clear all patches"""
        cleared = len(self._stack)
        self._stack.clear()
        self._current_delta = None
        logger.info(f"Cleared {cleared} patch(es)")

    def get_all_patches(self) -> list[SpeculativePatch]:
        """Get all patches in stack"""
        return [layer.patch for layer in self._stack]

    def get_all_risks(self) -> list[RiskReport]:
        """Get all risk reports"""
        return [layer.risk for layer in self._stack]

    def get_patch_history(self) -> list[dict[str, Any]]:
        """
        Get patch application history

        Returns:
            List of {patch_id, risk_level, timestamp}
        """
        return [
            {
                "patch_id": layer.patch.patch_id,
                "risk_level": layer.risk.risk_level.name,
                "risk_score": layer.risk.risk_score,
                "timestamp": layer.timestamp,
            }
            for layer in self._stack
        ]

    def stats(self) -> dict[str, Any]:
        """Manager statistics"""
        return {
            "stack_depth": len(self._stack),
            "total_applied": self._total_patches_applied,
            "total_rejected": self._total_patches_rejected,
            "total_rollbacks": self._total_rollbacks,
            "current_risk": self.current_risk().risk_level.name if self.current_risk() else "NONE",
        }

    def __repr__(self) -> str:
        return (
            f"OverlayManager("
            f"depth={len(self._stack)}/{self.max_stack_depth}, "
            f"applied={self._total_patches_applied}, "
            f"rejected={self._total_patches_rejected})"
        )
