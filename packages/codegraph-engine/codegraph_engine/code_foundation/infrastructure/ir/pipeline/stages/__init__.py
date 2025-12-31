"""Pipeline Stages

All stage implementations for the IR pipeline.

Stages:
- L0: CacheStage - Fast/Slow path caching (RFC-039)
- L1: StructuralIRStage - Structural IR from Rust
- L3: LSPTypeStage - Type enrichment from Pyright
- L4: CrossFileStage - Cross-file resolution (RFC-062)
- L5.5: TemplateIRStage - JSX/TSX/Vue template parsing
- L7: RetrievalIndexStage - Fuzzy search and ranking
- L8: DiagnosticsStage - LSP diagnostics collection
- L9: PackageStage - Package dependency analysis
- L10: ProvenanceStage - Deterministic fingerprints (RFC-037)
"""

from .cache import CacheStage
from .structural import StructuralIRStage
from .lsp_type import LSPTypeStage
from .cross_file import CrossFileStage
from .template_ir import TemplateIRStage
from .retrieval import RetrievalIndexStage
from .diagnostics import DiagnosticsStage
from .package import PackageStage
from .provenance import ProvenanceStage

__all__ = [
    "CacheStage",
    "StructuralIRStage",
    "LSPTypeStage",
    "CrossFileStage",
    "TemplateIRStage",
    "RetrievalIndexStage",
    "DiagnosticsStage",
    "PackageStage",
    "ProvenanceStage",
]
