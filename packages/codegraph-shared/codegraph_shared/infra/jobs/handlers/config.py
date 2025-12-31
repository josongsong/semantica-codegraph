"""
Indexing Pipeline Configuration.

중앙화된 설정으로 매직넘버/하드코딩 제거.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


# ============================================================
# Enums - 문자열 하드코딩 제거
# ============================================================


class ErrorCategory(str, Enum):
    """에러 카테고리 - 재시도 정책 결정에 사용."""

    TRANSIENT = "TRANSIENT"  # 재시도 가능 (일시적 오류)
    PERMANENT = "PERMANENT"  # 재시도 불가 (영구적 오류)
    INFRASTRUCTURE = "INFRASTRUCTURE"  # 인프라 오류 (알림 필요)


class ErrorCode(str, Enum):
    """에러 코드 - 상세 에러 분류."""

    # Common
    INVALID_PAYLOAD = "INVALID_PAYLOAD"
    PATH_NOT_FOUND = "PATH_NOT_FOUND"
    OUT_OF_MEMORY = "OUT_OF_MEMORY"

    # IR Build
    IR_BUILD_ERROR = "IR_BUILD_ERROR"
    FILE_ACCESS_ERROR = "FILE_ACCESS_ERROR"
    PARSE_ERROR = "PARSE_ERROR"

    # Occurrence Build
    OCCURRENCE_BUILD_ERROR = "OCCURRENCE_BUILD_ERROR"

    # Cross-file Resolution
    CROSS_FILE_ERROR = "CROSS_FILE_ERROR"
    CACHE_MISS = "CACHE_MISS"

    # Chunk Build
    CHUNK_BUILD_ERROR = "CHUNK_BUILD_ERROR"
    IR_CACHE_MISS = "IR_CACHE_MISS"
    DB_LOCKED = "DB_LOCKED"
    DB_ERROR = "DB_ERROR"

    # Lexical Index
    LEXICAL_INDEX_ERROR = "LEXICAL_INDEX_ERROR"
    INDEX_LOCKED = "INDEX_LOCKED"
    INDEX_CORRUPTED = "INDEX_CORRUPTED"
    IO_ERROR = "IO_ERROR"
    DISK_FULL = "DISK_FULL"

    # Vector Index
    VECTOR_INDEX_ERROR = "VECTOR_INDEX_ERROR"
    CHUNK_CACHE_MISS = "CHUNK_CACHE_MISS"
    RATE_LIMITED = "RATE_LIMITED"
    NETWORK_ERROR = "NETWORK_ERROR"
    QDRANT_ERROR = "QDRANT_ERROR"
    INVALID_MODEL = "INVALID_MODEL"


class JobType(str, Enum):
    """Job 타입."""

    BUILD_IR = "BUILD_IR"
    BUILD_CHUNK = "BUILD_CHUNK"
    LEXICAL_INDEX = "LEXICAL_INDEX"
    VECTOR_INDEX = "VECTOR_INDEX"


class JobState(str, Enum):
    """Job 상태 (SemanticaTaskEngine과 일치)."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ============================================================
# Configuration Dataclasses
# ============================================================


@dataclass(frozen=True)
class ExcludePatterns:
    """파일 제외 패턴."""

    # 기본 제외 디렉토리
    default: tuple[str, ...] = (
        "venv",
        ".venv",
        "node_modules",
        ".git",
        "__pycache__",
        "build",
        "dist",
    )

    # IR 빌드 전용 추가 제외 (테스트/벤치마크)
    ir_build: tuple[str, ...] = ("benchmark",)

    def get_ir_excludes(self) -> list[str]:
        """IR 빌드용 제외 패턴."""
        return list(self.default) + list(self.ir_build)

    def get_lexical_excludes(self) -> list[str]:
        """Lexical 인덱싱용 제외 패턴."""
        return list(self.default)


@dataclass(frozen=True)
class JobPriority:
    """Job 우선순위 설정."""

    # IR: 높은 우선순위 (L2, L4 블로킹)
    ir_build: int = 10

    # Chunk: 높은 우선순위 (L4 블로킹)
    chunk_build: int = 10

    # Lexical: 중간 우선순위 (독립적)
    lexical_index: int = 5

    # Vector: 낮은 우선순위 (최종 단계)
    vector_index: int = 5


@dataclass(frozen=True)
class TimeoutConfig:
    """타임아웃 설정 (초 단위)."""

    # 전체 파이프라인 타임아웃
    pipeline: int = 600

    # 개별 Job 타임아웃
    ir_build: int = 300
    chunk_build: int = 120
    vector_index: int = 180
    lexical_index: int = 120


