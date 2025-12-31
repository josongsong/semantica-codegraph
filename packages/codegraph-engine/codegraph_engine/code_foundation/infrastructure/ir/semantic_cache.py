"""
RFC-038: Semantic IR Cache
RFC-039: Uses common cache infrastructure

SOTA-level persistent cache for Semantic IR artifacts (CFG/DFG/Signatures/Expressions).

Design Principles:
1. Content-based key (file_path excluded for Rename/Move tolerance)
2. msgpack + tuple schema (no pickle for security/compatibility)
3. 26-byte struct header with xxh3 checksum
4. Atomic write (tmp + rename) + retry with backoff
5. Version-isolated directory structure

Performance:
- Cold run: No change (2.17s for httpx)
- Warm run: 0.2~0.4s (80~90% improvement)

Architecture:
- Infrastructure Layer (cache implementation details)
- Domain models unchanged (CFG/DFG/Expression/Signature)
- Hexagonal: Port (SemanticCachePort) + Adapter (DiskSemanticCache)
- RFC-039: Uses common cache infrastructure (atomic_io, core)

Usage:
    cache = get_semantic_cache()

    key = cache.generate_key(content_hash, structural_digest, config_hash)

    # Try cache
    cached = cache.get(key)
    if cached is not None:
        relative_path, result = cached
        return result

    # Build and store
    result = builder.build(ir_doc, mode, config)
    cache.set(key, result, relative_path)
"""

from __future__ import annotations

import struct
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

# RFC-039: Import common cache infrastructure
from .cache import (
    # Checksum utilities
    compute_xxh3_128,
    compute_xxh3_128_hex,
    HAS_XXHASH,
    # Atomic I/O
    atomic_write_file,
    read_with_retry,
    ensure_directory,
    safe_unlink,
    cleanup_tmp_files,
    # Base classes (for reference, not inheritance yet)
    BaseVersionEnum,
    ExtendedCacheStats,
)

# SOTA: Fast serialization (msgpack > pickle)
try:
    import msgpack

    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False

if TYPE_CHECKING:
    from codegraph_engine.code_foundation.infrastructure.ir.build_config import BuildConfig
    from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.models import BasicFlowGraph
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import ControlFlowGraph
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import Expression
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.signature.models import SignatureEntity


# =============================================================================
# Domain: Exceptions (Semantic Layer)
# =============================================================================


class SemanticCacheError(Exception):
    """Base exception for semantic cache errors."""

    pass


class CacheCorruptError(SemanticCacheError):
    """Cache entry is corrupted (header invalid, checksum mismatch)."""

    def __init__(self, message: str, cache_path: Path | None = None):
        self.cache_path = cache_path
        super().__init__(message)


class CacheSchemaVersionMismatch(SemanticCacheError):
    """Cache entry has incompatible schema version."""

    def __init__(self, found_version: int, expected_version: int):
        self.found_version = found_version
        self.expected_version = expected_version
        super().__init__(f"Schema version mismatch: found {found_version}, expected {expected_version}")


class CacheSerializationError(SemanticCacheError):
    """Failed to serialize/deserialize cache entry."""

    pass


# =============================================================================
# Domain: Version Enums (SOTA: No hardcoding)
# =============================================================================


class SemanticEngineVersion(str, Enum):
    """
    Semantic IR builder version.

    Update this when:
    - CFG/DFG generation logic changed
    - Expression extraction changed
    - Signature inference changed
    """

    V1_0_0 = "v1"

    @classmethod
    def current(cls) -> str:
        return cls.V1_0_0.value


class SemanticSchemaVersion(str, Enum):
    """
    Cache payload schema version.

    Update this when:
    - Tuple schema layout changed
    - Field order changed
    - New fields added/removed
    """

    S1 = "s1"

    @classmethod
    def current(cls) -> str:
        return cls.S1.value


# =============================================================================
# Domain: Cached Result Model
# =============================================================================


