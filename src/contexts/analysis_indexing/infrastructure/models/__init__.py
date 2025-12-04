"""
Indexing Models

Models for indexing orchestration results and progress tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .job import IndexJob, IndexJobCheckpoint, JobProgress, JobStatus, TriggerType
from .mode import MODE_LAYER_CONFIG, IndexingMode, Layer
from .session import IndexSessionContext


class IndexingStatus(str, Enum):
    """Status of indexing operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some files failed but overall succeeded


class IndexingStage(str, Enum):
    """Stages of the indexing pipeline."""

    GIT_OPERATIONS = "git_operations"
    FILE_DISCOVERY = "file_discovery"
    PARSING = "parsing"
    IR_BUILDING = "ir_building"
    SEMANTIC_IR_BUILDING = "semantic_ir_building"
    GRAPH_BUILDING = "graph_building"
    CHUNK_GENERATION = "chunk_generation"
    REPOMAP_BUILDING = "repomap_building"
    LEXICAL_INDEXING = "lexical_indexing"
    VECTOR_INDEXING = "vector_indexing"
    SYMBOL_INDEXING = "symbol_indexing"
    FUZZY_INDEXING = "fuzzy_indexing"
    DOMAIN_INDEXING = "domain_indexing"
    FINALIZATION = "finalization"


@dataclass
class StageProgress:
    """Progress information for a single stage."""

    stage: IndexingStage
    status: IndexingStatus
    progress_percent: float = 0.0
    items_processed: int = 0
    items_total: int = 0
    start_time: datetime | None = None
    end_time: datetime | None = None
    error: str | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Calculate duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None


@dataclass
class IndexingResult:
    """
    Result of indexing operation.

    Contains metrics and statistics about the indexing process.
    """

    repo_id: str
    snapshot_id: str
    status: IndexingStatus
    start_time: datetime
    end_time: datetime | None = None

    # File processing
    files_discovered: int = 0
    files_processed: int = 0
    files_failed: int = 0
    files_skipped: int = 0

    # IR/Graph/Chunk stats
    ir_nodes_created: int = 0
    graph_nodes_created: int = 0
    graph_edges_created: int = 0
    chunks_created: int = 0

    # RepoMap stats
    repomap_nodes_created: int = 0
    repomap_summaries_generated: int = 0

    # Index stats
    lexical_docs_indexed: int = 0
    vector_docs_indexed: int = 0
    symbol_entries_indexed: int = 0
    fuzzy_entries_indexed: int = 0
    domain_docs_indexed: int = 0

    # Performance metrics
    stage_durations: dict[str, float] = field(default_factory=dict)
    total_duration_seconds: float = 0.0

    # Errors and warnings
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # Detailed failure tracking (for debugging)
    failed_files: list[str] = field(default_factory=list)  # File paths that failed IR generation
    failed_parse_files: list[str] = field(default_factory=list)  # Files failed to parse AST
    failed_bfg_functions: list[str] = field(default_factory=list)  # Functions failed BFG extraction
    failed_dfg_functions: list[str] = field(default_factory=list)  # Functions failed DFG analysis
    failed_graph_nodes: list[str] = field(default_factory=list)  # Node IDs failed to save to graph store
    failed_graph_edges: list[tuple[str, str]] = field(default_factory=list)  # (edge_id, reason) tuples

    # Metadata
    incremental: bool = False
    git_commit_hash: str | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.files_discovered == 0:
            return 0.0
        return (self.files_processed / self.files_discovered) * 100

    def add_error(self, error: str):
        """Add an error message."""
        self.errors.append(error)

    def add_warning(self, warning: str):
        """Add a warning message."""
        self.warnings.append(warning)

    def mark_completed(self):
        """Mark indexing as completed."""
        self.status = IndexingStatus.COMPLETED
        self.end_time = datetime.now()
        if self.start_time:
            self.total_duration_seconds = (self.end_time - self.start_time).total_seconds()

    def mark_failed(self, error: str):
        """Mark indexing as failed."""
        self.status = IndexingStatus.FAILED
        self.end_time = datetime.now()
        self.add_error(error)
        if self.start_time:
            self.total_duration_seconds = (self.end_time - self.start_time).total_seconds()

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "repo_id": self.repo_id,
            "snapshot_id": self.snapshot_id,
            "status": self.status.value,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "files_discovered": self.files_discovered,
            "files_processed": self.files_processed,
            "files_failed": self.files_failed,
            "files_skipped": self.files_skipped,
            "ir_nodes_created": self.ir_nodes_created,
            "graph_nodes_created": self.graph_nodes_created,
            "graph_edges_created": self.graph_edges_created,
            "chunks_created": self.chunks_created,
            "repomap_nodes_created": self.repomap_nodes_created,
            "repomap_summaries_generated": self.repomap_summaries_generated,
            "lexical_docs_indexed": self.lexical_docs_indexed,
            "vector_docs_indexed": self.vector_docs_indexed,
            "symbol_entries_indexed": self.symbol_entries_indexed,
            "fuzzy_entries_indexed": self.fuzzy_entries_indexed,
            "domain_docs_indexed": self.domain_docs_indexed,
            "stage_durations": self.stage_durations,
            "total_duration_seconds": self.total_duration_seconds,
            "success_rate": self.success_rate,
            "errors": self.errors,
            "warnings": self.warnings,
            "incremental": self.incremental,
            "git_commit_hash": self.git_commit_hash,
            "metadata": self.metadata,
        }


