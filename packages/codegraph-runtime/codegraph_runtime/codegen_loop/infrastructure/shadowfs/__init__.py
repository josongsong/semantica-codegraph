"""
ShadowFS Infrastructure

Implementation of ShadowFS (RFC-016 v2.0).

Modules:
    - errors: Exception types
    - core: ShadowFSCore (Part A)
    - ir_transaction: IRTransactionManager (Part B)
    - unified: UnifiedShadowFS (Part C)
    - path_canonicalizer: Path normalization
    - detectors: Generated/LFS file detection
    - safety: Atomic operations
"""

from .core import ShadowFSCore
from .detectors import GeneratedFileDetector, GitLFSDetector
from .errors import (
    CyclicSymlinkError,
    DiskFullError,
    ExternalDriftError,
    GeneratedFileError,
    ParseTimeout,
    SecurityError,
    ShadowFSError,
)
from .ir_transaction_manager import IRConfig, IRTransactionManager
from .path_canonicalizer import PathCanonicalizer
from .stub_ir import StubIRDocument, StubIRNode, StubPythonParser
from .unified_shadowfs import UnifiedShadowFS

__all__ = [
    "ShadowFSError",
    "ExternalDriftError",
    "GeneratedFileError",
    "SecurityError",
    "DiskFullError",
    "CyclicSymlinkError",
    "ParseTimeout",
    "ShadowFSCore",
    "IRTransactionManager",
    "IRConfig",
    "GeneratedFileDetector",
    "GitLFSDetector",
    "PathCanonicalizer",
    "StubIRDocument",
    "StubIRNode",
    "StubPythonParser",
    "UnifiedShadowFS",
]