@dataclass
class SemanticCacheResult:
    """
    Cached semantic IR result for a single file.

    Contains only cacheable artifacts (file-local, deterministic).
    Cross-file edges are NOT cached (computed at merge phase).
    """

    # Metadata
    relative_path: str  # Project-relative path (for debugging/validation)

    # CFG artifacts
    cfg_graphs: list["ControlFlowGraph"] = field(default_factory=list)

    # BFG artifacts (needed for CFG reconstruction)
    bfg_graphs: list["BasicFlowGraph"] = field(default_factory=list)

    # DFG artifacts (def-use chains)
    dfg_defs: list[tuple[int, str]] = field(default_factory=list)  # (var_id, def_node_id)
    dfg_uses: list[tuple[int, list[str]]] = field(default_factory=list)  # (var_id, [use_node_ids])

    # Expression artifacts
    expressions: list["Expression"] = field(default_factory=list)

    # Signature artifacts
    signatures: list["SignatureEntity"] = field(default_factory=list)


# =============================================================================
# Domain: Statistics (Observable)
# =============================================================================


@dataclass
class SemanticCacheStats:
    """
    Cache statistics for monitoring and observability.

    Thread-safe via lock in SemanticIRCache.
    """

    hits: int = 0
    misses: int = 0
    write_fails: int = 0
    schema_mismatches: int = 0
    corrupt_entries: int = 0
    disk_full_errors: int = 0
    total_saved_ms: float = 0.0  # Estimated time saved by cache hits

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def to_dict(self) -> dict[str, int | float]:
        """Convert to dictionary for serialization."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hit_rate, 4),
            "write_fails": self.write_fails,
            "schema_mismatches": self.schema_mismatches,
            "corrupt_entries": self.corrupt_entries,
            "disk_full_errors": self.disk_full_errors,
            "total_saved_ms": round(self.total_saved_ms, 2),
        }


# =============================================================================
# Port: SemanticCachePort (Hexagonal Architecture)
# =============================================================================


class SemanticCachePort(ABC):
    """
    Port interface for Semantic IR Cache.

    Hexagonal Architecture: Domain doesn't depend on infrastructure.
    Adapters implement this port (DiskSemanticCache, MemorySemanticCache, etc.)
    """

    @abstractmethod
    def generate_key(
        self,
        content_hash: str,
        structural_digest: str,
        config_hash: str,
    ) -> str:
        """
        Generate cache key (file_path excluded for Rename/Move tolerance).

        Args:
            content_hash: File content hash (SHA-256 or xxh3)
            structural_digest: Structural IR digest (xxh3 over packed nodes/edges)
            config_hash: Build config hash (whitelist of options affecting result)

        Returns:
            Cache key string (xxh3_128 hex)
        """
        ...

    @abstractmethod
    def get(self, key: str) -> SemanticCacheResult | None:
        """
        Get cached semantic IR result.

        Args:
            key: Cache key from generate_key()

        Returns:
            SemanticCacheResult if cache hit, None if miss
        """
        ...

    @abstractmethod
    def set(
        self,
        key: str,
        result: SemanticCacheResult,
    ) -> bool:
        """
        Store semantic IR result in cache.

        Args:
            key: Cache key from generate_key()
            result: SemanticCacheResult to cache

        Returns:
            True if stored successfully, False otherwise
        """
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear all cached entries."""
        ...

    @abstractmethod
    def stats(self) -> SemanticCacheStats:
        """Get cache statistics."""
        ...


# =============================================================================
# Infrastructure: Pack/Unpack Protocol (Tuple Schema v1)
# =============================================================================

# Header constants
MAGIC = b"SSEM"  # Smart SEmantic Map
SCHEMA_VERSION = 1
HEADER_FORMAT = ">4sH I 16s"  # big-endian: magic(4) + schema(2) + len(4) + checksum(16)
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 26 bytes


# RFC-039: Use common checksum utility
_compute_checksum = compute_xxh3_128


def _pack_cfg_graph(cfg: "ControlFlowGraph") -> tuple:
    """Pack ControlFlowGraph to tuple."""
    return (
        cfg.id,
        cfg.function_node_id,
        cfg.entry_block_id,
        cfg.exit_block_id,
        # Blocks: list of (id, kind, function_node_id, span, defined_vars, used_vars)
        tuple(
            (
                b.id,
                b.kind.value,
                b.function_node_id,
                (b.span.start_line, b.span.start_col, b.span.end_line, b.span.end_col) if b.span else None,
                tuple(b.defined_variable_ids),
                tuple(b.used_variable_ids),
            )
            for b in cfg.blocks
        ),
        # Edges: list of (src, dst, kind)
        tuple((e.source_block_id, e.target_block_id, e.kind.value) for e in cfg.edges),
    )