@dataclass
class OrchestratorBuilders:
    """Builder components for IndexingOrchestrator."""

    parser_registry: Any  # Registry for language parsers
    ir_builder: Any  # IR builder
    semantic_ir_builder: Any  # Semantic IR builder (CFG/DFG/types)
    graph_builder: Any  # Graph builder
    chunk_builder: Any  # Chunk builder


@dataclass
class OrchestratorRepoMap:
    """RepoMap components for IndexingOrchestrator."""

    tree_builder_class: type  # Class (needs runtime repo_id)
    pagerank_engine: Any  # Instance (config known at DI time)
    summarizer: Any | None = None  # Instance (optional)


@dataclass
class OrchestratorStores:
    """Store components for IndexingOrchestrator."""

    graph_store: Any  # Graph storage
    chunk_store: Any  # Chunk storage
    repomap_store: Any  # RepoMap storage


@dataclass
class OrchestratorIndexes:
    """Index service components for IndexingOrchestrator."""

    lexical: Any  # Lexical index service
    vector: Any  # Vector index service
    symbol: Any  # Symbol index service
    fuzzy: Any | None = None  # Fuzzy index service (optional)
    domain: Any | None = None  # Domain index service (optional)


@dataclass
class OrchestratorComponents:
    """
    Grouped components for IndexingOrchestrator.

    Usage:
        components = OrchestratorComponents(
            builders=OrchestratorBuilders(...),
            repomap=OrchestratorRepoMap(...),
            stores=OrchestratorStores(...),
            indexes=OrchestratorIndexes(...),
        )
        orchestrator = IndexingOrchestrator(components=components)
    """

    builders: OrchestratorBuilders
    repomap: OrchestratorRepoMap
    stores: OrchestratorStores
    indexes: OrchestratorIndexes


@dataclass
class IndexingConfig:
    """Configuration for indexing operation."""

    # Parallel processing
    parallel: bool = True
    max_workers: int = 4

    # File filtering
    max_file_size_mb: int = 10
    excluded_dirs: list[str] = field(
        default_factory=lambda: [
            ".git",
            "node_modules",
            "__pycache__",
            ".venv",
            "venv",
            "dist",
            "build",
            ".next",
            ".cache",
        ]
    )
    excluded_extensions: list[str] = field(
        default_factory=lambda: [
            ".pyc",
            ".pyo",
            ".so",
            ".dylib",
            ".exe",
            ".bin",
            ".jpg",
            ".png",
            ".gif",
            ".pdf",
            ".zip",
            ".tar",
            ".gz",
        ]
    )

    # Language support
    supported_languages: list[str] = field(default_factory=lambda: ["python", "typescript", "javascript"])

    # RepoMap configuration
    repomap_enabled: bool = True
    repomap_use_llm_summaries: bool = True
    repomap_max_summary_tokens: int = 200

    # Index configuration
    enable_lexical_index: bool = True
    enable_vector_index: bool = True
    enable_symbol_index: bool = True
    enable_fuzzy_index: bool = True
    enable_domain_index: bool = True
    enable_runtime_index: bool = False  # Optional

    # Error handling
    skip_parse_errors: bool = True
    continue_on_error: bool = True

    # Incremental indexing
    incremental_enabled: bool = True
    incremental_check_git_diff: bool = True

    # Performance
    chunk_batch_size: int = 100
    # OpenAI embedding API supports up to 2048 texts per request
    # Increased from 256 to 1024 for better throughput (reduces API calls by 4x)
    # Can be increased to 2048 if memory allows
    vector_batch_size: int = 1024

    # Embedding control (for benchmarking)
    skip_embedding: bool = False  # Skip embedding generation (for fast benchmarking)
    embedding_concurrency: int = 32  # Concurrent embedding requests (Ollama)

    # Git History (P0-1)
    enable_git_history: bool = False  # Enrich chunks with git history metadata

    # Mode-based indexing
    default_mode: IndexingMode = IndexingMode.FAST
    auto_mode_selection: bool = True  # 자동 모드 선택
    enable_background_scheduler: bool = True  # 백그라운드 스케줄러 사용

    # Impact-based reindexing (P2 - 2-Pass)
    enable_impact_pass: bool = True  # 영향 받은 파일 즉시 재인덱싱
    max_impact_reindex_files: int = 200  # 2nd pass 최대 파일 수
    impact_pass_modes: list[IndexingMode] = field(
        default_factory=lambda: [IndexingMode.BALANCED, IndexingMode.DEEP]
    )  # Impact pass를 실행할 모드


__all__ = [
    # Job models
    "IndexJob",
    "JobStatus",
    "TriggerType",
    "IndexJobCheckpoint",
    "JobProgress",
    # Orchestration models
    "IndexingStatus",
    "IndexingStage",
    "StageProgress",
    "IndexingResult",
    "IndexingConfig",
    # Orchestrator components (grouped parameters)
    "OrchestratorBuilders",
    "OrchestratorRepoMap",
    "OrchestratorStores",
    "OrchestratorIndexes",
    "OrchestratorComponents",
    # Session models
    "IndexSessionContext",
    # Mode models
    "IndexingMode",
    "Layer",
    "MODE_LAYER_CONFIG",
]
