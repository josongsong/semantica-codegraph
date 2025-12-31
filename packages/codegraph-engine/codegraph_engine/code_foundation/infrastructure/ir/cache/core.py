"""
RFC-039 P0.1.5: Common Cache Infrastructure

Shared base classes and utilities for Structural IR and Semantic IR caches.

Design:
- BaseCacheStats: Common statistics tracking
- BaseVersionEnum: Version enum pattern
- BaseCacheError hierarchy: Unified exception handling
- Checksum utilities: xxhash/hashlib abstraction

Usage:
    from codegraph_engine.code_foundation.infrastructure.ir.cache.core import (
        BaseCacheStats,
        CacheError,
        CacheCorruptError,
        compute_xxh3_128,
        compute_xxh32,
    )
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# SOTA: Fast hashing (xxhash > hashlib for non-crypto)
try:
    import xxhash

    HAS_XXHASH = True
except ImportError:
    import hashlib

    HAS_XXHASH = False


# =============================================================================
# Exception Hierarchy
# =============================================================================


class CacheError(Exception):
    """Base exception for all cache errors."""

    pass


class CacheCorruptError(CacheError):
    """
    Cache entry is corrupted.

    Causes:
    - Invalid magic bytes
    - Checksum mismatch
    - Truncated file
    - Invalid payload structure
    """

    def __init__(self, message: str, cache_path: "Path | None" = None):
        self.cache_path = cache_path
        super().__init__(message)


class CacheVersionMismatchError(CacheError):
    """
    Cache entry has incompatible version.

    Causes:
    - Schema version changed (payload structure)
    - Engine version changed (generation logic)
    """

    def __init__(
        self,
        message: str = "Version mismatch",
        found_version: int | str | None = None,
        expected_version: int | str | None = None,
    ):
        self.found_version = found_version
        self.expected_version = expected_version
        if found_version is not None and expected_version is not None:
            message = f"Version mismatch: found {found_version}, expected {expected_version}"
        super().__init__(message)


class CacheSerializationError(CacheError):
    """
    Failed to serialize/deserialize cache entry.

    Causes:
    - msgpack encoding error
    - pickle error
    - Object not serializable
    """

    pass


class CacheDiskFullError(CacheError):
    """Disk full (ENOSPC) during cache write."""

    pass


class CachePermissionError(CacheError):
    """Permission denied (EACCES) during cache operation."""

    pass


# =============================================================================
# Statistics
# =============================================================================


@dataclass
class BaseCacheStats:
    """
    Common cache statistics.

    Thread-safe via external locking in cache implementations.

    Metrics:
    - hits/misses: Basic hit rate
    - write_fails: Write error count
    - corrupt_entries: Corrupted entry count
    - evictions: LRU eviction count (memory cache)
    """

    hits: int = 0
    misses: int = 0
    write_fails: int = 0
    corrupt_entries: int = 0
    evictions: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    @property
    def total_requests(self) -> int:
        """Total cache requests (hits + misses)."""
        return self.hits + self.misses

    def to_dict(self) -> dict[str, int | float]:
        """Convert to dictionary for serialization."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hit_rate, 4),
            "write_fails": self.write_fails,
            "corrupt_entries": self.corrupt_entries,
            "evictions": self.evictions,
            "total_requests": self.total_requests,
        }

    def reset(self) -> None:
        """Reset all statistics to zero."""
        self.hits = 0
        self.misses = 0
        self.write_fails = 0
        self.corrupt_entries = 0
        self.evictions = 0


@dataclass
class ExtendedCacheStats(BaseCacheStats):
    """
    Extended statistics for semantic cache.

    Additional metrics:
    - schema_mismatches: Schema version mismatch count
    - disk_full_errors: Disk full error count
    - total_saved_ms: Estimated time saved by cache hits
    """

    schema_mismatches: int = 0
    disk_full_errors: int = 0
    total_saved_ms: float = 0.0

    def to_dict(self) -> dict[str, int | float]:
        """Convert to dictionary for serialization."""
        base = super().to_dict()
        base.update(
            {
                "schema_mismatches": self.schema_mismatches,
                "disk_full_errors": self.disk_full_errors,
                "total_saved_ms": round(self.total_saved_ms, 2),
            }
        )
        return base

    def reset(self) -> None:
        """Reset all statistics to zero."""
        super().reset()
        self.schema_mismatches = 0
        self.disk_full_errors = 0
        self.total_saved_ms = 0.0