def _pack_bfg_graph(bfg: "BasicFlowGraph") -> tuple:
    """Pack BasicFlowGraph to tuple."""
    return (
        bfg.id,
        bfg.function_node_id,
        bfg.entry_block_id,
        bfg.exit_block_id,
        bfg.total_statements,
        bfg.is_generator,
        bfg.generator_yield_count,
        # Blocks: essential fields only
        tuple(
            (
                b.id,
                b.kind.value,
                b.function_node_id,
                (b.span.start_line, b.span.start_col, b.span.end_line, b.span.end_col) if b.span else None,
                b.statement_count,
                tuple(b.defined_variable_ids),
                tuple(b.used_variable_ids),
                b.is_break,
                b.is_continue,
                b.is_return,
            )
            for b in bfg.blocks
        ),
    )


def _pack_expression(expr: "Expression") -> tuple:
    """Pack Expression to tuple."""
    return (
        expr.id,
        expr.kind.value,
        expr.repo_id,
        expr.file_path,
        expr.function_fqn,
        (expr.span.start_line, expr.span.start_col, expr.span.end_line, expr.span.end_col),
        tuple(expr.reads_vars),
        expr.defines_var,
        expr.type_id,
        expr.inferred_type,
        expr.symbol_id,
        expr.symbol_fqn,
        expr.block_id,
        # attrs serialized as msgpack-compatible dict
        tuple(sorted(expr.attrs.items())) if expr.attrs else (),
    )


def _pack_signature(sig: "SignatureEntity") -> tuple:
    """Pack SignatureEntity to tuple."""
    return (
        sig.id,
        sig.owner_node_id,
        sig.name,
        sig.raw,
        tuple(sig.parameter_type_ids),
        sig.return_type_id,
        sig.is_async,
        sig.is_static,
        sig.visibility.value if sig.visibility else None,
        tuple(sig.throws_type_ids),
        sig.signature_hash,
        sig.raw_body_hash,
    )


def pack_semantic_result(result: SemanticCacheResult) -> bytes:
    """
    Pack SemanticCacheResult to bytes with header.

    Format:
    - Header (26 bytes): magic + schema + payload_len + checksum
    - Payload (msgpack): tuple schema

    Raises:
        CacheSerializationError: If serialization fails
    """
    if not HAS_MSGPACK:
        raise CacheSerializationError("msgpack not installed - required for semantic cache")

    try:
        # Build payload tuple
        payload_data = (
            result.relative_path,
            # CFG graphs
            tuple(_pack_cfg_graph(cfg) for cfg in result.cfg_graphs),
            # BFG graphs
            tuple(_pack_bfg_graph(bfg) for bfg in result.bfg_graphs),
            # DFG defs/uses
            tuple(result.dfg_defs),
            tuple((var_id, tuple(use_ids)) for var_id, use_ids in result.dfg_uses),
            # Expressions
            tuple(_pack_expression(expr) for expr in result.expressions),
            # Signatures
            tuple(_pack_signature(sig) for sig in result.signatures),
        )

        packed_body = msgpack.packb(payload_data, use_bin_type=True)

        # Build header
        checksum = _compute_checksum(packed_body)
        header = struct.pack(
            HEADER_FORMAT,
            MAGIC,
            SCHEMA_VERSION,
            len(packed_body),
            checksum,
        )

        return header + packed_body

    except Exception as e:
        raise CacheSerializationError(f"Failed to pack semantic result: {e}") from e


def _unpack_cfg_graph(data: tuple) -> "ControlFlowGraph":
    """Unpack ControlFlowGraph from tuple."""
    from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.cfg.models import (
        CFGBlockKind,
        CFGEdgeKind,
        ControlFlowBlock,
        ControlFlowEdge,
        ControlFlowGraph,
    )

    cfg_id, fn_id, entry_id, exit_id, blocks_data, edges_data = data

    blocks = []
    for b in blocks_data:
        b_id, b_kind, b_fn_id, span_data, defined_vars, used_vars = b
        span = Span(span_data[0], span_data[1], span_data[2], span_data[3]) if span_data else None
        blocks.append(
            ControlFlowBlock(
                id=b_id,
                kind=CFGBlockKind(b_kind),
                function_node_id=b_fn_id,
                span=span,
                defined_variable_ids=list(defined_vars),
                used_variable_ids=list(used_vars),
            )
        )

    edges = [ControlFlowEdge(source_block_id=e[0], target_block_id=e[1], kind=CFGEdgeKind(e[2])) for e in edges_data]

    return ControlFlowGraph(
        id=cfg_id,
        function_node_id=fn_id,
        entry_block_id=entry_id,
        exit_block_id=exit_id,
        blocks=blocks,
        edges=edges,
    )


