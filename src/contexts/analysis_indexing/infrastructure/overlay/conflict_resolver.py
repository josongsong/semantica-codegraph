"""
Conflict Resolver

Resolves conflicts between base and overlay symbols.
"""

from src.common.observability import get_logger
from .models import SymbolConflict

logger = get_logger(__name__)


class ConflictResolver:
    """
    Resolve symbol conflicts

    Strategy: Overlay always wins (uncommitted changes have priority)

    This is the simplest and most intuitive strategy for developers:
    "What I'm editing right now is what I want to see in IDE/Agent."
    """

    def resolve(self, conflict: SymbolConflict) -> SymbolConflict:
        """
        Resolve conflict

        Current strategy: Overlay always wins

        Future: Could add more sophisticated strategies:
        - Prompt user for resolution
        - Smart merge based on change type
        - Configurable per-project
        """
        # Already resolved as "overlay_wins" by default
        conflict.resolution = "overlay_wins"

        logger.debug(
            "conflict_resolved",
            symbol_id=conflict.symbol_id,
            conflict_type=conflict.conflict_type,
            resolution=conflict.resolution,
            is_breaking=conflict.is_breaking_change(),
        )

        return conflict

    def assess_risk(self, conflicts: list[SymbolConflict]) -> str:
        """
        Assess risk level of conflicts

        Returns:
            "low", "medium", "high"
        """
        if not conflicts:
            return "low"

        breaking_changes = [c for c in conflicts if c.is_breaking_change()]

        if len(breaking_changes) > 5:
            return "high"
        elif len(breaking_changes) > 0:
            return "medium"
        else:
            return "low"

    def generate_warnings(self, conflicts: list[SymbolConflict]) -> list[str]:
        """
        Generate user-friendly warnings for conflicts

        Returns:
            List of warning messages
        """
        warnings = []

        for conflict in conflicts:
            if conflict.is_breaking_change():
                if conflict.conflict_type == "deletion":
                    warnings.append(
                        f"⚠️ Symbol '{conflict.symbol_id}' was deleted. This may break code that depends on it."
                    )
                elif conflict.conflict_type == "signature_change":
                    warnings.append(
                        f"⚠️ Signature of '{conflict.symbol_id}' changed: "
                        f"{conflict.base_signature} → {conflict.overlay_signature}. "
                        f"This may be a breaking change."
                    )

        return warnings
