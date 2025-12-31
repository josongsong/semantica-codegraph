"""
DFG Models - Deprecated/Stub

NOTE: DFG functionality has been migrated to Rust IR pipeline.
This is a minimal stub for backward compatibility.
"""

from dataclasses import dataclass, field


@dataclass
class DfgSnapshot:
    """
    Data Flow Graph Snapshot (Stub for backward compatibility).

    DEPRECATED: Use Rust IR pipeline (codegraph_ir.IRIndexingOrchestrator)
    which provides DFG as part of L4 stage output.

    This stub allows existing code to import and use DfgSnapshot
    without errors during migration to Rust-based analysis.
    """

    variables: list = field(default_factory=list)
    edges: list = field(default_factory=list)

    # Compatibility fields for legacy code
    definitions: dict = field(default_factory=dict)
    uses: dict = field(default_factory=dict)

    def __post_init__(self):
        """Log deprecation warning on first use."""
        import logging

        logger = logging.getLogger(__name__)
        logger.debug("DfgSnapshot is deprecated. Use Rust IR pipeline (codegraph_ir) for DFG analysis.")