# =============================================================================
# Version Enum Base
# =============================================================================


class BaseVersionEnum(str, Enum):
    """
    Base class for version enums.

    Pattern:
    - Each version is a string value
    - current() returns the latest version
    - Automatic cache invalidation on version change

    Usage:
        class SchemaVersion(BaseVersionEnum):
            V1 = "v1"
            V2 = "v2"  # Latest

        current = SchemaVersion.current()  # "v2"
    """

    @classmethod
    def current(cls) -> str:
        """Get current (latest) version string."""
        # Return the last enum value (convention: latest is last)
        return list(cls)[-1].value

    @classmethod
    def all_versions(cls) -> list[str]:
        """Get all version strings."""
        return [v.value for v in cls]


# =============================================================================
# Checksum Utilities
# =============================================================================


def compute_xxh3_128(data: bytes) -> bytes:
    """
    Compute xxh3_128 checksum (16 bytes).

    Fast non-cryptographic hash, ideal for cache validation.
    Fallback: SHA-256[:16] if xxhash not available.

    Args:
        data: Bytes to hash

    Returns:
        16-byte checksum
    """
    if HAS_XXHASH:
        return xxhash.xxh3_128_digest(data)
    else:
        import hashlib

        return hashlib.sha256(data).digest()[:16]


def compute_xxh3_128_hex(data: bytes) -> str:
    """
    Compute xxh3_128 checksum as hex string (32 chars).

    Args:
        data: Bytes to hash

    Returns:
        32-character hex string
    """
    if HAS_XXHASH:
        return xxhash.xxh3_128_hexdigest(data)
    else:
        import hashlib

        return hashlib.sha256(data).hexdigest()[:32]


def compute_xxh32(data: bytes) -> int:
    """
    Compute xxh32 checksum (4 bytes as int).

    Faster but less collision-resistant than xxh3_128.
    Fallback: CRC32 if xxhash not available.

    Args:
        data: Bytes to hash

    Returns:
        32-bit unsigned integer checksum
    """
    if HAS_XXHASH:
        return xxhash.xxh32_intdigest(data)
    else:
        import zlib

        return zlib.crc32(data) & 0xFFFFFFFF


def compute_content_hash(content: str | bytes, use_xxhash: bool = True) -> str:
    """
    Compute content hash for cache key.

    Args:
        content: File content (str or bytes)
        use_xxhash: Use xxhash (fast) vs SHA-256 (crypto-safe)

    Returns:
        Hex digest string (32 chars for xxh3_128, 64 chars for SHA-256)
    """
    if isinstance(content, str):
        content_bytes = content.encode("utf-8", errors="replace")
    else:
        content_bytes = content

    if use_xxhash and HAS_XXHASH:
        return xxhash.xxh3_128_hexdigest(content_bytes)
    else:
        import hashlib

        return hashlib.sha256(content_bytes).hexdigest()


# =============================================================================
# Cache Backend Protocol
# =============================================================================


class CacheBackendProtocol(ABC):
    """
    Abstract protocol for cache backends.

    Implementations:
    - MemoryCache: In-process memory (volatile)
    - DiskCache: Persistent disk storage
    - TieredCache: L1 (Memory) + L2 (Disk)
    """

    @abstractmethod
    def get(self, key: str) -> Any | None:
        """
        Get cached value.

        Args:
            key: Cache key string

        Returns:
            Cached value or None on miss
        """
        ...

    @abstractmethod
    def set(self, key: str, value: Any) -> bool:
        """
        Set cached value.

        Args:
            key: Cache key string
            value: Value to cache

        Returns:
            True if stored successfully
        """
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        Delete cached entry.

        Args:
            key: Cache key string

        Returns:
            True if deleted (or didn't exist)
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear all cached entries."""
        ...

    @abstractmethod
    def stats(self) -> BaseCacheStats:
        """Get cache statistics."""
        ...


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Exceptions
    "CacheError",
    "CacheCorruptError",
    "CacheVersionMismatchError",
    "CacheSerializationError",
    "CacheDiskFullError",
    "CachePermissionError",
    # Stats
    "BaseCacheStats",
    "ExtendedCacheStats",
    # Version
    "BaseVersionEnum",
    # Checksum
    "compute_xxh3_128",
    "compute_xxh3_128_hex",
    "compute_xxh32",
    "compute_content_hash",
    "HAS_XXHASH",
    # Protocol
    "CacheBackendProtocol",
]
