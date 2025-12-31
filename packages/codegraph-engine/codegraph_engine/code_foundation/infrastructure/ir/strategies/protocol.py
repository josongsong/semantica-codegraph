"""
IR Build Strategy Protocol

Defines the interface for all IR build strategies.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from codegraph_engine.code_foundation.domain.semantic_ir.mode import SemanticIrBuildMode

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.cross_file_resolver import GlobalContext
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
    from codegraph_engine.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex


@dataclass
class IRBuildContext:
    """
    Context for IR build operations.

    Carries configuration and state across the build pipeline.
    Strategies can read/write to this context.
    """

    project_root: Path
    repo_id: str = "default"

    # Layer toggles
    enable_occurrences: bool = True
    enable_lsp_enrichment: bool = True
    enable_cross_file: bool = True
    enable_retrieval_index: bool = True
    enable_semantic_ir: bool = False
    semantic_mode: SemanticIrBuildMode = SemanticIrBuildMode.FULL
    enable_advanced_analysis: bool = False  # Layer 6: Analysis indexes (not analysis execution)
    collect_diagnostics: bool = True
    analyze_packages: bool = True

    # State (mutable, carried across pipeline)
    existing_irs: dict[str, "IRDocument"] = field(default_factory=dict)
    global_ctx: "GlobalContext | None" = None
    retrieval_index: "RetrievalOptimizedIndex | None" = None

    # Strategy-specific options
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class IRBuildResult:
    """
    Result of IR build operation.

    Unified return type for all strategies.
    """

    ir_documents: dict[str, "IRDocument"]
    global_ctx: "GlobalContext"
    retrieval_index: "RetrievalOptimizedIndex"
    diagnostic_index: Any = None  # DiagnosticIndex | None
    package_index: Any = None  # PackageIndex | None

    # RFC-037 Phase 2: Build provenance (determinism tracking)
    provenance: Any = None  # BuildProvenance | None

    # Metrics
    files_processed: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    elapsed_seconds: float = 0.0

    # Strategy-specific results
    extra: dict[str, Any] = field(default_factory=dict)

    # Layer-specific detailed statistics
    layer_stats: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get_stats(self) -> dict[str, Any]:
        """
        Get comprehensive statistics from the build result.

        Returns:
            Dictionary with all collected statistics from each layer.
        """
        # Basic metrics
        stats: dict[str, Any] = {
            "files_processed": self.files_processed,
            "files_skipped": self.files_skipped,
            "files_failed": self.files_failed,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }

        # Aggregate IR document stats
        total_nodes = sum(len(doc.nodes) for doc in self.ir_documents.values())
        total_edges = sum(len(doc.edges) for doc in self.ir_documents.values())
        total_occurrences = sum(len(doc.occurrences) for doc in self.ir_documents.values())

        stats["structural_ir"] = {
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "total_occurrences": total_occurrences,
        }

        # Cross-file resolution stats
        if self.global_ctx and hasattr(self.global_ctx, "get_stats"):
            stats["cross_file"] = self.global_ctx.get_stats()

        # Retrieval index stats
        if self.retrieval_index and hasattr(self.retrieval_index, "get_stats"):
            stats["retrieval_index"] = self.retrieval_index.get_stats()

        # Diagnostic index stats
        if self.diagnostic_index and hasattr(self.diagnostic_index, "get_stats"):
            stats["diagnostics"] = self.diagnostic_index.get_stats()

        # Package index stats
        if self.package_index and hasattr(self.package_index, "get_stats"):
            stats["packages"] = self.package_index.get_stats()

        # Layer-specific stats (collected during build)
        stats["layers"] = self.layer_stats

        return stats


class IRBuildStrategy(ABC):
    """
    Strategy interface for IR building.

    Each strategy implements a different approach to IR generation:
    - DefaultStrategy: Full 9-layer sequential build
    - IncrementalStrategy: Delta-based with change tracking
    - ParallelStrategy: Multi-process parallel build
    - OverlayStrategy: Git uncommitted changes overlay
    - QuickStrategy: Layer 1 only for fast feedback

    Strategies can:
    1. Pre-process files (filter, sort, batch)
    2. Build structural IR (Layer 1)
    3. Post-process IR (add layers 2-9)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name for logging/debugging."""
        ...

    @abstractmethod
    async def build(
        self,
        files: list[Path],
        context: IRBuildContext,
    ) -> IRBuildResult:
        """
        Build IR for given files.

        Args:
            files: Files to process
            context: Build context with configuration and state

        Returns:
            IRBuildResult with IR documents and metadata
        """
        ...

    def pre_process(
        self,
        files: list[Path],
        context: IRBuildContext,
    ) -> list[Path]:
        """
        Pre-process files before IR generation.

        Override to filter, sort, or batch files.
        Default: return files unchanged.

        Args:
            files: Input files
            context: Build context

        Returns:
            Processed files
        """
        return files

    def post_process(
        self,
        result: IRBuildResult,
        context: IRBuildContext,
    ) -> IRBuildResult:
        """
        Post-process IR after generation.

        Override to add custom processing.
        Default: return result unchanged.

        Args:
            result: Build result
            context: Build context

        Returns:
            Processed result
        """
        return result
