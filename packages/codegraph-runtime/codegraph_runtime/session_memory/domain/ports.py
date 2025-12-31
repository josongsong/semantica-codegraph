"""
Session Memory Domain Ports (SOTA Refactored)

Hexagonal Architecture Ports:
- Primary Ports (Driving): Application uses these to interact with domain
- Secondary Ports (Driven): Domain uses these to interact with infrastructure

All ports are Protocol-based for maximum flexibility.
"""

from __future__ import annotations

from abc import abstractmethod
from datetime import datetime
from typing import Any, Protocol, TypeVar, runtime_checkable

from .models import (
    BugPattern,
    CodePattern,
    CodeRule,
    Episode,
    ErrorObservation,
    Guidance,
    Memory,
    MemoryScore,
    MemoryType,
    PatternMatch,
    ProjectKnowledge,
    Session,
    SimilarityQuery,
    TaskStatus,
    TaskType,
    UserPreferences,
)

# ============================================================
# Generic Type Variables
# ============================================================

T = TypeVar("T")
TPattern = TypeVar("TPattern", BugPattern, CodePattern, CodeRule)

# ============================================================
# Base Repository Protocol (Generic)
# ============================================================


@runtime_checkable
class Repository(Protocol[T]):
    """
    Generic Repository Protocol.

    Eliminates code duplication across pattern managers.
    Each concrete repository implements this for specific entity types.
    """

    @abstractmethod
    async def save(self, entity: T) -> str:
        """Save entity, return ID."""
        ...

    @abstractmethod
    async def get(self, entity_id: str) -> T | None:
        """Get entity by ID."""
        ...

    @abstractmethod
    async def delete(self, entity_id: str) -> bool:
        """Delete entity by ID."""
        ...

    @abstractmethod
    async def list(self, limit: int = 100, offset: int = 0) -> list[T]:
        """List entities with pagination."""
        ...

    @abstractmethod
    async def count(self) -> int:
        """Count total entities."""
        ...


# ============================================================
# Bounded Generic Repository with Eviction (SOTA Pattern)
# ============================================================


@runtime_checkable
class BoundedRepository(Repository[T], Protocol[T]):
    """
    Repository with memory bounds and automatic eviction.

    SOTA pattern for preventing unbounded memory growth.
    """

    @property
    @abstractmethod
    def max_size(self) -> int:
        """Maximum number of entities to store."""
        ...

    @property
    @abstractmethod
    def current_size(self) -> int:
        """Current number of entities."""
        ...

    @abstractmethod
    async def evict_oldest(self, count: int = 1) -> int:
        """
        Evict oldest/least valuable entities.

        Returns number of entities evicted.
        """
        ...


# ============================================================
# Memory Store Ports
# ============================================================


@runtime_checkable
class MemoryStorePort(Protocol):
    """Primary port for memory storage operations."""

    async def save(self, memory: Memory) -> None:
        """Save memory."""
        ...

    async def get(self, memory_id: str) -> Memory | None:
        """Get memory by ID."""
        ...

    async def get_by_session(
        self,
        session_id: str,
        memory_type: MemoryType | None = None,
    ) -> list[Memory]:
        """Get memories by session."""
        ...

    async def search(
        self,
        query: str,
        session_id: str | None = None,
        memory_type: MemoryType | None = None,
        limit: int = 10,
    ) -> list[Memory]:
        """Search memories."""
        ...

    async def delete(self, memory_id: str) -> None:
        """Delete memory."""
        ...


@runtime_checkable
class SessionStorePort(Protocol):
    """Primary port for session storage."""

    async def create(self, session: Session) -> None:
        """Create session."""
        ...

    async def get(self, session_id: str) -> Session | None:
        """Get session."""
        ...

    async def update(self, session: Session) -> None:
        """Update session."""
        ...

    async def get_by_repo(self, repo_id: str, limit: int = 10) -> list[Session]:
        """Get sessions by repo."""
        ...