def _unpack_bfg_graph(data: tuple) -> "BasicFlowGraph":
    """Unpack BasicFlowGraph from tuple."""
    from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.models import (
        BasicFlowBlock,
        BasicFlowGraph,
        BFGBlockKind,
    )

    bfg_id, fn_id, entry_id, exit_id, total_stmts, is_gen, yield_count, blocks_data = data

    blocks = []
    for b in blocks_data:
        b_id, b_kind, b_fn_id, span_data, stmt_count, defined_vars, used_vars, is_break, is_continue, is_return = b
        span = Span(span_data[0], span_data[1], span_data[2], span_data[3]) if span_data else None
        blocks.append(
            BasicFlowBlock(
                id=b_id,
                kind=BFGBlockKind(b_kind),
                function_node_id=b_fn_id,
                span=span,
                statement_count=stmt_count,
                defined_variable_ids=list(defined_vars),
                used_variable_ids=list(used_vars),
                is_break=is_break,
                is_continue=is_continue,
                is_return=is_return,
            )
        )

    return BasicFlowGraph(
        id=bfg_id,
        function_node_id=fn_id,
        entry_block_id=entry_id,
        exit_block_id=exit_id,
        blocks=blocks,
        total_statements=total_stmts,
        is_generator=is_gen,
        generator_yield_count=yield_count,
    )


def _unpack_expression(data: tuple) -> "Expression":
    """Unpack Expression from tuple."""
    from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.models import (
        Expression,
        ExprKind,
    )

    (
        expr_id,
        kind,
        repo_id,
        file_path,
        fn_fqn,
        span_data,
        reads_vars,
        defines_var,
        type_id,
        inferred_type,
        symbol_id,
        symbol_fqn,
        block_id,
        attrs_data,
    ) = data

    span = Span(span_data[0], span_data[1], span_data[2], span_data[3])
    attrs = dict(attrs_data) if attrs_data else {}

    return Expression(
        id=expr_id,
        kind=ExprKind(kind),
        repo_id=repo_id,
        file_path=file_path,
        function_fqn=fn_fqn,
        span=span,
        reads_vars=list(reads_vars),
        defines_var=defines_var,
        type_id=type_id,
        inferred_type=inferred_type,
        symbol_id=symbol_id,
        symbol_fqn=symbol_fqn,
        block_id=block_id,
        attrs=attrs,
    )


def _unpack_signature(data: tuple) -> "SignatureEntity":
    """Unpack SignatureEntity from tuple."""
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.signature.models import (
        SignatureEntity,
        Visibility,
    )

    (
        sig_id,
        owner_id,
        name,
        raw,
        param_types,
        return_type,
        is_async,
        is_static,
        visibility_val,
        throws_types,
        sig_hash,
        body_hash,
    ) = data

    return SignatureEntity(
        id=sig_id,
        owner_node_id=owner_id,
        name=name,
        raw=raw,
        parameter_type_ids=list(param_types),
        return_type_id=return_type,
        is_async=is_async,
        is_static=is_static,
        visibility=Visibility(visibility_val) if visibility_val else None,
        throws_type_ids=list(throws_types),
        signature_hash=sig_hash,
        raw_body_hash=body_hash,
    )


