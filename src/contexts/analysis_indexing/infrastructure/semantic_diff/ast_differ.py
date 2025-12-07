"""
AST Differ

Compares AST structures to detect semantic changes.
"""

from dataclasses import dataclass
from typing import Any

import structlog

from .models import (
    ChangeSeverity,
    ChangeType,
    DiffContext,
    SemanticChange,
    SemanticDiff,
)

logger = structlog.get_logger(__name__)


@dataclass
class ASTDiffer:
    """
    AST-level differ

    Detects structural changes by comparing AST:
    - Function signatures
    - Parameter lists
    - Return types
    - Class hierarchies

    Example:
        differ = ASTDiffer(context)
        diff = differ.compare_symbols("calculate_price", old_node, new_node)
    """

    context: DiffContext

    def compare_symbols(
        self,
        symbol_id: str,
        old_node: Any,
        new_node: Any,
    ) -> SemanticDiff:
        """
        Compare two symbol nodes

        Args:
            symbol_id: Symbol identifier
            old_node: Old AST node
            new_node: New AST node

        Returns:
            SemanticDiff with detected changes
        """
        diff = SemanticDiff()

        # Compare signatures
        sig_changes = self._compare_signatures(symbol_id, old_node, new_node)
        for change in sig_changes:
            diff.add_change(change)

        # Compare types
        type_changes = self._compare_types(symbol_id, old_node, new_node)
        for change in type_changes:
            diff.add_change(change)

        # Compare visibility
        vis_change = self._compare_visibility(symbol_id, old_node, new_node)
        if vis_change:
            diff.add_change(vis_change)

        return diff

    def _compare_signatures(
        self,
        symbol_id: str,
        old_node: Any,
        new_node: Any,
    ) -> list[SemanticChange]:
        """Compare function/method signatures"""
        changes = []

        old_sig = getattr(old_node, "signature", "")
        new_sig = getattr(new_node, "signature", "")

        if old_sig == new_sig:
            return changes

        # Parse signatures (simplified)
        old_params = self._parse_parameters(old_sig)
        new_params = self._parse_parameters(new_sig)

        # Parameters added
        added_params = set(new_params.keys()) - set(old_params.keys())
        for param in added_params:
            change = SemanticChange(
                change_type=ChangeType.PARAMETER_ADDED,
                severity=ChangeSeverity.MAJOR,  # May break positional calls
                file_path=getattr(old_node, "file", ""),
                symbol_id=symbol_id,
                description=f"Parameter '{param}' added",
                old_value=None,
                new_value=new_params[param],
            )
            changes.append(change)

        # Parameters removed
        removed_params = set(old_params.keys()) - set(new_params.keys())
        for param in removed_params:
            change = SemanticChange(
                change_type=ChangeType.PARAMETER_REMOVED,
                severity=ChangeSeverity.BREAKING,
                file_path=getattr(old_node, "file", ""),
                symbol_id=symbol_id,
                description=f"Parameter '{param}' removed",
                old_value=old_params[param],
                new_value=None,
            )
            changes.append(change)

        # Parameter types changed
        common_params = set(old_params.keys()) & set(new_params.keys())
        for param in common_params:
            if old_params[param] != new_params[param]:
                change = SemanticChange(
                    change_type=ChangeType.PARAMETER_TYPE_CHANGED,
                    severity=ChangeSeverity.MAJOR,
                    file_path=getattr(old_node, "file", ""),
                    symbol_id=symbol_id,
                    description=f"Parameter '{param}' type changed",
                    old_value=old_params[param],
                    new_value=new_params[param],
                )
                changes.append(change)

        # Return type changed
        old_return = self._parse_return_type(old_sig)
        new_return = self._parse_return_type(new_sig)

        if old_return != new_return:
            change = SemanticChange(
                change_type=ChangeType.RETURN_TYPE_CHANGED,
                severity=ChangeSeverity.MAJOR,
                file_path=getattr(old_node, "file", ""),
                symbol_id=symbol_id,
                description="Return type changed",
                old_value=old_return,
                new_value=new_return,
            )
            changes.append(change)

        return changes

    def _parse_parameters(self, signature: str) -> dict[str, str]:
        """Parse parameters from signature (simplified)"""
        params = {}

        # Extract params between parentheses
        if "(" not in signature or ")" not in signature:
            return params

        params_str = signature[signature.find("(") + 1 : signature.find(")")]

        if not params_str.strip():
            return params

        # Split by comma
        for param in params_str.split(","):
            param = param.strip()
            if not param:
                continue

            # Parse "name: type" or "name"
            if ":" in param:
                name, type_hint = param.split(":", 1)
                name = name.strip()
                type_hint = type_hint.strip()
                # Remove default value if present
                if "=" in type_hint:
                    type_hint = type_hint.split("=")[0].strip()
                params[name] = type_hint
            else:
                # No type hint
                name = param.split("=")[0].strip()
                params[name] = "Any"

        return params

    def _parse_return_type(self, signature: str) -> str | None:
        """Parse return type from signature"""
        if "->" not in signature:
            return None

        return_part = signature.split("->")[-1].strip()
        # Remove trailing colon if present
        return_part = return_part.rstrip(":")
        return return_part

    def _compare_types(
        self,
        symbol_id: str,
        old_node: Any,
        new_node: Any,
    ) -> list[SemanticChange]:
        """Compare type annotations"""
        changes = []

        # Get type info (if available)
        old_type = getattr(old_node, "type_annotation", None)
        new_type = getattr(new_node, "type_annotation", None)

        if old_type != new_type and old_type is not None and new_type is not None:
            change = SemanticChange(
                change_type=ChangeType.PARAMETER_TYPE_CHANGED,
                severity=ChangeSeverity.MODERATE,
                file_path=getattr(old_node, "file", ""),
                symbol_id=symbol_id,
                description="Type annotation changed",
                old_value=old_type,
                new_value=new_type,
            )
            changes.append(change)

        return changes

    def _compare_visibility(
        self,
        symbol_id: str,
        old_node: Any,
        new_node: Any,
    ) -> SemanticChange | None:
        """Compare visibility (public/private)"""
        old_name = getattr(old_node, "name", "")
        new_name = getattr(new_node, "name", "")

        old_private = old_name.startswith("_")
        new_private = new_name.startswith("_")

        if old_private != new_private:
            return SemanticChange(
                change_type=ChangeType.VISIBILITY_CHANGED,
                severity=ChangeSeverity.MAJOR if not old_private else ChangeSeverity.MODERATE,
                file_path=getattr(old_node, "file", ""),
                symbol_id=symbol_id,
                description=f"Visibility changed: {'private' if new_private else 'public'}",
                old_value="private" if old_private else "public",
                new_value="private" if new_private else "public",
            )

        return None

    def __repr__(self) -> str:
        return f"ASTDiffer(context={self.context})"
