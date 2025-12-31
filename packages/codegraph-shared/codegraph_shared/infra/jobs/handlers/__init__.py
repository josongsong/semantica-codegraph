"""
Indexing Pipeline Job Handlers.

SemanticaTaskEngine과 통합하여 병렬 인덱싱 파이프라인 구현:

Pipeline Architecture:
    ┌───────────┐     ┌─────────────┐
    │ L1: IR    │     │ L3: Lexical │  ← 병렬 실행 (파일 경로만 필요)
    └─────┬─────┘     └─────────────┘
          │
    ┌─────┴─────┐
    │ L2: Chunk │  ← L1 완료 후 실행 (IR 필요)
    └─────┬─────┘
          │
    ┌─────┴─────┐
    │ L4: Vector│  ← L2 완료 후 실행 (Chunk 필요)
    └───────────┘

Job Types:
    - BUILD_IR: IR 빌드 (L1)
    - LEXICAL_INDEX: Tantivy 인덱싱 (L3)
    - BUILD_CHUNK: 청크 생성 (L2)
    - VECTOR_INDEX: Qdrant 인덱싱 (L4)
"""

from codegraph_shared.infra.jobs.handlers.config import (
    # Enums
    ErrorCategory,
    ErrorCode,
    JobType,
    JobState,
    # Config classes
    DEFAULT_CONFIG,
    IndexingConfig,
    BatchConfig,
    CacheKeyConfig,
    DefaultValues,
    ExcludePatterns,
    IRBuildDefaults,
    JobPriority,
    LexicalConfig,
    MetricsConfig,
    QueueConfig,
    TimeoutConfig,
    VectorSimulation,
)
from codegraph_shared.infra.jobs.handlers.ir_handler import IRBuildHandler
from codegraph_shared.infra.jobs.handlers.lexical_handler import LexicalIndexHandler
from codegraph_shared.infra.jobs.handlers.chunk_handler import ChunkBuildHandler
from codegraph_shared.infra.jobs.handlers.vector_handler import VectorIndexHandler
from codegraph_shared.infra.jobs.handlers.orchestrator import ParallelIndexingOrchestrator

__all__ = [
    # Enums
    "ErrorCategory",
    "ErrorCode",
    "JobType",
    "JobState",
    # Config
    "DEFAULT_CONFIG",
    "IndexingConfig",
    "BatchConfig",
    "CacheKeyConfig",
    "DefaultValues",
    "ExcludePatterns",
    "IRBuildDefaults",
    "JobPriority",
    "LexicalConfig",
    "MetricsConfig",
    "QueueConfig",
    "TimeoutConfig",
    "VectorSimulation",
    # Handlers
    "IRBuildHandler",
    "LexicalIndexHandler",
    "ChunkBuildHandler",
    "VectorIndexHandler",
    "ParallelIndexingOrchestrator",
]