def unpack_semantic_result(data: bytes) -> SemanticCacheResult:
    """
    Unpack SemanticCacheResult from bytes with header validation.

    Raises:
        CacheCorruptError: If header/checksum validation fails
        CacheSchemaVersionMismatch: If schema version doesn't match
        CacheSerializationError: If deserialization fails
    """
    if not HAS_MSGPACK:
        raise CacheSerializationError("msgpack not installed - required for semantic cache")

    # Validate header size
    if len(data) < HEADER_SIZE:
        raise CacheCorruptError(f"Data too short: {len(data)} < {HEADER_SIZE} bytes")

    # Parse header
    try:
        magic, schema_ver, payload_len, stored_checksum = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
    except struct.error as e:
        raise CacheCorruptError(f"Invalid header format: {e}")

    # Validate magic
    if magic != MAGIC:
        raise CacheCorruptError(f"Invalid magic bytes: {magic!r} != {MAGIC!r}")

    # Validate schema version
    if schema_ver != SCHEMA_VERSION:
        raise CacheSchemaVersionMismatch(schema_ver, SCHEMA_VERSION)

    # Extract payload
    payload = data[HEADER_SIZE : HEADER_SIZE + payload_len]
    if len(payload) < payload_len:
        raise CacheCorruptError(f"Payload truncated: {len(payload)} < {payload_len}")

    # Validate checksum
    actual_checksum = _compute_checksum(payload)
    if actual_checksum != stored_checksum:
        raise CacheCorruptError("Checksum mismatch - cache entry corrupted")

    # Unpack msgpack
    try:
        unpacked = msgpack.unpackb(payload, raw=False, use_list=True)
    except Exception as e:
        raise CacheSerializationError(f"Failed to unpack msgpack: {e}") from e

    # Destructure payload
    try:
        (
            relative_path,
            cfg_data,
            bfg_data,
            dfg_defs_data,
            dfg_uses_data,
            expr_data,
            sig_data,
        ) = unpacked
    except (ValueError, TypeError) as e:
        raise CacheSerializationError(f"Invalid payload structure: {e}") from e

    # Reconstruct objects
    try:
        return SemanticCacheResult(
            relative_path=relative_path,
            cfg_graphs=[_unpack_cfg_graph(cfg) for cfg in cfg_data],
            bfg_graphs=[_unpack_bfg_graph(bfg) for bfg in bfg_data],
            dfg_defs=[(d[0], d[1]) for d in dfg_defs_data],
            dfg_uses=[(u[0], list(u[1])) for u in dfg_uses_data],
            expressions=[_unpack_expression(expr) for expr in expr_data],
            signatures=[_unpack_signature(sig) for sig in sig_data],
        )
    except Exception as e:
        raise CacheSerializationError(f"Failed to reconstruct objects: {e}") from e


# =============================================================================
# Adapter: DiskSemanticCache (Infrastructure Layer)
# =============================================================================