# ============================================================
# Episode Repository Port
# ============================================================


@runtime_checkable
class EpisodeRepositoryPort(Protocol):
    """Repository port for episodic memory."""

    async def save(self, episode: Episode) -> str:
        """Save episode."""
        ...

    async def get(self, episode_id: str) -> Episode | None:
        """Get episode by ID."""
        ...

    async def find_similar(
        self,
        query: SimilarityQuery,
    ) -> list[tuple[Episode, MemoryScore]]:
        """
        Find similar episodes with scoring.

        Returns episodes with their composite scores.
        """
        ...

    async def find_by_error(
        self,
        error_type: str,
        error_message: str | None = None,
        project_id: str | None = None,
        limit: int = 5,
    ) -> list[Episode]:
        """Find episodes by error pattern."""
        ...

    async def find_by_project(
        self,
        project_id: str,
        task_type: TaskType | None = None,
        outcome_status: TaskStatus | None = None,
        limit: int = 20,
    ) -> list[Episode]:
        """Find episodes by project."""
        ...

    async def update_feedback(
        self,
        episode_id: str,
        helpful: bool,
        feedback_text: str | None = None,
    ) -> None:
        """Update episode feedback."""
        ...

    async def increment_retrieval_count(self, episode_id: str) -> None:
        """Increment retrieval count."""
        ...

    async def cleanup_old(
        self,
        max_age_days: int = 90,
        min_usefulness: float = 0.3,
        min_retrievals: int = 2,
    ) -> int:
        """Cleanup old low-value episodes. Returns count deleted."""
        ...


# ============================================================
# Pattern Repository Port (Generic)
# ============================================================


@runtime_checkable
class PatternRepositoryPort(Protocol[TPattern]):
    """
    Generic repository port for patterns (Bug, Code, Rule).

    SOTA: Single generic interface eliminates duplication across
    BugPatternManager, CodePatternManager, etc.
    """

    @property
    def max_patterns(self) -> int:
        """Maximum patterns to store."""
        ...

    async def add(self, pattern: TPattern) -> str:
        """
        Add pattern with automatic eviction if at capacity.

        Returns pattern ID.
        """
        ...

    async def get(self, pattern_id: str) -> TPattern | None:
        """Get pattern by ID."""
        ...

    async def find_by_criteria(
        self,
        **criteria: Any,
    ) -> list[TPattern]:
        """Find patterns matching criteria."""
        ...

    async def update(self, pattern: TPattern) -> None:
        """Update existing pattern."""
        ...

    async def remove(self, pattern_id: str) -> bool:
        """Remove pattern."""
        ...

    async def get_statistics(self) -> dict[str, Any]:
        """Get repository statistics."""
        ...


# ============================================================
# Pattern Matcher Port
# ============================================================


@runtime_checkable
class PatternMatcherPort(Protocol[TPattern]):
    """Port for pattern matching operations."""

    async def match(
        self,
        observation: ErrorObservation,
        patterns: list[TPattern],
        top_k: int = 5,
    ) -> list[PatternMatch[TPattern]]:
        """
        Match observation against patterns.

        Uses hybrid matching:
        1. Hard filter (error_type, language)
        2. Semantic similarity (embeddings)
        3. Regex boost (pattern matching)
        """
        ...


# ============================================================
# Embedding Provider Port
# ============================================================


