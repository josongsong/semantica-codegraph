"""
Memory System Configuration

중앙 집중식 설정 관리로 하드코딩 제거 및 환경별 설정 분리
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class SemanticMemoryConfig:
    """Semantic Memory 설정"""

    # Pattern limits
    max_bug_patterns: int = 500
    max_code_patterns: int = 200
    max_code_rules: int = 1000
    max_projects: int = 100

    # Pattern thresholds
    min_pattern_confidence: float = 0.3
    pattern_promotion_threshold: float = 0.8
    pattern_min_observations: int = 3

    # Learning rates
    ema_alpha: float = 0.2  # Exponential moving average smoothing

    @classmethod
    def from_env(cls) -> "SemanticMemoryConfig":
        """환경변수에서 로드"""
        return cls(
            max_bug_patterns=int(os.getenv("MEMORY_MAX_BUG_PATTERNS", "500")),
            max_code_patterns=int(os.getenv("MEMORY_MAX_CODE_PATTERNS", "200")),
            max_code_rules=int(os.getenv("MEMORY_MAX_CODE_RULES", "1000")),
            max_projects=int(os.getenv("MEMORY_MAX_PROJECTS", "100")),
            min_pattern_confidence=float(os.getenv("MEMORY_MIN_PATTERN_CONFIDENCE", "0.3")),
            pattern_promotion_threshold=float(os.getenv("MEMORY_PATTERN_PROMOTION_THRESHOLD", "0.8")),
            ema_alpha=float(os.getenv("MEMORY_EMA_ALPHA", "0.2")),
        )


@dataclass
class WorkingMemoryConfig:
    """Working Memory 설정"""

    # Capacity limits
    max_steps: int = 1000
    max_hypotheses: int = 50
    max_decisions: int = 100
    max_files: int = 200
    max_symbols: int = 500

    # Auto-cleanup thresholds
    auto_cleanup_enabled: bool = True
    cleanup_threshold_ratio: float = 0.9  # 90% 찼을 때 cleanup

    @classmethod
    def from_env(cls) -> "WorkingMemoryConfig":
        """환경변수에서 로드"""
        return cls(
            max_steps=int(os.getenv("MEMORY_MAX_STEPS", "1000")),
            max_hypotheses=int(os.getenv("MEMORY_MAX_HYPOTHESES", "50")),
            max_decisions=int(os.getenv("MEMORY_MAX_DECISIONS", "100")),
            max_files=int(os.getenv("MEMORY_MAX_FILES", "200")),
            max_symbols=int(os.getenv("MEMORY_MAX_SYMBOLS", "500")),
            auto_cleanup_enabled=os.getenv("MEMORY_AUTO_CLEANUP", "true").lower() == "true",
        )


@dataclass
class EpisodicMemoryConfig:
    """Episodic Memory 설정"""

    # Storage limits
    max_episodes_in_memory: int = 1000

    # Cleanup policies
    cleanup_age_days: int = 90
    min_usefulness_score: float = 0.3
    min_retrieval_count: int = 2

    # Embedding
    enable_embeddings: bool = True
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536

    @classmethod
    def from_env(cls) -> "EpisodicMemoryConfig":
        """환경변수에서 로드"""
        return cls(
            max_episodes_in_memory=int(os.getenv("MEMORY_MAX_EPISODES", "1000")),
            cleanup_age_days=int(os.getenv("MEMORY_CLEANUP_AGE_DAYS", "90")),
            min_usefulness_score=float(os.getenv("MEMORY_MIN_USEFULNESS", "0.3")),
            enable_embeddings=os.getenv("MEMORY_ENABLE_EMBEDDINGS", "true").lower() == "true",
            embedding_model=os.getenv("MEMORY_EMBEDDING_MODEL", "text-embedding-3-small"),
        )


@dataclass
class RetrievalConfig:
    """Memory Retrieval 설정 (SOTA: 3-axis scoring)"""

    # Scoring weights
    weight_similarity: float = 0.5  # Semantic similarity
    weight_recency: float = 0.3  # Time decay
    weight_importance: float = 0.2  # Importance score

    # Recency decay
    recency_decay_days: float = 30.0  # Half-life for recency score

    # Result limits
    default_top_k: int = 5
    max_results: int = 50

    @classmethod
    def from_env(cls) -> "RetrievalConfig":
        """환경변수에서 로드"""
        return cls(
            weight_similarity=float(os.getenv("MEMORY_WEIGHT_SIMILARITY", "0.5")),
            weight_recency=float(os.getenv("MEMORY_WEIGHT_RECENCY", "0.3")),
            weight_importance=float(os.getenv("MEMORY_WEIGHT_IMPORTANCE", "0.2")),
            recency_decay_days=float(os.getenv("MEMORY_RECENCY_DECAY_DAYS", "30.0")),
            default_top_k=int(os.getenv("MEMORY_DEFAULT_TOP_K", "5")),
        )


@dataclass
class CacheConfig:
    """캐싱 설정"""

    # L1 Cache (in-memory)
    enable_l1_cache: bool = True
    l1_cache_size: int = 128

    # L2 Cache (Redis)
    enable_l2_cache: bool = False
    redis_url: str = "redis://localhost:6379"
    redis_ttl_seconds: int = 3600

    # Cache strategies
    cache_project_knowledge: bool = True
    cache_bug_patterns: bool = True
    cache_episodes: bool = False  # Too dynamic

    @classmethod
    def from_env(cls) -> "CacheConfig":
        """환경변수에서 로드"""
        return cls(
            enable_l1_cache=os.getenv("MEMORY_ENABLE_L1_CACHE", "true").lower() == "true",
            l1_cache_size=int(os.getenv("MEMORY_L1_CACHE_SIZE", "128")),
            enable_l2_cache=os.getenv("MEMORY_ENABLE_L2_CACHE", "false").lower() == "true",
            redis_url=os.getenv("MEMORY_REDIS_URL", "redis://localhost:6379"),
            redis_ttl_seconds=int(os.getenv("MEMORY_REDIS_TTL", "3600")),
        )


@dataclass
class StorageConfig:
    """Storage 설정"""

    # Storage type
    storage_type: Literal["memory", "file", "postgres"] = "file"

    # File storage
    file_storage_path: Path = Path(".memory")

    # PostgreSQL
    postgres_url: str = ""
    postgres_pool_size: int = 10

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "memory_episodes"
    qdrant_api_key: str = ""

    @classmethod
    def from_env(cls) -> "StorageConfig":
        """환경변수에서 로드"""
        storage_type = os.getenv("MEMORY_STORAGE_TYPE", "file")
        return cls(
            storage_type=storage_type,  # type: ignore
            file_storage_path=Path(os.getenv("MEMORY_STORAGE_PATH", ".memory")),
            postgres_url=os.getenv("MEMORY_POSTGRES_URL", ""),
            postgres_pool_size=int(os.getenv("MEMORY_POSTGRES_POOL_SIZE", "10")),
            qdrant_url=os.getenv("MEMORY_QDRANT_URL", "http://localhost:6333"),
            qdrant_collection=os.getenv("MEMORY_QDRANT_COLLECTION", "memory_episodes"),
            qdrant_api_key=os.getenv("MEMORY_QDRANT_API_KEY", ""),
        )


@dataclass
class ReflectionConfig:
    """Reflection 설정 (Generative Agents style)"""

    # Reflection triggers
    enable_reflection: bool = True
    reflection_interval_episodes: int = 10  # N개 에피소드마다 reflection
    reflection_min_importance: float = 0.7  # 중요도 높은 것만 reflection

    # LLM settings
    reflection_model: str = "gpt-4o-mini"
    reflection_max_tokens: int = 500

    @classmethod
    def from_env(cls) -> "ReflectionConfig":
        """환경변수에서 로드"""
        return cls(
            enable_reflection=os.getenv("MEMORY_ENABLE_REFLECTION", "true").lower() == "true",
            reflection_interval_episodes=int(os.getenv("MEMORY_REFLECTION_INTERVAL", "10")),
            reflection_min_importance=float(os.getenv("MEMORY_REFLECTION_MIN_IMPORTANCE", "0.7")),
            reflection_model=os.getenv("MEMORY_REFLECTION_MODEL", "gpt-4o-mini"),
        )


@dataclass
class MemorySystemConfig:
    """전체 Memory System 통합 설정"""

    semantic: SemanticMemoryConfig = field(default_factory=SemanticMemoryConfig)
    working: WorkingMemoryConfig = field(default_factory=WorkingMemoryConfig)
    episodic: EpisodicMemoryConfig = field(default_factory=EpisodicMemoryConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    reflection: ReflectionConfig = field(default_factory=ReflectionConfig)

    @classmethod
    def from_env(cls) -> "MemorySystemConfig":
        """환경변수에서 전체 설정 로드"""
        return cls(
            semantic=SemanticMemoryConfig.from_env(),
            working=WorkingMemoryConfig.from_env(),
            episodic=EpisodicMemoryConfig.from_env(),
            retrieval=RetrievalConfig.from_env(),
            cache=CacheConfig.from_env(),
            storage=StorageConfig.from_env(),
            reflection=ReflectionConfig.from_env(),
        )

    @classmethod
    def for_development(cls) -> "MemorySystemConfig":
        """개발 환경 기본 설정"""
        return cls(
            storage=StorageConfig(storage_type="file"),
            cache=CacheConfig(enable_l1_cache=True, enable_l2_cache=False),
            episodic=EpisodicMemoryConfig(enable_embeddings=False),  # 빠른 테스트
        )

    @classmethod
    def for_production(cls) -> "MemorySystemConfig":
        """프로덕션 환경 기본 설정"""
        return cls(
            storage=StorageConfig(storage_type="postgres"),
            cache=CacheConfig(enable_l1_cache=True, enable_l2_cache=True),
            episodic=EpisodicMemoryConfig(enable_embeddings=True),
            reflection=ReflectionConfig(enable_reflection=True),
        )


# Singleton instance
_config: MemorySystemConfig | None = None


def get_config() -> MemorySystemConfig:
    """전역 설정 인스턴스 가져오기 (singleton)"""
    global _config
    if _config is None:
        _config = MemorySystemConfig.from_env()
    return _config


def set_config(config: MemorySystemConfig) -> None:
    """전역 설정 설정 (테스트용)"""
    global _config
    _config = config


def reset_config() -> None:
    """전역 설정 리셋"""
    global _config
    _config = None
