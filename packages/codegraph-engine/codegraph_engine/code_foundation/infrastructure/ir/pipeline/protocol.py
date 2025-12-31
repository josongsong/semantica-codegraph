"""Pipeline Protocol Types

Core abstractions for the IR pipeline v3.

SOTA Features:
- Immutable dataclasses (functional style)
- Type-safe protocols
- Generic PipelineStage[T]
- Comprehensive metrics tracking
- Hook-based observability
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
    from codegraph_engine.code_foundation.infrastructure.ir.cross_file_resolver import GlobalContext

T = TypeVar("T")


@dataclass(frozen=True)
class StageMetrics:
    """Metrics for a pipeline stage.

    Attributes:
        stage_name: Name of the stage
        duration_ms: Execution duration in milliseconds
        error: Error message if stage failed
        items_processed: Number of items processed
        metadata: Additional metadata
    """

    stage_name: str
    duration_ms: float = 0.0
    error: str | None = None
    items_processed: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CacheState:
    """Cache state for tracking hits/misses.

    Attributes:
        total_files: Total number of files
        cache_hits: Number of cache hits
        cache_misses: Number of cache misses
        fast_path_hits: Number of fast path hits (mtime+size)
        slow_path_hits: Number of slow path hits (content hash)
    """

    total_files: int
    cache_hits: int
    cache_misses: int
    fast_path_hits: int = 0
    slow_path_hits: int = 0


@dataclass
class BuildConfig:
    """Configuration for pipeline build.

    Attributes:
        repo_root: Repository root directory
        use_rust: Use Rust implementations where available
        parallel_workers: Number of parallel workers
        cache_enabled: Enable caching
        incremental: Enable incremental builds
        profile: Profile name (fast, balanced, full)
        semantic_tier: Semantic analysis tier (BASE, ADVANCED, FULL)
        lsp_types_enabled: Enable LSP type enrichment
        cross_file_enabled: Enable cross-file resolution
        provenance_enabled: Enable provenance tracking
        hash_algorithm: Hash algorithm for provenance (sha256, blake2b)
    """

    repo_root: Path | None = None
    use_rust: bool = True
    parallel_workers: int = 4
    cache_enabled: bool = True
    incremental: bool = True
    profile: str = "balanced"
    semantic_tier: str = "BASE"

    # Stage-specific config
    lsp_types_enabled: bool = True
    cross_file_enabled: bool = True
    provenance_enabled: bool = True
    hash_algorithm: str = "sha256"


@dataclass(frozen=True)
class StageContext:
    """Shared context passed between pipeline stages.

    Immutable context that is passed through the pipeline.
    Each stage returns a modified copy using dataclasses.replace().

    Attributes:
        files: Tuple of files to process
        config: Build configuration
        ir_documents: Map of file_path → IRDocument
        global_ctx: Global cross-file context
        stage_metrics: List of stage metrics
        changed_files: Set of files that changed (from cache)
        cached_irs: Map of cached IRs
        cache_state: Cache hit/miss statistics
    """

    files: tuple[Path, ...] = field(default_factory=tuple)
    config: BuildConfig = field(default_factory=BuildConfig)
    ir_documents: dict[str, "IRDocument"] = field(default_factory=dict)
    global_ctx: "GlobalContext | None" = None
    stage_metrics: list[StageMetrics] = field(default_factory=list)
    changed_files: set[Path] | None = None
    cached_irs: dict[str, "IRDocument"] = field(default_factory=dict)
    cache_state: CacheState | None = None


class PipelineStage(ABC, Generic[T]):
    """Abstract base class for pipeline stages.

    Generic type T represents the output type of the stage.

    Example:
        ```python
        class MyStage(PipelineStage[dict[str, IRDocument]]):
            async def execute(self, ctx: StageContext) -> StageContext:
                # Process files
                return replace(ctx, ir_documents=new_irs)

            def should_skip(self, ctx: StageContext) -> tuple[bool, str | None]:
                if not self.enabled:
                    return (True, "Stage disabled")
                return (False, None)
        ```
    """

    @abstractmethod
    async def execute(self, ctx: StageContext) -> StageContext:
        """Execute the stage.

        Args:
            ctx: Input context

        Returns:
            Modified context with stage results
        """
        ...

    async def run(self, ctx: StageContext) -> StageContext:
        """Run the stage (wrapper around execute).

        This method can be overridden to add pre/post processing.

        Args:
            ctx: Input context

        Returns:
            Modified context
        """
        return await self.execute(ctx)

    def should_skip(self, ctx: StageContext) -> tuple[bool, str | None]:
        """Check if stage should be skipped.

        Args:
            ctx: Current context

        Returns:
            Tuple of (should_skip, skip_reason)
        """
        return (False, None)


@dataclass
class PipelineHook:
    """Hooks for pipeline observability.

    Callbacks invoked at specific points in the pipeline execution.

    Attributes:
        on_stage_start: Called when a stage starts
        on_stage_complete: Called when a stage completes successfully
        on_stage_error: Called when a stage fails
    """

    on_stage_start: list = field(default_factory=list)
    on_stage_complete: list = field(default_factory=list)
    on_stage_error: list = field(default_factory=list)


# Re-export BuildConfig from canonical location for backward compatibility
try:
    from codegraph_engine.code_foundation.infrastructure.ir.build_config import (
        BuildConfig as CanonicalBuildConfig,
        SemanticTier,
    )
except ImportError:
    pass
