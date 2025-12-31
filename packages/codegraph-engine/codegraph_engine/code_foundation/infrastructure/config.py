"""
⭐ P3-2: Centralized configuration for code_foundation

All configurable thresholds, timeouts, and limits should be defined here.
This makes them easy to find, modify, and override for different environments.

Usage:
    from codegraph_engine.code_foundation.infrastructure.config import AnalysisConfig, config

    # Use default config
    analyzer = SomeAnalyzer(max_depth=config.analysis.max_taint_depth)

    # Override for specific use case
    custom_config = AnalysisConfig(max_taint_depth=20)
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class AnalysisConfig(BaseModel):
    """Configuration for static analysis."""

    # Taint analysis
    max_taint_depth: int = Field(default=10, ge=1, le=100)
    """Maximum depth for taint tracking through call graph"""

    max_taint_paths: int = Field(default=100, ge=1, le=10000)
    """Maximum number of taint paths to report"""

    max_slice_depth: int = Field(default=10, ge=1, le=100)
    """Maximum depth for program slicing"""

    max_slice_paths: int = Field(default=100, ge=1, le=10000)
    """Maximum slice paths to compute"""

    # Points-to analysis
    points_to_timeout_ms: int = Field(default=30000, ge=1000, le=300000)
    """Timeout for points-to fixpoint computation (ms)"""

    points_to_max_iterations: int = Field(default=1000, ge=100, le=100000)
    """Maximum iterations for points-to fixpoint"""

    # CFG/DFG analysis
    max_cfg_depth: int = Field(default=50, ge=10, le=500)
    """Maximum depth for CFG traversal"""

    max_dfg_nodes: int = Field(default=10000, ge=1000, le=1000000)
    """Maximum nodes in DFG before truncation"""

    # SMT solver
    smt_timeout_ms: int = Field(default=150, ge=50, le=10000)
    """Timeout for SMT queries (ms)"""

    # Memory safety
    sep_logic_timeout_ms: int = Field(default=3000, ge=500, le=60000)
    """Timeout for separation logic analysis (ms)"""

    # Null analysis
    null_check_max_depth: int = Field(default=10, ge=1, le=50)
    """Maximum depth for null safety analysis"""

    null_check_max_iterations: int = Field(default=1000, ge=100, le=10000)
    """Maximum iterations for null analysis fixpoint"""

    null_check_timeout_ms: int = Field(default=30000, ge=1000, le=300000)
    """Timeout for null analysis (ms)"""


class RustworkxConfig(BaseModel):
    """
    Configuration for rustworkx integration (RFC-021).

    Controls whether to use rustworkx for graph algorithms.
    """

    enable_dominator: bool = Field(default=True)
    """Enable rustworkx for dominator computation (≥1000 blocks 시 필수)"""

    enable_scc: bool = Field(default=True)
    """Enable rustworkx for SCC computation (≥1000 nodes 시 필수)"""

    force_python: bool = Field(default=False)
    """Force Python implementation (debugging용)"""

    min_blocks_for_rustworkx: int = Field(default=0, ge=0, le=10000)
    """Minimum blocks to use rustworkx (0 = always try, 1000 = only large graphs)"""


class IRBuildConfig(BaseModel):
    """Configuration for IR building."""

    # Parsing
    max_ast_depth: int = Field(default=10000, ge=100, le=100000)
    """Maximum AST depth before warning/truncation"""

    max_file_size_bytes: int = Field(default=10_000_000, ge=100000, le=100_000_000)
    """Maximum file size to parse (bytes)"""

    # Type enrichment (LSP)
    lsp_timeout_ms: int = Field(default=5000, ge=1000, le=60000)
    """Timeout for LSP requests (ms)"""

    lsp_cache_size: int = Field(default=100, ge=10, le=1000)
    """LSP response cache size (LRU)"""

    lsp_hover_cache_size: int = Field(default=100, ge=10, le=1000)
    """LSP hover cache size"""

    lsp_max_retries: int = Field(default=3, ge=1, le=10)
    """Maximum LSP request retries"""

    # Cross-file resolution
    max_cross_file_depth: int = Field(default=10, ge=1, le=50)
    """Maximum depth for cross-file symbol resolution"""

    # Retrieval index
    fuzzy_match_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    """Fuzzy matching threshold for symbol search"""

    max_search_results: int = Field(default=20, ge=1, le=100)
    """Maximum search results to return"""

    # LSP concurrency
    lsp_concurrency: int = Field(default=20, ge=1, le=100)
    """Maximum concurrent LSP requests"""

    # Performance optimization: skip LSP fallback for type enrichment
    # When True, saves ~5s on 1440-file codebases (137 LSP queries skipped)
    # The skipped nodes are mostly DI components with complex types
    skip_lsp_fallback: bool = Field(default=True)
    """Skip LSP fallback for type enrichment (use local inference only)"""


class ChunkConfig(BaseModel):
    """Configuration for code chunking."""

    # Size limits
    min_chunk_lines: int = Field(default=5, ge=1, le=100)
    """Minimum lines per chunk"""

    max_chunk_lines: int = Field(default=500, ge=50, le=5000)
    """Maximum lines per chunk"""

    large_class_threshold: int = Field(default=5000, ge=1000, le=50000)
    """Threshold for splitting large classes"""

    # Similarity
    fuzzy_match_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    """Threshold for fuzzy matching (0-1)"""


class SearchConfig(BaseModel):
    """Configuration for code search."""

    # Semantic search
    semantic_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    """Minimum similarity score for semantic search"""

    hybrid_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    """Threshold for hybrid search fallback"""

    max_results: int = Field(default=100, ge=10, le=1000)
    """Maximum search results to return"""


class GraphConfig(BaseModel):
    """Configuration for graph operations."""

    # Traversal
    max_traversal_depth: int = Field(default=5, ge=1, le=50)
    """Maximum depth for graph traversal"""

    max_impact_nodes: int = Field(default=1000, ge=100, le=100000)
    """Maximum nodes in impact analysis"""

    # Context sensitivity
    k_cfa_depth: int = Field(default=3, ge=1, le=10)
    """K value for K-CFA context sensitivity"""


class PyrightConfig(BaseModel):
    """
    Pyright 설정 - IndexingMode에 따라 동적으로 조정.

    Mode별 최적화:
    - FAST: 최소 분석 (타입체크 off, 라이브러리 분석 제외)
    - BALANCED: 기본 분석 (타입체크 basic, 주요 디렉토리만)
    - DEEP: 전체 분석 (타입체크 standard, 라이브러리 포함)
    - BOOTSTRAP: 초기 인덱싱용 (최소 설정)
    """

    # Type checking mode: "off", "basic", "standard", "strict"
    type_checking_mode: str = Field(default="off")
    """Pyright type checking mode"""

    use_library_code_for_types: bool = Field(default=False)
    """Whether to analyze library source code (slow)"""

    analyze_unannotated_functions: bool = Field(default=False)
    """Whether to analyze functions without type hints"""

    # Include/Exclude patterns
    include_dirs: list[str] = Field(default_factory=lambda: ["src", "server"])
    """Directories to include in analysis"""

    exclude_patterns: list[str] = Field(
        default_factory=lambda: [
            "htmlcov",
            ".pytest_cache",
            ".vscode",
            "_docs",
            "_docs_legacy",
            "_temp_test",
            "benchmark/_external_benchmark",
            "migrations",
            "tests",
            "benchmark",
            "cwe",
            "scripts",
            "examples",
            "**/test_*.py",
            "**/*_test.py",
            "**/__pycache__",
        ]
    )
    """Patterns to exclude from analysis"""

    # Performance
    python_version: str = Field(default="3.10")
    """Python version for type checking"""

    report_missing_imports: str = Field(default="none")
    """Report missing imports: none, warning, error"""

    report_missing_type_stubs: str = Field(default="none")
    """Report missing type stubs: none, warning, error"""

    def to_pyrightconfig_dict(self) -> dict:
        """Generate pyrightconfig.json compatible dict."""
        return {
            "include": self.include_dirs,
            "exclude": self.exclude_patterns,
            "typeCheckingMode": self.type_checking_mode,
            "pythonVersion": self.python_version,
            "venvPath": ".",
            "reportMissingImports": self.report_missing_imports,
            "reportMissingTypeStubs": self.report_missing_type_stubs,
            "useLibraryCodeForTypes": self.use_library_code_for_types,
            "analyzeUnannotatedFunctions": self.analyze_unannotated_functions,
        }

    @classmethod
    def for_mode(cls, mode: str | Enum) -> PyrightConfig:
        """
        Pyright 분석 모드에 맞는 설정 반환.

        Args:
            mode: str, PyrightMode, 또는 IndexingMode
                  ("fast", "balanced", "deep", "bootstrap", "repair")

        Returns:
            PyrightConfig optimized for the mode

        Usage:
            from codegraph_engine.code_foundation.infrastructure.ir.build_config import PyrightMode
            config = PyrightConfig.for_mode(PyrightMode.FAST)  # ENUM 직접 사용
            config = PyrightConfig.for_mode("fast")  # 문자열도 호환

        Note:
            IndexingMode와 PyrightMode 모두 호환됨 (str, Enum 상속)
        """
        from enum import Enum

        # ENUM이면 value 추출, 문자열이면 그대로 사용
        if isinstance(mode, Enum):
            mode_lower = mode.value
        else:
            mode_lower = str(mode).lower()

        if mode_lower == "fast":
            # 최소 분석 - 속도 우선
            return cls(
                type_checking_mode="off",
                use_library_code_for_types=False,
                analyze_unannotated_functions=False,
                include_dirs=["src"],  # 핵심만
                exclude_patterns=[
                    "**/test_*.py",
                    "**/*_test.py",
                    "**/__pycache__",
                    "tests",
                    "benchmark",
                    "cwe",
                    "scripts",
                    "examples",
                    "_*",
                ],
            )

        elif mode_lower == "balanced":
            # 균형 모드 - 기본 설정
            return cls(
                type_checking_mode="off",
                use_library_code_for_types=True,  # inline types 활용
                analyze_unannotated_functions=False,
                include_dirs=["src", "server"],
            )

        elif mode_lower == "deep":
            # 전체 분석 - 정확도 우선
            return cls(
                type_checking_mode="basic",
                use_library_code_for_types=True,  # 라이브러리도 분석
                analyze_unannotated_functions=True,
                include_dirs=["src", "server", "tests"],
                exclude_patterns=[
                    "htmlcov",
                    ".pytest_cache",
                    ".vscode",
                    "_docs",
                    "_docs_legacy",
                    "**/__pycache__",
                ],
            )

        elif mode_lower == "bootstrap":
            # 초기 인덱싱 - 빠른 설정
            return cls(
                type_checking_mode="off",
                use_library_code_for_types=False,
                analyze_unannotated_functions=False,
                include_dirs=["src"],
                exclude_patterns=["**/test_*.py", "**/__pycache__", "_*"],
            )

        elif mode_lower == "repair":
            # 복구 모드 - 특정 파일만
            return cls(
                type_checking_mode="off",
                use_library_code_for_types=False,
                analyze_unannotated_functions=False,
                include_dirs=[],  # 동적 결정
                exclude_patterns=[],
            )

        else:
            # 기본값
            return cls()


class CodeFoundationConfig(BaseSettings):
    """
    Root configuration for code_foundation.

    Can be configured via:
    - Environment variables (prefixed with CF_)
    - Direct instantiation
    - .env file

    Examples:
        # Environment variable
        CF_ANALYSIS__MAX_TAINT_DEPTH=20
        CF_RUSTWORKX__FORCE_PYTHON=true

        # Direct
        config = CodeFoundationConfig(analysis=AnalysisConfig(max_taint_depth=20))

        # Disable rustworkx (debugging)
        config = CodeFoundationConfig(rustworkx=RustworkxConfig(force_python=True))
    """

    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    ir_build: IRBuildConfig = Field(default_factory=IRBuildConfig)
    chunk: ChunkConfig = Field(default_factory=ChunkConfig)
    rustworkx: RustworkxConfig = Field(default_factory=RustworkxConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    pyright: PyrightConfig = Field(default_factory=PyrightConfig)

    class Config:
        env_prefix = "CF_"
        env_nested_delimiter = "__"
        case_sensitive = False


@lru_cache(maxsize=1)
def get_config() -> CodeFoundationConfig:
    """
    Get the global configuration instance.

    The configuration is cached for performance.
    To reload, call get_config.cache_clear() first.

    Returns:
        CodeFoundationConfig instance
    """
    return CodeFoundationConfig()


# Convenience alias for easy access
# Note: Lazy initialization to avoid issues when imported from config/ package
try:
    config = get_config()
except Exception:
    # If config initialization fails (e.g., during circular import),
    # create a lazy getter instead
    config = None  # type: ignore


# ============================================================================
# Legacy compatibility - individual constants
# These are deprecated, use config.analysis.* etc. instead
# ============================================================================

# Analysis defaults
DEFAULT_MAX_TAINT_DEPTH = 10
DEFAULT_MAX_TAINT_PATHS = 100
DEFAULT_SMT_TIMEOUT_MS = 150

# IR build defaults
DEFAULT_MAX_AST_DEPTH = 10000
DEFAULT_LSP_TIMEOUT_MS = 5000

# Chunk defaults
DEFAULT_FUZZY_THRESHOLD = 0.7
DEFAULT_LARGE_CLASS_THRESHOLD = 5000

# Graph defaults
DEFAULT_MAX_TRAVERSAL_DEPTH = 5
DEFAULT_K_CFA_DEPTH = 3
