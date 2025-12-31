"""Pipeline Builder

Fluent API for constructing IR pipelines with preset profiles.

SOTA Features:
- Fluent builder pattern for excellent DX
- Preset profiles (fast, balanced, full)
- Fine-grained stage control
- Parallel execution groups
- Hook registration
- Type-safe configuration

Example:
    ```python
    # Quick start with preset
    pipeline = (
        PipelineBuilder()
        .with_profile("balanced")
        .with_files([Path("src/main.py")])
        .build()
    )

    # Advanced customization
    pipeline = (
        PipelineBuilder()
        .with_cache(enabled=True, fast_path=True)
        .with_structural_ir(use_rust=True)
        .with_lsp_types(enabled=False)  # Skip type enrichment
        .with_cross_file(incremental=True)
        .with_provenance(hash_algorithm="blake2b")
        .with_hook("on_stage_complete", my_callback)
        .with_parallel([
            [CacheStage],  # Group 1
            [StructuralIRStage, LSPTypeStage],  # Group 2 (parallel)
        ])
        .build()
    )

    # Execute
    result = await pipeline.execute()
    ```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from codegraph_shared.infra.logging import get_logger

from .protocol import BuildConfig, PipelineHook, PipelineStage, StageContext
from .orchestrator import StageOrchestrator
from .stages import (
    CacheStage,
    CrossFileStage,
    DiagnosticsStage,
    LSPTypeStage,
    PackageStage,
    ProvenanceStage,
    RetrievalIndexStage,
    StructuralIRStage,
    TemplateIRStage,
)

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models.ir_document import IRDocument

logger = get_logger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for pipeline builder."""

    # Files to process
    files: list[Path] = field(default_factory=list)

    # Build config
    build_config: BuildConfig = field(default_factory=BuildConfig)

    # Stage configurations
    cache_config: dict = field(default_factory=dict)
    structural_config: dict = field(default_factory=dict)
    lsp_type_config: dict = field(default_factory=dict)
    cross_file_config: dict = field(default_factory=dict)
    template_ir_config: dict = field(default_factory=dict)
    retrieval_config: dict = field(default_factory=dict)
    diagnostics_config: dict = field(default_factory=dict)
    package_config: dict = field(default_factory=dict)
    provenance_config: dict = field(default_factory=dict)

    # Hooks
    hooks: dict[str, list[Callable]] = field(default_factory=dict)

    # Parallel execution groups (stage indices)
    parallel_groups: list[list[int]] = field(default_factory=list)

    # Cached IRs (for incremental builds)
    cached_irs: dict[str, "IRDocument"] = field(default_factory=dict)