@dataclass(frozen=True)
class BatchConfig:
    """배치 처리 설정."""

    # Vector 인덱싱 배치 크기
    vector_batch_size: int = 100

    # Lexical 인덱싱 배치 크기
    lexical_batch_size: int = 100


@dataclass(frozen=True)
class MetricsConfig:
    """메트릭 계산 설정."""

    # Division by zero 방지용 epsilon
    min_duration_epsilon: float = 0.001


@dataclass(frozen=True)
class DefaultValues:
    """기본값 설정."""

    # 기본 스냅샷 ID
    snapshot_id: str = "main"

    # 기본 시맨틱 티어
    semantic_tier: Literal["BASE", "EXTENDED", "FULL"] = "FULL"

    # 기본 병렬 워커 수
    parallel_workers: int = 4

    # 기본 파일 패턴
    file_patterns: tuple[str, ...] = ("*.py",)

    # 기본 임베딩 모델
    embedding_model: str = "text-embedding-3-small"

    # 기본 DB 경로
    db_path: str = "data/codegraph.db"

    # 기본 Tantivy 인덱스 경로
    tantivy_index_dir: str = "data/tantivy_index"


@dataclass(frozen=True)
class QueueConfig:
    """Job Queue 설정."""

    # 기본 큐 이름
    default_queue: str = "indexing"


@dataclass(frozen=True)
class VectorSimulation:
    """Vector 인덱싱 시뮬레이션 설정 (실제 구현 전까지)."""

    # 청크당 시뮬레이션 지연 시간 (초)
    delay_per_chunk: float = 0.02


@dataclass(frozen=True)
class LexicalConfig:
    """Lexical 인덱싱 설정."""

    # 인덱싱 모드 (AGGRESSIVE, INCREMENTAL, LAZY)
    indexing_mode: str = "AGGRESSIVE"

    # 파일 읽기 시 에러 처리 모드
    file_read_errors: str = "ignore"


@dataclass(frozen=True)
class IRBuildDefaults:
    """IR Build 기본 설정 (BuildConfig 기본값)."""

    # Occurrence 활성화
    occurrences: bool = True

    # Cross-file 분석 활성화
    cross_file: bool = True

    # Retrieval index 활성화
    retrieval_index: bool = True


@dataclass(frozen=True)
class CacheKeyConfig:
    """캐시 키 접두사 설정."""

    # IR 캐시 키 접두사
    ir_prefix: str = "ir"

    # Chunk 캐시 키 접두사
    chunk_prefix: str = "chunks"

    def make_ir_key(self, repo_id: str, snapshot_id: str) -> str:
        """IR 캐시 키 생성."""
        return f"{self.ir_prefix}:{repo_id}:{snapshot_id}"

    def make_chunk_key(self, repo_id: str, snapshot_id: str) -> str:
        """Chunk 캐시 키 생성."""
        return f"{self.chunk_prefix}:{repo_id}:{snapshot_id}"

    def make_occurrence_key(self, repo_id: str, snapshot_id: str) -> str:
        """Occurrence 캐시 키 생성."""
        return f"occ:{repo_id}:{snapshot_id}"

    def make_global_ctx_key(self, repo_id: str, snapshot_id: str) -> str:
        """GlobalContext 캐시 키 생성."""
        return f"ctx:{repo_id}:{snapshot_id}"


@dataclass
class IndexingConfig:
    """
    인덱싱 파이프라인 통합 설정.

    Usage:
        config = IndexingConfig()
        config.defaults.parallel_workers  # 4
        config.timeouts.pipeline  # 600
        config.exclude_patterns.get_ir_excludes()  # ["venv", ".venv", ...]
    """

    defaults: DefaultValues = field(default_factory=DefaultValues)
    timeouts: TimeoutConfig = field(default_factory=TimeoutConfig)
    batch: BatchConfig = field(default_factory=BatchConfig)
    priority: JobPriority = field(default_factory=JobPriority)
    exclude_patterns: ExcludePatterns = field(default_factory=ExcludePatterns)
    queue: QueueConfig = field(default_factory=QueueConfig)
    vector_simulation: VectorSimulation = field(default_factory=VectorSimulation)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)
    lexical: LexicalConfig = field(default_factory=LexicalConfig)
    ir_build: IRBuildDefaults = field(default_factory=IRBuildDefaults)
    cache_keys: CacheKeyConfig = field(default_factory=CacheKeyConfig)


# 싱글톤 인스턴스 (전역 설정)
DEFAULT_CONFIG = IndexingConfig()
