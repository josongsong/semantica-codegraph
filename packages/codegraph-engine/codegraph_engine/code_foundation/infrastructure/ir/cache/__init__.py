"""
RFC-039 P0.1.5: Common Cache Infrastructure + Backward Compatibility

Shared infrastructure for Structural IR and Semantic IR caches.

This package also re-exports the structural cache classes for backward
compatibility with existing code that imports from `...ir.cache`.

Modules:
- core: Base classes, exceptions, statistics, checksum utilities
- atomic_io: Atomic write, read-with-retry, file utilities
- (re-exported from structural_cache.py): CacheKey, IRCache, MemoryCache, DiskCache, TieredCache

Usage:
    # New common infrastructure
    from codegraph_engine.code_foundation.infrastructure.ir.cache import (
        CacheError,
        CacheCorruptError,
        BaseCacheStats,
        compute_xxh3_128,
        atomic_write_file,
    )

    # Backward compatible (structural cache)
    from codegraph_engine.code_foundation.infrastructure.ir.cache import (
        CacheKey,
        IRCache,
        MemoryCache,
        DiskCache,
        TieredCache,
        get_global_cache,
    )
"""

from .core import (
    # Exceptions
    CacheError,
    CacheCorruptError,
    CacheVersionMismatchError,
    CacheSerializationError,
    CacheDiskFullError,
    CachePermissionError,
    # Stats
    BaseCacheStats,
    ExtendedCacheStats,
    # Version
    BaseVersionEnum,
    # Checksum
    compute_xxh3_128,
    compute_xxh3_128_hex,
    compute_xxh32,
    compute_content_hash,
    HAS_XXHASH,
    # Protocol
    CacheBackendProtocol,
)

from .atomic_io import (
    atomic_write_file,
    read_with_retry,
    ensure_directory,
    safe_unlink,
    cleanup_tmp_files,
    get_file_size_safe,
)

# Re-export structural cache classes for backward compatibility
# (These were previously in cache.py, now in structural_cache.py)
from ..structural_cache import (
    # Version enums
    SchemaVersion,
    EngineVersion,
    # Key
    CacheKey,
    # Backends
    IRCacheBackend,
    MemoryCache,
    DiskCache,
    TieredCache,
    # Facade
    IRCache,
    # Global
    get_global_cache,
    set_global_cache,
)

# RFC-039 P0.5: Priority-based cache
from .priority_cache import (
    CacheEntry,
    PriorityCacheStats,
    PriorityMemoryCache,
)

__all__ = [
    # From core
    "CacheError",
    "CacheCorruptError",
    "CacheVersionMismatchError",
    "CacheSerializationError",
    "CacheDiskFullError",
    "CachePermissionError",
    "BaseCacheStats",
    "ExtendedCacheStats",
    "BaseVersionEnum",
    "compute_xxh3_128",
    "compute_xxh3_128_hex",
    "compute_xxh32",
    "compute_content_hash",
    "HAS_XXHASH",
    "CacheBackendProtocol",
    # From atomic_io
    "atomic_write_file",
    "read_with_retry",
    "ensure_directory",
    "safe_unlink",
    "cleanup_tmp_files",
    "get_file_size_safe",
    # From structural_cache (backward compatibility)
    "SchemaVersion",
    "EngineVersion",
    "CacheKey",
    "IRCacheBackend",
    "MemoryCache",
    "DiskCache",
    "TieredCache",
    "IRCache",
    "get_global_cache",
    "set_global_cache",
    # From priority_cache (RFC-039 P0.5)
    "CacheEntry",
    "PriorityCacheStats",
    "PriorityMemoryCache",
]