class DiskSemanticCache(SemanticCachePort):
    """
    Disk-based Semantic IR Cache.

    Features:
    - Content-based key (file_path excluded, Rename/Move tolerant)
    - xxh3 checksum validation (26-byte header)
    - msgpack + tuple schema (no pickle)
    - Atomic write (tmp + rename)
    - Corrupt entry fallback with auto-delete
    - Version-isolated directory structure
    - Retry with backoff for race conditions

    Thread-safety:
    - Read: Concurrent OK (retry on transient errors)
    - Write: Atomic (file-level)
    - Stats: Lock-protected
    """

    # Retry settings
    MAX_RETRIES = 3
    RETRY_DELAY_MS = 20

    def __init__(
        self,
        base_dir: Path | None = None,
        engine_version: str | None = None,
        schema_version: str | None = None,
    ):
        """
        Initialize disk-based semantic cache.

        Args:
            base_dir: Base cache directory (default: ~/.cache/codegraph/sem_ir)
            engine_version: Engine version for directory isolation
            schema_version: Schema version for directory isolation
        """
        if base_dir is None:
            base_dir = Path.home() / ".cache" / "codegraph" / "sem_ir"

        if engine_version is None:
            engine_version = SemanticEngineVersion.current()
        if schema_version is None:
            schema_version = SemanticSchemaVersion.current()

        # Version-isolated directory
        self._cache_dir = base_dir / engine_version / schema_version
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._stats = SemanticCacheStats()

    @property
    def cache_dir(self) -> Path:
        """Get cache directory (for testing/debugging)."""
        return self._cache_dir

    def generate_key(
        self,
        content_hash: str,
        structural_digest: str,
        config_hash: str,
    ) -> str:
        """
        Generate cache key (file_path excluded for Rename/Move tolerance).

        RFC-039: Uses common compute_xxh3_128_hex utility.
        Key = xxh3_128(content_hash + structural_digest + config_hash)
        """
        combined = f"{content_hash}{structural_digest}{config_hash}"
        # RFC-039: Use common checksum utility
        return compute_xxh3_128_hex(combined.encode())

    def get(self, key: str) -> SemanticCacheResult | None:
        """
        Get cached semantic IR result with retry for transient errors.

        Returns:
            SemanticCacheResult if cache hit, None if miss
        """
        cache_path = self._cache_dir / f"{key}.sem"

        if not cache_path.exists():
            with self._lock:
                self._stats.misses += 1
            return None

        # Retry with backoff for race conditions
        for attempt in range(self.MAX_RETRIES):
            try:
                data = cache_path.read_bytes()
                result = unpack_semantic_result(data)

                with self._lock:
                    self._stats.hits += 1
                return result

            except CacheSchemaVersionMismatch:
                with self._lock:
                    self._stats.schema_mismatches += 1
                cache_path.unlink(missing_ok=True)
                return None

            except CacheCorruptError:
                with self._lock:
                    self._stats.corrupt_entries += 1
                cache_path.unlink(missing_ok=True)
                return None

            except (PermissionError, FileNotFoundError):
                # Transient error (file being replaced by another process)
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY_MS / 1000)
                    continue
                with self._lock:
                    self._stats.misses += 1
                return None

            except CacheSerializationError:
                with self._lock:
                    self._stats.corrupt_entries += 1
                cache_path.unlink(missing_ok=True)
                return None

            except Exception:
                with self._lock:
                    self._stats.corrupt_entries += 1
                cache_path.unlink(missing_ok=True)
                return None

        with self._lock:
            self._stats.misses += 1
        return None

    def set(
        self,
        key: str,
        result: SemanticCacheResult,
    ) -> bool:
        """
        Store semantic IR result with atomic write.

        RFC-039: Uses common atomic_write_file utility.

        Returns:
            True if stored successfully, False otherwise
        """
        cache_path = self._cache_dir / f"{key}.sem"

        # Write-once: skip if already exists
        if cache_path.exists():
            return True

        try:
            data = pack_semantic_result(result)

            # RFC-039: Use common atomic write utility
            from .cache import CacheDiskFullError, CachePermissionError

            try:
                success = atomic_write_file(cache_path, data, use_flock=False, fsync=True)
                return success
            except CacheDiskFullError:
                with self._lock:
                    self._stats.disk_full_errors += 1
                return False
            except CachePermissionError:
                with self._lock:
                    self._stats.disk_full_errors += 1
                return False

        except CacheSerializationError:
            with self._lock:
                self._stats.write_fails += 1
            return False

        except Exception:
            with self._lock:
                self._stats.write_fails += 1
            return False

    def clear(self) -> None:
        """Clear all cached entries.

        RFC-039: Uses common cleanup_tmp_files utility.
        """
        # Clear cache files
        for cache_file in self._cache_dir.glob("*.sem"):
            safe_unlink(cache_file)

        # RFC-039: Clean tmp files using common utility
        cleanup_tmp_files(self._cache_dir, suffix=".sem")

        with self._lock:
            self._stats = SemanticCacheStats()

    def stats(self) -> SemanticCacheStats:
        """Get cache statistics (thread-safe copy)."""
        with self._lock:
            return SemanticCacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                write_fails=self._stats.write_fails,
                schema_mismatches=self._stats.schema_mismatches,
                corrupt_entries=self._stats.corrupt_entries,
                disk_full_errors=self._stats.disk_full_errors,
                total_saved_ms=self._stats.total_saved_ms,
            )

    def record_time_saved(self, saved_ms: float) -> None:
        """Record time saved by cache hit (for telemetry)."""
        with self._lock:
            self._stats.total_saved_ms += saved_ms


# =============================================================================
# Global Singleton (Lazy Initialization)
# =============================================================================

_global_semantic_cache: DiskSemanticCache | None = None
_global_cache_lock = threading.Lock()


def get_semantic_cache() -> DiskSemanticCache:
    """
    Get global semantic IR cache instance (lazy singleton).

    Thread-safe initialization.

    Returns:
        DiskSemanticCache instance
    """
    global _global_semantic_cache

    if _global_semantic_cache is None:
        with _global_cache_lock:
            # Double-checked locking
            if _global_semantic_cache is None:
                _global_semantic_cache = DiskSemanticCache()

    return _global_semantic_cache


