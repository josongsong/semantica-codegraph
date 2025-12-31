"""
Adapters for security analysis

기존 시스템을 새로운 인터페이스와 연결하는 어댑터들

NOTE: Security analysis is now fully handled by Rust (codegraph-ir).
Python only provides thin API wrappers for querying results.
"""

# DEPRECATED: TaintAnalyzerAdapter removed (Week 2 cleanup)
# from codegraph_analysis.security_analysis.infrastructure.adapters.taint_analyzer_adapter import (
#     TaintAnalyzerAdapter,
# )

from codegraph_analysis.security_analysis.infrastructure.adapters.rust_taint_adapter import (
    RustTaintAdapter,
    RustTaintBatchAnalyzer,
)
from codegraph_analysis.security_analysis.infrastructure.adapters.e2e_taint_wrapper import (
    E2ETaintAnalyzer,
)

__all__ = [
    # "TaintAnalyzerAdapter",  # DEPRECATED
    "RustTaintAdapter",
    "RustTaintBatchAnalyzer",
    "E2ETaintAnalyzer",  # E2E Pipeline wrapper (recommended)
]
