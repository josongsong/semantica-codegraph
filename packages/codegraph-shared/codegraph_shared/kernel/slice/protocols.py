"""
Slice Protocols - Interface Definitions

Purpose: Define contracts for slicers without implementation
"""

from typing import Protocol

from .models import SliceConfig, SliceResult


class SlicerPort(Protocol):
    """
    Program Slicer Protocol.

    Implementations:
    - reasoning_engine.infrastructure.slicer.slicer.ProgramSlicer
    """

    def backward_slice(self, target_node: str, config: SliceConfig | None = None) -> SliceResult:
        """Backward slice from target node"""
        ...

    def forward_slice(self, target_node: str, config: SliceConfig | None = None) -> SliceResult:
        """Forward slice from target node"""
        ...

    def hybrid_slice(self, target_node: str, config: SliceConfig | None = None) -> SliceResult:
        """Hybrid (backward + forward) slice"""
        ...
