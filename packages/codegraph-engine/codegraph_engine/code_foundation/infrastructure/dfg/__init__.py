"""
DFG (Data Flow Graph) - Deprecated/Stub

NOTE: DFG functionality has been migrated to Rust IR pipeline (codegraph-ir).
This module exists only for backward compatibility with legacy code.

For new code, use the Rust IR pipeline:
    import codegraph_ir
    orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
    result = orchestrator.execute()  # Returns DFG as part of L4 stage
"""

from codegraph_engine.code_foundation.infrastructure.dfg.models import DfgSnapshot

__all__ = ["DfgSnapshot"]
