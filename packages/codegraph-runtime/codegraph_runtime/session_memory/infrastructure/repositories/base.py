"""
Generic Repository Base Classes (SOTA)

Eliminates code duplication across BugPatternManager, CodePatternManager, etc.
Single implementation used by all pattern types via Generic[T].
"""

from __future__ import annotations

import asyncio
from abc import ABC
from collections.abc import Callable
from datetime import datetime
from typing import Any, Generic, TypeVar

from codegraph_runtime.session_memory.domain.models import Entity

T = TypeVar("T", bound=Entity)


class InMemoryRepository(ABC, Generic[T]):
    """
    Generic in-memory repository.

    Base implementation for all repository types.
    Thread-safe with asyncio locks.
    """

    def __init__(self) -> None:
        self._storage: dict[str, T] = {}
        self._lock = asyncio.Lock()

    async def save(self, entity: T) -> str:
        """Save entity, return ID."""
        async with self._lock:
            entity.updated_at = datetime.now()
            self._storage[entity.id] = entity
            return entity.id

    async def get(self, entity_id: str) -> T | None:
        """Get entity by ID."""
        return self._storage.get(entity_id)

    async def delete(self, entity_id: str) -> bool:
        """Delete entity by ID."""
        async with self._lock:
            if entity_id in self._storage:
                del self._storage[entity_id]
                return True
            return False

    async def list(self, limit: int = 100, offset: int = 0) -> list[T]:
        """List entities with pagination."""
        all_entities = list(self._storage.values())
        return all_entities[offset : offset + limit]

    async def count(self) -> int:
        """Count total entities."""
        return len(self._storage)

    async def exists(self, entity_id: str) -> bool:
        """Check if entity exists."""
        return entity_id in self._storage

    async def clear(self) -> None:
        """Clear all entities."""
        async with self._lock:
            self._storage.clear()

    async def find_by(
        self,
        predicate: Callable[[T], bool],
        limit: int | None = None,
    ) -> list[T]:
        """Find entities matching predicate."""
        results = [e for e in self._storage.values() if predicate(e)]
        if limit:
            results = results[:limit]
        return results


class BoundedInMemoryRepository(InMemoryRepository[T], Generic[T]):
    """
    Bounded in-memory repository with automatic eviction.

    SOTA pattern: Prevents unbounded memory growth with configurable
    eviction strategy (oldest, least-used, lowest-confidence).
    """

    def __init__(
        self,
        max_size: int = 500,
        eviction_batch_size: int = 10,
        sort_key: Callable[[T], Any] | None = None,
    ) -> None:
        """
        Initialize bounded repository.

        Args:
            max_size: Maximum number of entities to store
            eviction_batch_size: Number of entities to evict when at capacity
            sort_key: Function to determine eviction order (ascending = evict first)
                      Defaults to updated_at (oldest first)
        """
        super().__init__()
        self._max_size = max_size
        self._eviction_batch_size = eviction_batch_size
        self._sort_key = sort_key or (lambda e: e.updated_at)

    @property
    def max_size(self) -> int:
        """Maximum number of entities."""
        return self._max_size

    @property
    def current_size(self) -> int:
        """Current number of entities."""
        return len(self._storage)

    @property
    def is_at_capacity(self) -> bool:
        """Check if at capacity."""
        return self.current_size >= self._max_size

    async def save(self, entity: T) -> str:
        """Save entity with automatic eviction if at capacity."""
        async with self._lock:
            # Evict if at capacity and not updating existing
            if entity.id not in self._storage and self.is_at_capacity:
                await self._evict_batch()

            entity.updated_at = datetime.now()
            self._storage[entity.id] = entity
            return entity.id

    async def _evict_batch(self) -> int:
        """
        Evict a batch of entities based on sort key.

        Returns number of entities evicted.
        """
        if not self._storage:
            return 0

        # Sort all entities by eviction priority (ascending)
        sorted_entities = sorted(self._storage.values(), key=self._sort_key)

        # Evict the first batch (lowest priority)
        to_evict = sorted_entities[: self._eviction_batch_size]
        for entity in to_evict:
            del self._storage[entity.id]

        return len(to_evict)

    async def evict_oldest(self, count: int = 1) -> int:
        """Explicitly evict oldest entities."""
        async with self._lock:
            if not self._storage:
                return 0

            sorted_entities = sorted(self._storage.values(), key=self._sort_key)
            to_evict = sorted_entities[:count]

            for entity in to_evict:
                del self._storage[entity.id]

            return len(to_evict)

    async def evict_below_threshold(
        self,
        score_fn: Callable[[T], float],
        threshold: float,
        min_observations: int = 3,
    ) -> int:
        """
        Evict entities below a score threshold.

        Useful for removing low-confidence patterns after enough observations.

        Args:
            score_fn: Function to calculate entity score
            threshold: Minimum score to keep
            min_observations: Minimum observations before considering eviction

        Returns:
            Number of entities evicted
        """
        async with self._lock:
            to_evict = []

            for entity_id, entity in self._storage.items():
                # Check if has enough observations
                obs_count = getattr(entity, "observation_count", 0)
                if obs_count < min_observations:
                    continue

                # Check if below threshold
                if score_fn(entity) < threshold:
                    to_evict.append(entity_id)

            for entity_id in to_evict:
                del self._storage[entity_id]

            return len(to_evict)

    def get_statistics(self) -> dict[str, Any]:
        """Get repository statistics."""
        return {
            "current_size": self.current_size,
            "max_size": self._max_size,
            "utilization": self.current_size / self._max_size if self._max_size > 0 else 0,
            "eviction_batch_size": self._eviction_batch_size,
        }