class PipelineBuilder:
    """Fluent builder for IR pipelines.

    SOTA Developer Experience:
    - Preset profiles for quick start
    - Fine-grained control for advanced use
    - Type-safe configuration
    - Chainable methods
    - Clear defaults

    Example:
        ```python
        pipeline = (
            PipelineBuilder()
            .with_profile("balanced")
            .with_files(files)
            .with_cache(fast_path=True)
            .build()
        )
        ```
    """

    def __init__(self):
        """Initialize builder with default config."""
        self._config = PipelineConfig()

    def with_profile(self, profile: str) -> "PipelineBuilder":
        """Apply preset profile.

        Profiles:
        - "fast": Skip expensive stages (no LSP, no retrieval)
            - L0: Cache (fast path only)
            - L1: Structural IR
            - L4: Cross-file (incremental)

        - "balanced": Default profile (good DX + performance)
            - L0: Cache (fast + slow path)
            - L1: Structural IR
            - L3: LSP Types (lightweight)
            - L4: Cross-file (incremental)
            - L10: Provenance

        - "full": All stages enabled (maximum features)
            - L0: Cache
            - L1: Structural IR
            - L3: LSP Types
            - L4: Cross-file
            - L7: Retrieval Index
            - L10: Provenance

        Args:
            profile: Profile name (fast, balanced, full)

        Returns:
            Self for chaining
        """
        if profile == "fast":
            self._config.cache_config = {"enabled": True, "fast_path_only": True}
            self._config.structural_config = {"enabled": True}
            self._config.lsp_type_config = {"enabled": False}
            self._config.cross_file_config = {"enabled": True, "incremental": True}
            self._config.template_ir_config = {"enabled": False}
            self._config.retrieval_config = {"enabled": False}
            self._config.diagnostics_config = {"enabled": False}
            self._config.package_config = {"enabled": False}
            self._config.provenance_config = {"enabled": False}

        elif profile == "balanced":
            self._config.cache_config = {"enabled": True, "fast_path_only": False}
            self._config.structural_config = {"enabled": True}
            self._config.lsp_type_config = {"enabled": True, "max_concurrent": 5}
            self._config.cross_file_config = {"enabled": True, "incremental": True}
            self._config.template_ir_config = {"enabled": True}
            self._config.retrieval_config = {"enabled": False}
            self._config.diagnostics_config = {"enabled": False}
            self._config.package_config = {"enabled": True}
            self._config.provenance_config = {"enabled": True}

        elif profile == "full":
            self._config.cache_config = {"enabled": True}
            self._config.structural_config = {"enabled": True}
            self._config.lsp_type_config = {"enabled": True, "max_concurrent": 10}
            self._config.cross_file_config = {"enabled": True, "use_msgpack": True}
            self._config.template_ir_config = {"enabled": True}
            self._config.retrieval_config = {"enabled": True}
            self._config.diagnostics_config = {"enabled": True}
            self._config.package_config = {"enabled": True}
            self._config.provenance_config = {"enabled": True, "hash_algorithm": "blake2b"}

        else:
            raise ValueError(f"Unknown profile: {profile}. Use 'fast', 'balanced', or 'full'")

        logger.info(f"Applied profile: {profile}")
        return self

    def with_files(self, files: list[Path]) -> "PipelineBuilder":
        """Set files to process.

        Args:
            files: List of file paths

        Returns:
            Self for chaining
        """
        self._config.files = files
        return self

    def with_build_config(self, config: BuildConfig) -> "PipelineBuilder":
        """Set build configuration.

        Args:
            config: BuildConfig instance

        Returns:
            Self for chaining
        """
        self._config.build_config = config
        return self

    def with_cache(self, **kwargs) -> "PipelineBuilder":
        """Configure L0 cache stage.

        Args:
            enabled: Enable caching
            fast_path_only: Use only fast path (mtime+size)
            cache_dir: Cache directory
            ttl_seconds: TTL for cache entries
            max_size: Max cache size (LRU eviction)

        Returns:
            Self for chaining
        """
        self._config.cache_config.update(kwargs)
        return self

    def with_structural_ir(self, **kwargs) -> "PipelineBuilder":
        """Configure L1 structural IR stage.

        Args:
            enabled: Enable structural IR
            use_rust: Use Rust implementation (default: True)
            use_msgpack: Use msgpack API (default: True)

        Returns:
            Self for chaining
        """
        self._config.structural_config.update(kwargs)
        return self

    def with_lsp_types(self, **kwargs) -> "PipelineBuilder":
        """Configure L3 LSP type stage.

        Args:
            enabled: Enable LSP type enrichment
            max_concurrent: Max concurrent LSP requests
            lsp_timeout: Timeout per file (seconds)
            fail_fast: Raise on first error

        Returns:
            Self for chaining
        """
        self._config.lsp_type_config.update(kwargs)
        return self

    def with_cross_file(self, **kwargs) -> "PipelineBuilder":
        """Configure L4 cross-file resolution stage.

        Args:
            enabled: Enable cross-file resolution
            use_msgpack: Use msgpack API (25x faster)
            incremental: Use incremental updates

        Returns:
            Self for chaining
        """
        self._config.cross_file_config.update(kwargs)
        return self

    def with_retrieval(self, **kwargs) -> "PipelineBuilder":
        """Configure L7 retrieval index stage.

        Args:
            enabled: Enable retrieval indexing
            min_score: Minimum fuzzy match score
            max_results: Maximum results per query
            enable_fuzzy: Enable fuzzy matching
            enable_tfidf: Enable TF-IDF ranking

        Returns:
            Self for chaining
        """
        self._config.retrieval_config.update(kwargs)
        return self

    def with_provenance(self, **kwargs) -> "PipelineBuilder":
        """Configure L10 provenance stage.

        Args:
            enabled: Enable provenance tracking
            hash_algorithm: Hash algorithm (sha256, blake2b)
            include_comments: Include comments in hash
            include_docstrings: Include docstrings in hash

        Returns:
            Self for chaining
        """
        self._config.provenance_config.update(kwargs)
        return self

    def with_template_ir(self, **kwargs) -> "PipelineBuilder":
        """Configure L5.5 template IR stage.

        Args:
            enabled: Enable template IR processing (JSX/TSX/Vue)

        Returns:
            Self for chaining
        """
        self._config.template_ir_config.update(kwargs)
        return self

    def with_diagnostics(self, **kwargs) -> "PipelineBuilder":
        """Configure L8 diagnostics stage.

        Args:
            enabled: Enable LSP diagnostics collection
            lsp_manager: Custom LSP manager (optional)

        Returns:
            Self for chaining
        """
        self._config.diagnostics_config.update(kwargs)
        return self

    def with_package(self, **kwargs) -> "PipelineBuilder":
        """Configure L9 package analysis stage.

        Args:
            enabled: Enable package dependency analysis
            project_root: Project root directory (optional)

        Returns:
            Self for chaining
        """
        self._config.package_config.update(kwargs)
        return self

    def with_hook(self, event: str, callback: Callable) -> "PipelineBuilder":
        """Register hook callback.

        Events:
        - "on_stage_start": (stage_name: str, ctx: StageContext)
        - "on_stage_complete": (stage_name: str, ctx: StageContext, duration_ms: float)
        - "on_stage_error": (stage_name: str, ctx: StageContext, error: Exception)

        Args:
            event: Event name
            callback: Callback function

        Returns:
            Self for chaining
        """
        if event not in self._config.hooks:
            self._config.hooks[event] = []

        self._config.hooks[event].append(callback)
        return self

    def with_parallel(self, groups: list[list[int]]) -> "PipelineBuilder":
        """Configure parallel execution groups.

        Args:
            groups: List of stage index groups (each group runs in parallel)

        Example:
            ```python
            .with_parallel([
                [0],        # Stage 0 runs alone
                [1, 2, 3],  # Stages 1,2,3 run in parallel
                [4],        # Stage 4 runs after 1,2,3 complete
            ])
            ```

        Returns:
            Self for chaining
        """
        self._config.parallel_groups = groups
        return self

    def with_cached_irs(self, cached_irs: dict[str, "IRDocument"]) -> "PipelineBuilder":
        """Provide cached IRs for incremental builds.

        Args:
            cached_irs: Map of file_path → IRDocument

        Returns:
            Self for chaining
        """
        self._config.cached_irs = cached_irs
        return self

    def build(self) -> "IRPipeline":
        """Build pipeline from configuration.

        Returns:
            Configured IRPipeline ready to execute
        """
        # Create stages
        stages: list[PipelineStage] = []

        # L0: Cache
        if self._config.cache_config.get("enabled", True):
            stages.append(CacheStage(**self._config.cache_config))

        # L1: Structural IR
        if self._config.structural_config.get("enabled", True):
            stages.append(StructuralIRStage(**self._config.structural_config))

        # L3: LSP Types
        if self._config.lsp_type_config.get("enabled", False):
            stages.append(LSPTypeStage(**self._config.lsp_type_config))

        # L4: Cross-File
        if self._config.cross_file_config.get("enabled", True):
            stages.append(CrossFileStage(**self._config.cross_file_config))

        # L5.5: Template IR
        if self._config.template_ir_config.get("enabled", False):
            stages.append(TemplateIRStage(**self._config.template_ir_config))

        # L7: Retrieval
        if self._config.retrieval_config.get("enabled", False):
            stages.append(RetrievalIndexStage(**self._config.retrieval_config))

        # L8: Diagnostics
        if self._config.diagnostics_config.get("enabled", False):
            stages.append(DiagnosticsStage(**self._config.diagnostics_config))

        # L9: Package
        if self._config.package_config.get("enabled", False):
            stages.append(PackageStage(**self._config.package_config))

        # L10: Provenance
        if self._config.provenance_config.get("enabled", False):
            stages.append(ProvenanceStage(**self._config.provenance_config))

        # Create hooks
        hooks = PipelineHook(
            on_stage_start=self._config.hooks.get("on_stage_start", []),
            on_stage_complete=self._config.hooks.get("on_stage_complete", []),
            on_stage_error=self._config.hooks.get("on_stage_error", []),
        )

        # Create orchestrator
        orchestrator = StageOrchestrator(stages, hooks)

        # Create initial context
        initial_ctx = StageContext(
            files=tuple(self._config.files),
            config=self._config.build_config,
            cached_irs=self._config.cached_irs,
        )

        # Create pipeline
        from .pipeline import IRPipeline

        return IRPipeline(
            orchestrator=orchestrator,
            initial_ctx=initial_ctx,
            parallel_groups=self._config.parallel_groups,
        )
