"""
IR Generators (Internal)

⚠️ WARNING: Do NOT use these generators directly!
Use LayeredIRBuilder instead for full 9-layer IR construction.

These generators only provide Layer 1 (Structural IR).
Direct usage will miss:
- Layer 2: Occurrence (SCIP-compatible)
- Layer 3: LSP Type Enrichment
- Layer 4: Cross-file Resolution
- Layer 5: Semantic IR (CFG/DFG/BFG)
- Layer 6: Advanced Analysis (PDG/Taint)
- Layer 7: Retrieval Indexes
- Layer 8: Diagnostics
- Layer 9: Package Analysis

Correct usage:
    from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder

    builder = LayeredIRBuilder(project_root)
    ir_docs, ctx, idx, diag, pkg = await builder.build_full(files)

Internal usage only (within LayeredIRBuilder):
    from codegraph_engine.code_foundation.infrastructure.generators import _PythonIRGenerator
"""

from codegraph_engine.code_foundation.infrastructure.generators.base import IRGenerator

# Internal generators (prefixed with _ to indicate private)
# Only LayeredIRBuilder should use these directly
from codegraph_engine.code_foundation.infrastructure.generators.java_generator import (
    _JavaIRGenerator,
)
from codegraph_engine.code_foundation.infrastructure.generators.python_generator import (
    _PythonIRGenerator,
)
from codegraph_engine.code_foundation.infrastructure.generators.scope_stack import ScopeStack
from codegraph_engine.code_foundation.infrastructure.generators.typescript_generator import (
    _TypeScriptIRGenerator,
)

__all__ = [
    # Public API
    "IRGenerator",  # Base class (for type hints)
    "ScopeStack",  # Utility (used by generators)
    # Internal (_ prefix = do not use directly)
    "_PythonIRGenerator",
    "_JavaIRGenerator",
    "_TypeScriptIRGenerator",
]
