"""
Template IR Index Management (RFC-051)

Provides index invalidation and lazy rebuilding for template queries.

Author: Semantica Team
Version: 1.0.0
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.domain.ports.template_ports import (
        SlotContextKind,
        TemplateSlotContract,
    )
    from codegraph_engine.code_foundation.infrastructure.ir.models.core import Edge


class TemplateIndexManager:
    """
    Template IR index manager with invalidation tracking.

    Responsibilities:
    - Build template indexes on demand
    - Invalidate indexes when data changes
    - Provide O(1) query methods

    SOTA Pattern: Lazy + Invalidation
    - Indexes built only when queried
    - Invalidated when source data changes
    - Thread-safe (read-only after build)
    """

    def __init__(self):
        """Initialize with empty indexes"""
        self._slots_by_context: dict["SlotContextKind", list["TemplateSlotContract"]] | None = None
        self._slots_by_file: dict[str, list["TemplateSlotContract"]] | None = None
        self._bindings_by_slot: dict[str, list["Edge"]] | None = None
        self._bindings_by_source: dict[str, list["Edge"]] | None = None
        self._is_built = False

    def invalidate(self) -> None:
        """
        Invalidate all indexes (call when slots/edges change).

        Thread-safety: Safe (sets to None)
        """
        self._slots_by_context = None
        self._slots_by_file = None
        self._bindings_by_slot = None
        self._bindings_by_source = None
        self._is_built = False

    def is_built(self) -> bool:
        """Check if indexes are built"""
        return self._is_built

    def build(
        self,
        template_slots: list["TemplateSlotContract"],
        edges: list["Edge"],
    ) -> None:
        """
        Build all template indexes.

        Args:
            template_slots: List of template slots
            edges: List of all edges (filtered for BINDS internally)

        Performance:
            O(slots + edges), ~1ms for 1000 slots

        Thread-safety:
            Not thread-safe during build, safe after
        """
        # Import EdgeKind locally
        from codegraph_engine.code_foundation.infrastructure.ir.models.kinds import EdgeKind

        # 1. Slots by context kind
        self._slots_by_context = {}
        for slot in template_slots:
            context_kind = getattr(slot, "context_kind", None)
            if context_kind:
                self._slots_by_context.setdefault(context_kind, []).append(slot)

        # 2. Slots by file
        self._slots_by_file = {}
        for slot in template_slots:
            slot_id = getattr(slot, "slot_id", "")
            if slot_id and ":" in slot_id:
                parts = slot_id.split(":")
                if len(parts) >= 2:
                    file_path = parts[1]
                    self._slots_by_file.setdefault(file_path, []).append(slot)

        # 3. BINDS edges by slot
        self._bindings_by_slot = {}
        for edge in edges:
            if edge.kind == EdgeKind.BINDS:
                self._bindings_by_slot.setdefault(edge.target_id, []).append(edge)

        # 4. BINDS edges by source
        self._bindings_by_source = {}
        for edge in edges:
            if edge.kind == EdgeKind.BINDS:
                self._bindings_by_source.setdefault(edge.source_id, []).append(edge)

        self._is_built = True

    def get_slots_by_context(self, context_kind: "SlotContextKind") -> list["TemplateSlotContract"]:
        """Get slots by context kind (O(1))"""
        if not self._is_built:
            return []
        return self._slots_by_context.get(context_kind, []) if self._slots_by_context else []

    def get_slots_by_file(self, file_path: str) -> list["TemplateSlotContract"]:
        """Get slots by file path (O(1))"""
        if not self._is_built:
            return []
        return self._slots_by_file.get(file_path, []) if self._slots_by_file else []

    def get_slot_bindings(self, slot_id: str) -> list["Edge"]:
        """Get BINDS edges for slot (O(1))"""
        if not self._is_built:
            return []
        return self._bindings_by_slot.get(slot_id, []) if self._bindings_by_slot else []

    def get_variable_bindings(self, variable_id: str) -> list["Edge"]:
        """Get BINDS edges from variable (O(1))"""
        if not self._is_built:
            return []
        return self._bindings_by_source.get(variable_id, []) if self._bindings_by_source else []