@runtime_checkable
class EmbeddingProviderPort(Protocol):
    """Port for embedding generation."""

    @property
    def dimension(self) -> int:
        """Embedding dimension."""
        ...

    async def embed(self, text: str) -> list[float]:
        """Embed single text."""
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed batch of texts."""
        ...


# ============================================================
# Vector Store Port
# ============================================================


@runtime_checkable
class VectorStorePort(Protocol):
    """Port for vector similarity search."""

    async def upsert(
        self,
        id: str,
        vector: list[float],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Upsert vector."""
        ...

    async def search(
        self,
        query_vector: list[float],
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        """
        Search similar vectors.

        Returns list of (id, score, metadata) tuples.
        """
        ...

    async def delete(self, id: str) -> None:
        """Delete vector."""
        ...


# ============================================================
# Project Knowledge Port
# ============================================================


@runtime_checkable
class ProjectKnowledgePort(Protocol):
    """Port for project knowledge operations."""

    async def get_or_create(self, project_id: str) -> ProjectKnowledge:
        """Get or create project knowledge."""
        ...

    async def update(self, knowledge: ProjectKnowledge) -> None:
        """Update project knowledge."""
        ...

    async def update_from_episode(self, episode: Episode) -> None:
        """Update knowledge from completed episode."""
        ...


# ============================================================
# User Preferences Port
# ============================================================


@runtime_checkable
class UserPreferencesPort(Protocol):
    """Port for user preferences."""

    async def get(self, user_id: str) -> UserPreferences | None:
        """Get user preferences."""
        ...

    async def update(self, preferences: UserPreferences) -> None:
        """Update preferences."""
        ...

    async def learn_from_feedback(
        self,
        user_id: str,
        accepted: bool,
        pattern_type: str,
    ) -> None:
        """Learn from user feedback."""
        ...


# ============================================================
# Memory Scoring Port
# ============================================================


@runtime_checkable
class MemoryScorerPort(Protocol):
    """Port for memory scoring (SOTA 3-axis)."""

    def score(
        self,
        episode: Episode,
        query_embedding: list[float] | None = None,
        current_time: datetime | None = None,
    ) -> MemoryScore:
        """
        Calculate composite score.

        Uses 3-axis scoring:
        - Similarity (semantic)
        - Recency (time decay)
        - Importance (intrinsic value)
        """
        ...

    def rank(
        self,
        episodes: list[Episode],
        query_embedding: list[float] | None = None,
        top_k: int = 5,
    ) -> list[tuple[Episode, MemoryScore]]:
        """Rank episodes by composite score."""
        ...


# ============================================================
# Cache Port
# ============================================================


@runtime_checkable
class CachePort(Protocol):
    """Port for caching (L1/L2)."""

    async def get(self, key: str) -> Any | None:
        """Get cached value."""
        ...

    async def put(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Put value in cache."""
        ...

    async def delete(self, key: str) -> None:
        """Delete from cache."""
        ...

    async def clear(self) -> None:
        """Clear all cache."""
        ...


# ============================================================
# Reflection Engine Port
# ============================================================


@runtime_checkable
class ReflectionEnginePort(Protocol):
    """Port for reflection (Generative Agents style)."""

    async def should_reflect(self, episode_count: int) -> bool:
        """Check if reflection should be triggered."""
        ...

    async def reflect_on_episodes(
        self,
        episodes: list[Episode],
        project_id: str,
    ) -> list[dict[str, Any]]:
        """
        Perform reflection on episodes.

        Returns list of extracted semantic memories.
        """
        ...


# ============================================================
# Memory Retrieval Service Port (Application Layer)
# ============================================================


@runtime_checkable
class MemoryRetrievalPort(Protocol):
    """
    Application-level port for memory retrieval.

    Orchestrates across multiple memory layers.
    """

    async def load_relevant_memories(
        self,
        task_description: str,
        task_type: TaskType,
        project_id: str = "default",
        files: list[str] | None = None,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        """Load all relevant memories for a task."""
        ...

    async def query_similar_error(
        self,
        error_type: str,
        error_message: str | None = None,
        stack_trace: str | None = None,
    ) -> dict[str, Any]:
        """Query for similar errors."""
        ...

    async def synthesize_guidance(
        self,
        memories: dict[str, Any],
        task_type: TaskType,
    ) -> Guidance:
        """Synthesize guidance from memories."""
        ...

    async def learn_from_session(self, episode: Episode) -> None:
        """Learn from completed session."""
        ...