def reset_semantic_cache() -> None:
    """
    Reset global semantic cache (for testing).

    Clears both the singleton reference and cache contents.
    """
    global _global_semantic_cache

    with _global_cache_lock:
        if _global_semantic_cache is not None:
            _global_semantic_cache.clear()
        _global_semantic_cache = None


def set_semantic_cache(cache: DiskSemanticCache) -> None:
    """
    Set global semantic cache (for testing/dependency injection).

    Args:
        cache: DiskSemanticCache instance to use
    """
    global _global_semantic_cache

    with _global_cache_lock:
        _global_semantic_cache = cache


# =============================================================================
# Helper Functions for Worker Integration
# =============================================================================


def compute_structural_digest(ir_doc: "IRDocument") -> str:
    """
    Compute stable digest over structural IR.

    Uses xxh3 for speed (not crypto-secure, but fast).
    Includes nodes and edges in deterministic order.

    Args:
        ir_doc: IRDocument with nodes and edges

    Returns:
        xxh3_128 hex digest (32 chars)
    """
    if HAS_XXHASH:
        hasher = xxhash.xxh3_128()

        # Sort nodes by id for determinism
        for node in sorted(ir_doc.nodes, key=lambda n: n.id):
            hasher.update(f"{node.id}:{node.kind.value}:{node.name}".encode())

        # Sort edges by (src, dst, kind)
        for edge in sorted(ir_doc.edges, key=lambda e: (e.source_id, e.target_id, e.kind.value)):
            hasher.update(f"{edge.source_id}:{edge.target_id}:{edge.kind.value}".encode())

        return hasher.hexdigest()
    else:
        # Fallback: SHA-256
        import hashlib

        hasher = hashlib.sha256()

        for node in sorted(ir_doc.nodes, key=lambda n: n.id):
            hasher.update(f"{node.id}:{node.kind.value}:{node.name}".encode())

        for edge in sorted(ir_doc.edges, key=lambda e: (e.source_id, e.target_id, e.kind.value)):
            hasher.update(f"{edge.source_id}:{edge.target_id}:{edge.kind.value}".encode())

        return hasher.hexdigest()[:32]


def compute_config_hash(
    mode: "SemanticIrBuildMode",
    config: "BuildConfig",
) -> str:
    """
    Compute hash of config options that affect semantic IR result.

    Whitelist approach: Only include options that affect the output.
    Excluding irrelevant options (parallel_workers, etc.) prevents cache misses.

    Args:
        mode: SemanticIrBuildMode (QUICK/PR/FULL)
        config: BuildConfig with semantic options

    Returns:
        xxh3_64 hex digest (16 chars)
    """
    from codegraph_engine.code_foundation.domain.semantic_ir.mode import SemanticIrBuildMode

    if HAS_XXHASH:
        hasher = xxhash.xxh3_64()
    else:
        hasher = hashlib.sha256()

    # Mode
    hasher.update(mode.value.encode())

    # Config options (whitelist - only those affecting result)
    hasher.update(str(config.dfg_function_loc_threshold).encode())
    hasher.update(str(config.cfg).encode())
    hasher.update(str(config.dfg).encode())
    hasher.update(str(config.ssa).encode())
    hasher.update(str(config.expressions).encode())
    hasher.update(str(config.bfg).encode())
    hasher.update(config.semantic_tier.value.encode())

    if HAS_XXHASH:
        return hasher.hexdigest()
    else:
        return hasher.hexdigest()[:16]


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Exceptions
    "SemanticCacheError",
    "CacheCorruptError",
    "CacheSchemaVersionMismatch",
    "CacheSerializationError",
    # Models
    "SemanticCacheResult",
    "SemanticCacheStats",
    # Versions
    "SemanticEngineVersion",
    "SemanticSchemaVersion",
    # Port
    "SemanticCachePort",
    # Adapter
    "DiskSemanticCache",
    # Pack/Unpack
    "pack_semantic_result",
    "unpack_semantic_result",
    # Global
    "get_semantic_cache",
    "reset_semantic_cache",
    "set_semantic_cache",
    # Helpers
    "compute_structural_digest",
    "compute_config_hash",
    # Constants
    "SCHEMA_VERSION",
    "HEADER_SIZE",
]
