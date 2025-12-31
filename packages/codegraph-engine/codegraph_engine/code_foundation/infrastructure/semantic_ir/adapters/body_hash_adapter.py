"""
SHA256 Body Hash Adapter (Hexagonal Architecture - Infrastructure)

Adapter that implements BodyHashPort using SourceFile/AstTree.
"""

import hashlib
import threading
import time
from typing import Any

from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span
from codegraph_engine.code_foundation.infrastructure.semantic_ir.config import (
    BODY_HASH_LENGTH,
    BODY_HASH_PREFIX,
)


class SHA256BodyHashAdapter:
    """
    Adapter for computing SHA256 hashes of function bodies.

    Hexagonal Architecture:
    - Implements BodyHashPort (domain interface)
    - Uses SourceFile/AstTree (infrastructure)
    - Domain code is independent of this implementation
    """

    def __init__(
        self,
        source_map: dict[str, tuple[Any, Any]] | None = None,
        metrics_port: Any | None = None,
    ):
        """
        Initialize adapter.

        Args:
            source_map: Mapping of file_path -> (SourceFile, AstTree)
            metrics_port: Optional metrics port for observability
        """
        self._source_map = source_map or {}
        self._metrics_port = metrics_port
        self._cache: dict[tuple[str, int, int], str] = {}
        self._cache_lock = threading.RLock()

    def compute_hash(self, file_path: str, span: Span) -> tuple[str, str | None]:
        """
        Compute hash with caching and metrics.

        Returns:
            (hash_value, error_message)
        """
        start_time = time.perf_counter()
        cache_key = (file_path, span.start_line, span.end_line)

        # Try cache first
        with self._cache_lock:
            if cache_key in self._cache:
                duration_ms = (time.perf_counter() - start_time) * 1000
                if self._metrics_port:
                    self._metrics_port.record_computation(file_path, duration_ms, cache_hit=True)
                return self._cache[cache_key], None

        # Compute
        hash_value, error = self._compute_uncached(file_path, span)

        # Cache success
        if hash_value and not error:
            with self._cache_lock:
                self._cache[cache_key] = hash_value

        # Record metrics
        duration_ms = (time.perf_counter() - start_time) * 1000
        if self._metrics_port:
            if error:
                self._metrics_port.record_error("computation_failed", file_path)
            else:
                self._metrics_port.record_computation(file_path, duration_ms, cache_hit=False)
                self._metrics_port.record_cache_size(len(self._cache))

        return hash_value, error

    def _compute_uncached(self, file_path: str, span: Span) -> tuple[str, str | None]:
        """
        Compute hash without caching (internal).

        Returns:
            (hash_value, error_message)
        """
        # Validate source_map
        if not self._source_map:
            return None, f"source_map is required. File: {file_path}"

        if file_path not in self._source_map:
            return None, f"File '{file_path}' not in source_map. Available: {list(self._source_map.keys())}"

        # CRITICAL: Validate source_map entry is not None
        source_entry = self._source_map[file_path]
        if source_entry is None:
            return None, f"source_map['{file_path}'] is None (corrupted data)"

        # Validate source_entry is tuple
        if not isinstance(source_entry, tuple) or len(source_entry) < 2:
            return None, f"source_map['{file_path}'] has invalid format: {type(source_entry)} (expected tuple)"

        source_file, _ = source_entry

        # Validate span
        if not span:
            return None, f"Missing span for file: {file_path}"

        # Validate content
        if not source_file.content:
            return None, f"Empty content for file: {file_path}"

        lines = source_file.content.splitlines()
        start_line = span.start_line - 1  # 0-indexed
        end_line = span.end_line  # inclusive

        # Bounds checking
        if start_line < 0:
            return None, f"Invalid start_line={span.start_line} < 1"

        if end_line > len(lines):
            return None, f"Out of bounds: end_line={end_line} > total_lines={len(lines)}"

        if start_line >= end_line:
            return None, f"Invalid range: start={start_line} >= end={end_line}"

        # Extract and hash
        body_lines = lines[start_line:end_line]
        body_content = "\n".join(body_lines)

        hash_obj = hashlib.sha256(body_content.encode("utf-8"))
        hash_hex = hash_obj.hexdigest()[:BODY_HASH_LENGTH]

        return f"{BODY_HASH_PREFIX}:{hash_hex}", None

    def clear_cache(self) -> None:
        """Clear cache (thread-safe)"""
        with self._cache_lock:
            self._cache.clear()

    def update_source_map(self, source_map: dict[str, tuple[Any, Any]]) -> None:
        """
        Update source map (useful for incremental updates).

        Args:
            source_map: New source map to use
        """
        self._source_map = source_map
