"""
Unified IR Build Configuration (SOTA)

Single configuration object that replaces:
- SemanticIrBuildMode (QUICK/PR/FULL)
- IRBuildStrategy (Default/Incremental/Parallel/etc.)
- IRBuildContext layer toggles

Design Principles:
1. Single source of truth for all build options
2. Preset factory methods for common use cases
3. Fine-grained control when needed
4. No Strategy/Mode confusion

RFC-036: 3-Tier Semantic IR Model
- BASE: CFG + Calls (90% use)
- EXTENDED: + DFG + Expression (9% use)
- FULL: + SSA + PDG (1% use)

Usage:
    # Simple: Use presets (RFC-036)
    config = BuildConfig.for_editor()       # BASE tier
    config = BuildConfig.for_refactoring()  # EXTENDED tier
    config = BuildConfig.for_analysis()     # FULL tier

    # Legacy: Still works
    config = BuildConfig.for_pr_review()
    result = await builder.build(files, config)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

# PyrightMode는 AnalysisMode의 alias (RFC-021: 중복 ENUM 제거)
# shared_kernel에서 단일 정의, 기존 코드 호환성 유지
from codegraph_shared.kernel.contracts.modes import AnalysisMode

PyrightMode = AnalysisMode


class SemanticTier(str, Enum):
    """
    RFC-036: Semantic IR tiers.

    3-tier model based on usage patterns (90/9/1).
    """

    BASE = "base"  # CFG + Calls (90% AI tasks)
    EXTENDED = "extended"  # + DFG + Expression (9% AI tasks)
    FULL = "full"  # + SSA + PDG (1% AI tasks)


if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument


def _default_parallel_workers() -> int:
    """
    Calculate default parallel workers based on CPU cores.

    Returns:
        cpu_count // 2 (minimum 1, maximum 8)

    Rationale:
        - Half of CPU cores leaves room for other processes
        - Capped at 8 to avoid diminishing returns from process overhead
        - ProcessPoolExecutor has overhead per process (~10-50ms spawn time)
    """
    cpu_count = os.cpu_count() or 4
    return max(1, min(cpu_count // 2, 8))


def _max_parallel_workers() -> int:
    """
    Calculate maximum parallel workers for heavy workloads (CI, indexing).

    Returns:
        cpu_count (minimum 4, maximum 16)

    Used by: for_ci(), for_initial_index(), LayeredIRBuilder ProcessPool
    """
    cpu_count = os.cpu_count() or 8
    return max(4, min(cpu_count, 16))


def get_cpu_limit() -> int:
    """
    Get CPU core count with fallback.

    Returns:
        os.cpu_count() or 8 (default for systems without info)

    Used by: LayeredIRBuilder._build_structural_ir_parallel()
    """
    return os.cpu_count() or 8


@dataclass
class BuildConfig:
    """
    Unified IR build configuration.

    Replaces the separate Mode + Strategy pattern with a single config object.

    Categories:
    1. Analysis Depth (what to generate)
    2. Build Strategy (how to build)
    3. Performance Tuning
    4. Caching & Incremental
    """

    # ================================================================
    # 1. Analysis Depth (What to generate)
    # ================================================================

    # Layer 1: Structural IR (always on)
    # - AST nodes, edges, basic structure

    # Layer 2: Occurrences (SCIP-compatible)
    occurrences: bool = True

    # Layer 3: LSP Type Enrichment
    lsp_enrichment: bool = True

    # Layer 4: Cross-file Resolution
    cross_file: bool = True

    # Layer 5: Semantic IR (RFC-036: 3-Tier Model)
    semantic_tier: SemanticTier = SemanticTier.EXTENDED  # 🆕 Source of Truth (default: EXTENDED for compat)

    # Derived flags (set by __post_init__ based on semantic_tier)
    # SOTA: semantic_tier is Source of Truth, these are derived
    cfg: bool = field(default=True, init=False)  # Derived from tier
    dfg: bool = field(default=True, init=False)  # Derived from tier
    dfg_function_loc_threshold: int = 500  # 🆕 RFC-036: Skip huge functions
    ssa: bool = field(default=False, init=False)  # Derived from tier
    bfg: bool = True  # Basic Block Flow Graph
    expressions: bool = field(default=True, init=False)  # Derived from tier
    generic_inference: bool = field(default=True, init=False)  # Derived from tier

    # Layer 6: Analysis Indexes (build indexes only, not run analysis)
    heap_analysis: bool = False  # PDG/Taint/Slicing indexes (analysis runs separately)
    taint_analysis: bool = False  # Run taint analysis during build (deprecated, use separate analysis)

    # Layer 7: Retrieval Indexes
    retrieval_index: bool = True

    # Layer 8: Diagnostics
    diagnostics: bool = True

    # Layer 9: Package Analysis
    packages: bool = True

    # ================================================================
    # 2. Build Strategy (How to build)
    # ================================================================

    # Parallelization (default: cpu_count // 2, see _default_parallel_workers)
    parallel_workers: int = field(default_factory=_default_parallel_workers)

    # Incremental build
    incremental: bool = False  # Only rebuild changed files
    changed_files: set[str] = field(default_factory=set)  # For incremental

    # v2: Language Plugin Architecture (Feature Flag)
    use_plugin_registry: bool = False  # Enable language plugin registry (default: False for gradual migration)

    # ================================================================
    # 3. Performance Tuning
    # ================================================================

    max_concurrent_files: int = 50  # Concurrency limit
    timeout_seconds: float = 300.0  # Build timeout
    batch_size: int = 100  # Files per batch
    cache_generators: bool = True  # Cache IR generators across builds (memory vs speed tradeoff)

    # ================================================================
    # 3.1 ProcessPool Configuration (SOTA: 중앙화된 병렬 처리 설정)
    # ================================================================

    # ProcessPool을 사용할 최소 파일 수 (오버헤드 vs 이득 균형점)
    # 계산: 파일당 ~10ms 파싱 기준, 200 파일 = 2000ms 순차 vs ~300ms 병렬(8코어)
    #       500ms prewarm + 300ms 병렬 = 800ms < 2000ms 순차 → 이득
    process_pool_threshold: int = 200

    # Semantic IR ProcessPool 임계값 (현재는 Layer 1과 동일하게 유지)
    # 원래 계획: 순차+AST재사용으로 피클링 비용 회피
    # 실제: 순차 경로가 70배 느림(Pyright 직렬 호출 등)
    # TODO: 워커에 AST 전달 또는 배치 처리로 개선 후 임계값 상향
    semantic_pool_threshold: int = 200

    # ProcessPool 워커 사전 예열 여부
    # True: Bootstrap 단계에서 미리 fork (Layer 1,5에서 재사용)
    # False: 첫 사용 시 fork (지연 초기화)
    process_pool_prewarm: bool = True

    # ProcessPool 사용 여부 (False면 항상 순차 처리)
    use_process_pool: bool = True

    # ------------------------------------------------
    # Semantic IR 전용 ProcessPool 설정 (SOTA: 동적 임계값)
    # ------------------------------------------------
    # SOTA: Work-based threshold (파일 수가 아닌 예상 작업량 기반)
    #
    # 기존 문제:
    # - 고정 임계값(500)은 파일당 복잡도를 무시함
    # - httpx(180 files, 6.9k functions) vs simple(500 files, 1k functions)
    #   → httpx가 훨씬 무거운데 sequential로 처리됨
    #
    # SOTA 접근:
    # - 예상 작업량 = files * avg_complexity_factor
    # - Complexity indicators: LOC/file, functions/file, expressions/file
    # - 손익분기점: 예상 작업량이 충분히 크면 병렬 (pickle 비용 < 병렬 이득)
    #
    # Calibration (empirical):
    # - Prewarm overhead: ~500ms
    # - Pickle overhead per file: ~2ms (Semantic IR 객체 크기 의존)
    # - Sequential processing: ~70ms/file (CFG+DFG+Expression)
    # - Parallel speedup: ~8x (16 cores, 50% efficiency)
    # - Break-even: 500ms / (70ms - 70ms/8) ≈ 8 files (이론)
    #   실제로는 pickle 비용 + IPC로 ~50 files
    semantic_process_pool_threshold: int = 50  # 보수적 최소값
    use_process_pool_semantic: bool = True

    # SOTA: 동적 임계값 파라미터
    # 예상 작업량 = file_count * work_factor
    # work_factor는 런타임에 LOC, 함수 수 등으로 추정
    semantic_work_threshold: int = 5000  # 예상 작업량 (함수 수 기준)

    # ================================================================
    # 3.2 ThreadPool Configuration (SOTA: CPU-bound 순차 작업 병렬화)
    # ================================================================

    # ThreadPool을 사용할 최소 함수 수 (SSA/Dominator 빌드용)
    # 계산: 함수당 ~0.03ms SSA 빌드, 1000함수 = 30ms 순차 vs ~5ms 병렬(8스레드)
    #       ThreadPool 생성 오버헤드: ~2ms (ProcessPool보다 훨씬 가벼움)
    #       손익분기점: 100 함수 이상
    ssa_thread_pool_threshold: int = 100

    # SSA/Dominator 병렬 빌드 여부
    # NOTE: ThreadPool은 GIL 때문에 CPU-bound SSA 빌드에 비효율적
    # 테스트 결과: ThreadPool 10.5s vs 순차 1.7s (순차가 6x 빠름)
    # 순차 처리가 더 빠르므로 기본 비활성화
    use_ssa_parallel: bool = False

    # ================================================================
    # 4. Incremental Build State
    # ================================================================

    # Existing IR for incremental builds (passed to strategies)
    existing_irs: dict[str, IRDocument] = field(default_factory=dict)

    # ================================================================
    # 5. Pyright Configuration
    # ================================================================

    # Pyright analysis mode (uses PyrightMode enum)
    pyright_mode: PyrightMode = PyrightMode.BALANCED

    # ================================================================
    # 6. Context (runtime state, not config)
    # ================================================================

    project_root: Path | None = None
    repo_id: str = "default"
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """
        RFC-036: Derive flags from semantic_tier.

        SOTA: semantic_tier is Source of Truth.
        Prevents tier/flag mismatch bugs.
        """
        # Derive flags from tier
        if self.semantic_tier == SemanticTier.BASE:
            # BASE: CFG + Calls only
            object.__setattr__(self, "cfg", True)
            object.__setattr__(self, "dfg", False)
            object.__setattr__(self, "ssa", False)
            object.__setattr__(self, "expressions", False)
            object.__setattr__(self, "generic_inference", False)

        elif self.semantic_tier == SemanticTier.EXTENDED:
            # EXTENDED: + DFG + Expression
            object.__setattr__(self, "cfg", True)
            object.__setattr__(self, "dfg", True)
            object.__setattr__(self, "ssa", False)
            object.__setattr__(self, "expressions", True)
            object.__setattr__(self, "generic_inference", True)

        elif self.semantic_tier == SemanticTier.FULL:
            # FULL: All
            object.__setattr__(self, "cfg", True)
            object.__setattr__(self, "dfg", True)
            object.__setattr__(self, "ssa", True)
            object.__setattr__(self, "expressions", True)
            object.__setattr__(self, "generic_inference", True)

        # Validation
        if self.dfg_function_loc_threshold <= 0:
            raise ValueError("dfg_function_loc_threshold must be > 0")

    # ================================================================
    # Preset Factory Methods (RFC-036 Updated)
    # ================================================================

    @classmethod
    def for_editor(cls) -> BuildConfig:
        """
        Editor/LSP mode - fastest response for real-time feedback.

        Use for: Autocomplete, hover, syntax highlighting
        Speed: ~10ms/file
        """
        return cls(
            # RFC-036: BASE tier (cfg/dfg/ssa derived in __post_init__)
            semantic_tier=SemanticTier.BASE,
            occurrences=True,
            lsp_enrichment=False,  # BASE tier doesn't need LSP
            cross_file=False,
            # cfg/dfg/ssa/expressions/generic_inference: derived from tier
            heap_analysis=False,
            taint_analysis=False,
            retrieval_index=False,
            diagnostics=False,
            packages=False,
            parallel_workers=4,
            incremental=False,
            pyright_mode=PyrightMode.FAST,
        )

    @classmethod
    def for_pr_review(
        cls,
        changed_files: set[str] | None = None,
    ) -> BuildConfig:
        """
        PR review mode - security analysis on changed files.

        Use for: PR checks, code review, incremental security scan
        Speed: ~50ms/file
        """
        return cls(
            # RFC-036: Use EXTENDED tier (DFG but no SSA for speed)
            semantic_tier=SemanticTier.EXTENDED,
            # Taint-capable analysis (CFG + DFG + Expression)
            occurrences=True,
            lsp_enrichment=True,  # Pyright 타입 정보 (오버헤드 ~20%)
            cross_file=True,
            bfg=False,  # Not needed for taint
            heap_analysis=False,
            taint_analysis=True,  # Run taint on changed files
            retrieval_index=True,
            diagnostics=True,
            packages=False,  # Skip for speed
            # Incremental (half CPU for PR review)
            parallel_workers=_default_parallel_workers(),
            incremental=True,
            changed_files=changed_files or set(),
            # Pyright: balanced for PR (good accuracy without full depth)
            pyright_mode=PyrightMode.BALANCED,
        )

    @classmethod
    def for_ci(cls) -> BuildConfig:
        """
        CI/CD mode - full analysis for pipeline.

        Use for: CI security checks, build verification
        Speed: ~90ms/file
        """
        return cls(
            # RFC-036: Use FULL tier
            semantic_tier=SemanticTier.FULL,
            # Full analysis
            occurrences=True,
            lsp_enrichment=True,  # Pyright 타입 정보 (오버헤드 ~20%)
            cross_file=True,
            bfg=True,
            heap_analysis=True,
            taint_analysis=True,
            retrieval_index=True,
            diagnostics=True,
            packages=True,
            # Parallel for speed (max CPU for CI)
            parallel_workers=_max_parallel_workers(),
            incremental=False,  # Full build in CI
            # Pyright: deep for CI (maximum accuracy)
            pyright_mode=PyrightMode.DEEP,
        )

    @classmethod
    def for_initial_index(cls) -> BuildConfig:
        """
        Initial indexing mode - complete analysis for first-time setup.

        Use for: First-time repo indexing, full reindex
        Speed: ~90ms/file (but comprehensive)
        """
        return cls(
            # RFC-036: Use FULL tier
            semantic_tier=SemanticTier.FULL,
            # Everything
            occurrences=True,
            lsp_enrichment=True,  # Pyright 타입 정보 (오버헤드 ~20%)
            cross_file=True,
            bfg=True,
            heap_analysis=True,
            taint_analysis=False,  # Run separately after indexing
            retrieval_index=True,
            diagnostics=True,
            packages=True,
            # Max parallelism (full CPU for initial index)
            parallel_workers=_max_parallel_workers(),
            incremental=False,
            # Pyright: bootstrap for initial indexing (fast startup)
            pyright_mode=PyrightMode.BOOTSTRAP,
        )

    @classmethod
    def for_security_audit(cls) -> BuildConfig:
        """
        Deep security audit mode - maximum analysis depth.

        Use for: Security review, vulnerability assessment
        Speed: Slowest but most thorough
        """
        return cls(
            # RFC-036: Use FULL tier
            semantic_tier=SemanticTier.FULL,
            # Maximum analysis
            occurrences=True,
            lsp_enrichment=True,  # Pyright 타입 정보 (오버헤드 ~20%)
            cross_file=True,
            bfg=True,
            heap_analysis=True,
            taint_analysis=True,
            retrieval_index=True,
            diagnostics=True,
            packages=True,
            # Thorough but slower (half CPU for audit)
            parallel_workers=_default_parallel_workers(),
            incremental=False,
            # Pyright: deep for security audit (maximum accuracy)
            pyright_mode=PyrightMode.DEEP,
        )

    # ================================================================
    # Convenience Methods
    # ================================================================

    def get_pyright_config(self):
        """
        Get PyrightConfig for this build configuration.

        Returns:
            PyrightConfig instance matching the pyright_mode

        Usage:
            config = BuildConfig.for_ci()
            pyright_cfg = config.get_pyright_config()
            # pyright_cfg.type_checking_mode == "basic"
            # pyright_cfg.use_library_code_for_types == True
        """
        from codegraph_engine.code_foundation.infrastructure.config import PyrightConfig

        return PyrightConfig.for_mode(self.pyright_mode)

    def supports_taint(self) -> bool:
        """Whether this config supports taint analysis."""
        return self.cfg and self.dfg and self.expressions

    def is_incremental(self) -> bool:
        """Whether this is an incremental build."""
        return self.incremental and len(self.changed_files) > 0

    def is_parallel(self) -> bool:
        """Whether this uses parallel processing."""
        return self.parallel_workers > 1

    def with_project(self, project_root: Path, repo_id: str = "default") -> BuildConfig:
        """Return a copy with project info set."""
        import copy

        new = copy.copy(self)
        new.project_root = project_root
        new.repo_id = repo_id
        return new

    def with_changed_files(self, files: set[str]) -> BuildConfig:
        """Return a copy with changed files for incremental build."""
        import copy

        new = copy.copy(self)
        new.changed_files = files
        new.incremental = True
        return new

    # ================================================================
    # Internal: Legacy Compatibility (used by LayeredIRBuilder)
    # ================================================================

    def to_semantic_mode(self) -> str:
        """
        Convert to legacy SemanticIrBuildMode string.

        Internal use only - LayeredIRBuilder uses this to call _build_layers().

        RFC-036: Map semantic_tier to SemanticIrBuildMode:
        - BASE → "quick" (CFG only, no DFG/Expression)
        - EXTENDED → "pr" (CFG + DFG + Expression)
        - FULL → "full" (All)
        """
        if self.semantic_tier == SemanticTier.BASE:
            return "quick"
        elif self.semantic_tier == SemanticTier.EXTENDED:
            return "pr"
        else:  # FULL
            return "full"

    # ================================================================
    # ProcessPool Decision Helper (SOTA: 중앙화된 로직)
    # ================================================================

    def should_use_process_pool(self, file_count: int) -> bool:
        """
        ProcessPool 사용 여부 결정 (중앙화된 로직).

        Args:
            file_count: 처리할 파일 수

        Returns:
            True if ProcessPool should be used

        Rationale:
            - ProcessPool prewarm 오버헤드: ~500ms
            - 파일당 파싱 시간: ~10ms
            - 손익분기점: 200 파일 (병렬화 이득 > prewarm 비용)
        """
        return self.use_process_pool and self.parallel_workers > 1 and file_count >= self.process_pool_threshold

    def should_use_semantic_pool(
        self,
        file_count: int,
        estimated_functions: int | None = None,
        estimated_loc: int | None = None,
    ) -> bool:
        """
        Semantic IR에서 ProcessPool 사용 여부 (SOTA: 동적 임계값).

        Args:
            file_count: 처리할 파일 수
            estimated_functions: 예상 함수 수 (선택, 더 정확한 판단)
            estimated_loc: 예상 LOC (선택, complexity 추정)

        Returns:
            True if ProcessPool should be used for Semantic IR

        SOTA Rationale:
            Work-based threshold (파일 수가 아닌 작업량 기반)

            1. 기본 임계값 (파일 수만 있을 때):
               - 50+ 파일이면 병렬 시도 (보수적)

            2. 작업량 기반 (함수 수 있을 때):
               - 예상 작업량 = file_count * (estimated_functions / file_count)
               - 5000+ 함수면 병렬 확정 (httpx: 6.9k → 병렬)
               - 이유: 함수당 CFG/DFG 빌드 비용이 지배적

            3. 복잡도 기반 (LOC 있을 때):
               - LOC/file > 500 → 복잡한 파일 → 병렬 이득 큼
               - LOC/file < 100 → 단순한 파일 → pickle 비용 우세

            Break-even analysis:
            - Prewarm: 500ms (1회)
            - Pickle: 2ms/file * N
            - Sequential: 70ms/file * N
            - Parallel: 70ms/file * N / 8 (cores)
            - Break-even: 500 + 2N < 70N - 70N/8
            - Solve: N > 8 files (이론), 실제 ~50 files (IPC 오버헤드)
        """
        if not self.use_process_pool or self.parallel_workers <= 1:
            return False

        # Strategy 1: 파일 수 기반 (기본)
        if file_count >= self.semantic_process_pool_threshold:
            return True

        # Strategy 2: 작업량 기반 (함수 수)
        if estimated_functions is not None:
            if estimated_functions >= self.semantic_work_threshold:
                return True
            # 파일당 평균 함수 수가 많으면 (복잡한 파일)
            avg_functions_per_file = estimated_functions / max(file_count, 1)
            if avg_functions_per_file > 30 and file_count >= 20:
                # 복잡한 파일 20개 이상이면 병렬 이득
                return True

        # Strategy 3: 복잡도 기반 (LOC)
        if estimated_loc is not None and file_count > 0:
            avg_loc_per_file = estimated_loc / file_count
            if avg_loc_per_file > 500 and file_count >= 30:
                # 큰 파일 30개 이상이면 병렬 이득
                return True

        return False

    def should_use_process_pool_semantic(self, file_count: int) -> bool:
        """
        Semantic IR 전용 ProcessPool 사용 여부 결정.

        Semantic IR은 구조상 (현재) 워커에서 AST 재파싱 + 대용량 결과 pickle 왕복이 발생하므로,
        파일 수가 충분히 커서 병렬화 이득이 확실할 때만 ProcessPool을 사용한다.
        """
        return (
            self.use_process_pool
            and self.use_process_pool_semantic
            and self.parallel_workers > 1
            and file_count >= self.semantic_process_pool_threshold
        )

    # ================================================================
    # ThreadPool Decision Helper (SOTA: SSA/Dominator 병렬화)
    # ================================================================

    def should_use_ssa_parallel(self, function_count: int) -> bool:
        """
        SSA/Dominator 병렬 빌드 여부 결정.

        Args:
            function_count: 처리할 함수 수

        Returns:
            True if ThreadPool should be used for SSA/Dominator

        Rationale:
            - ThreadPool 생성 오버헤드: ~2ms (ProcessPool보다 훨씬 가벼움)
            - 함수당 SSA 빌드: ~0.03ms
            - 손익분기점: 100 함수 (병렬화 이득 > 오버헤드)
        """
        return self.use_ssa_parallel and self.parallel_workers > 1 and function_count >= self.ssa_thread_pool_threshold

    # ================================================================
    # RFC-036: New Presets (3-Tier Model)
    # ================================================================

    @classmethod
    def for_refactoring(cls) -> "BuildConfig":
        """
        RFC-036: Refactoring mode (EXTENDED tier).

        Tier: EXTENDED
        Layers: BASE + DFG + Expression
        Use: Extract method, inline, rename with flow (9% AI tasks)
        Perf: ~2.0s (45% of full)
        Memory: ~250MB

        Returns:
            BuildConfig with EXTENDED tier
        """
        return cls(
            semantic_tier=SemanticTier.EXTENDED,
            occurrences=True,
            lsp_enrichment=False,
            cross_file=False,
            dfg_function_loc_threshold=500,
            retrieval_index=False,
            diagnostics=False,
            packages=False,
            parallel_workers=4,
        )

    @classmethod
    def for_analysis(cls) -> "BuildConfig":
        """
        RFC-036: Analysis mode (FULL tier).

        Tier: FULL
        Layers: All (CFG + DFG + SSA + PDG)
        Use: Path-sensitive, slicing, taint (1% AI tasks)
        Perf: ~4.4s (100%)
        Memory: ~400MB

        Returns:
            BuildConfig with FULL tier
        """
        return cls(
            semantic_tier=SemanticTier.FULL,
            occurrences=True,
            lsp_enrichment=True,
            cross_file=True,
            heap_analysis=True,
            taint_analysis=False,
            retrieval_index=True,
            diagnostics=True,
            packages=True,
            parallel_workers=8,
        )


__all__ = ["BuildConfig", "PyrightMode", "SemanticTier"]