class TimestampedRepository(BoundedInMemoryRepository[T], Generic[T]):
    """
    Repository with timestamp-based eviction and TTL support.

    Extends BoundedInMemoryRepository with:
    - TTL (Time-To-Live) support
    - Age-based cleanup
    """

    def __init__(
        self,
        max_size: int = 500,
        eviction_batch_size: int = 10,
        default_ttl_seconds: int | None = None,
    ) -> None:
        """
        Initialize timestamped repository.

        Args:
            max_size: Maximum number of entities
            eviction_batch_size: Batch size for eviction
            default_ttl_seconds: Default TTL for entities (None = no expiry)
        """
        super().__init__(
            max_size=max_size,
            eviction_batch_size=eviction_batch_size,
            sort_key=lambda e: e.updated_at,
        )
        self._ttl_seconds = default_ttl_seconds
        self._expiry: dict[str, datetime] = {}

    async def save(self, entity: T, ttl_seconds: int | None = None) -> str:
        """Save entity with optional TTL."""
        entity_id = await super().save(entity)

        # Set expiry if TTL provided
        ttl = ttl_seconds or self._ttl_seconds
        if ttl:
            async with self._lock:
                self._expiry[entity_id] = datetime.now().replace(second=datetime.now().second + ttl)

        return entity_id

    async def get(self, entity_id: str) -> T | None:
        """Get entity if not expired."""
        # Check expiry
        if entity_id in self._expiry:
            if datetime.now() > self._expiry[entity_id]:
                await self.delete(entity_id)
                return None

        return await super().get(entity_id)

    async def cleanup_expired(self) -> int:
        """Remove expired entities."""
        async with self._lock:
            now = datetime.now()
            expired = [entity_id for entity_id, expiry in self._expiry.items() if now > expiry]

            for entity_id in expired:
                if entity_id in self._storage:
                    del self._storage[entity_id]
                del self._expiry[entity_id]

            return len(expired)

    async def cleanup_older_than(self, max_age_days: int) -> int:
        """Remove entities older than specified days."""
        async with self._lock:
            cutoff = datetime.now().replace(day=datetime.now().day - max_age_days)

            to_remove = [entity_id for entity_id, entity in self._storage.items() if entity.updated_at < cutoff]

            for entity_id in to_remove:
                del self._storage[entity_id]
                if entity_id in self._expiry:
                    del self._expiry[entity_id]

            return len(to_remove)
