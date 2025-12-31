"""
LSP Diagnostics Subscriber

SOTA-grade diagnostics collection from LSP servers.
Supports streaming, batching, and severity filtering.

Usage:
    subscriber = DiagnosticsSubscriber()

    # Subscribe to diagnostics
    subscriber.on_diagnostics(callback)

    # Get diagnostics
    diagnostics = subscriber.get_diagnostics(file_path)
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any

from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)


class DiagnosticSeverity(IntEnum):
    """LSP Diagnostic severity levels."""

    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4


@dataclass
class DiagnosticRange:
    """Source code range for a diagnostic."""

    start_line: int  # 0-indexed
    start_column: int
    end_line: int
    end_column: int

    @classmethod
    def from_lsp(cls, range_data: dict) -> DiagnosticRange:
        """Create from LSP range object."""
        start = range_data.get("start", {})
        end = range_data.get("end", {})
        return cls(
            start_line=start.get("line", 0),
            start_column=start.get("character", 0),
            end_line=end.get("line", 0),
            end_column=end.get("character", 0),
        )


@dataclass
class DiagnosticRelatedInfo:
    """Related information for a diagnostic."""

    file_path: Path
    range: DiagnosticRange
    message: str

    @classmethod
    def from_lsp(cls, info: dict) -> DiagnosticRelatedInfo:
        """Create from LSP related information."""
        from urllib.parse import unquote, urlparse

        location = info.get("location", {})
        uri = location.get("uri", "")

        # Parse URI to path
        try:
            parsed = urlparse(uri)
            path = Path(unquote(parsed.path))
        except Exception:
            path = Path(uri)

        return cls(
            file_path=path,
            range=DiagnosticRange.from_lsp(location.get("range", {})),
            message=info.get("message", ""),
        )


@dataclass
class Diagnostic:
    """
    LSP Diagnostic representation.

    Supports:
    - Severity levels (error, warning, info, hint)
    - Source identification (compiler, linter, etc.)
    - Related information (for multi-location errors)
    - Code actions (quick fixes)
    - Tags (deprecated, unnecessary)
    """

    file_path: Path
    range: DiagnosticRange
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
    source: str | None = None
    code: str | int | None = None
    code_description_url: str | None = None
    tags: list[int] = field(default_factory=list)
    related_information: list[DiagnosticRelatedInfo] = field(default_factory=list)
    data: Any = None  # Custom data from server

    @classmethod
    def from_lsp(cls, uri: str, diag: dict) -> Diagnostic:
        """Create Diagnostic from LSP publishDiagnostics notification."""
        from urllib.parse import unquote, urlparse

        # Parse URI to path
        try:
            parsed = urlparse(uri)
            path = Path(unquote(parsed.path))
        except Exception:
            path = Path(uri)

        # Parse code description
        code_desc = diag.get("codeDescription", {})
        code_desc_url = code_desc.get("href") if code_desc else None

        # Parse related information
        related = []
        for info in diag.get("relatedInformation", []):
            try:
                related.append(DiagnosticRelatedInfo.from_lsp(info))
            except Exception:
                pass

        return cls(
            file_path=path,
            range=DiagnosticRange.from_lsp(diag.get("range", {})),
            message=diag.get("message", ""),
            severity=DiagnosticSeverity(diag.get("severity", 1)),
            source=diag.get("source"),
            code=diag.get("code"),
            code_description_url=code_desc_url,
            tags=diag.get("tags", []),
            related_information=related,
            data=diag.get("data"),
        )

    def is_error(self) -> bool:
        """Check if this is an error."""
        return self.severity == DiagnosticSeverity.ERROR

    def is_warning(self) -> bool:
        """Check if this is a warning."""
        return self.severity == DiagnosticSeverity.WARNING

    def is_deprecated(self) -> bool:
        """Check if marked as deprecated (tag 2)."""
        return 2 in self.tags

    def is_unnecessary(self) -> bool:
        """Check if marked as unnecessary (tag 1)."""
        return 1 in self.tags


DiagnosticsCallback = Callable[[str, list[Diagnostic]], None]


class DiagnosticsStore:
    """
    Thread-safe diagnostics storage.

    Features:
    - Per-file storage
    - Severity filtering
    - TTL-based expiration
    - Statistics tracking
    """

    def __init__(self, ttl_seconds: float = 300.0):
        """
        Initialize diagnostics store.

        Args:
            ttl_seconds: Time-to-live for diagnostics (default 5 minutes)
        """
        self._diagnostics: dict[str, list[Diagnostic]] = {}
        self._timestamps: dict[str, float] = {}
        self._lock = threading.RLock()
        self._ttl = ttl_seconds

        # Statistics
        self._total_received = 0
        self._error_count = 0
        self._warning_count = 0

    def update(self, uri: str, diagnostics: list[Diagnostic]) -> None:
        """Update diagnostics for a file."""
        with self._lock:
            self._diagnostics[uri] = diagnostics
            self._timestamps[uri] = time.time()

            # Update stats
            self._total_received += len(diagnostics)
            for diag in diagnostics:
                if diag.is_error():
                    self._error_count += 1
                elif diag.is_warning():
                    self._warning_count += 1

    def get(self, uri: str) -> list[Diagnostic]:
        """Get diagnostics for a file."""
        with self._lock:
            # Check TTL
            if uri in self._timestamps:
                if time.time() - self._timestamps[uri] > self._ttl:
                    self._diagnostics.pop(uri, None)
                    self._timestamps.pop(uri, None)
                    return []
            return self._diagnostics.get(uri, [])

    def get_by_path(self, file_path: Path) -> list[Diagnostic]:
        """Get diagnostics by file path."""
        uri = file_path.as_uri()
        return self.get(uri)

    def get_errors(self, uri: str | None = None) -> list[Diagnostic]:
        """Get error-level diagnostics."""
        with self._lock:
            if uri:
                return [d for d in self.get(uri) if d.is_error()]
            else:
                all_errors = []
                for diags in self._diagnostics.values():
                    all_errors.extend(d for d in diags if d.is_error())
                return all_errors

    def get_warnings(self, uri: str | None = None) -> list[Diagnostic]:
        """Get warning-level diagnostics."""
        with self._lock:
            if uri:
                return [d for d in self.get(uri) if d.is_warning()]
            else:
                all_warnings = []
                for diags in self._diagnostics.values():
                    all_warnings.extend(d for d in diags if d.is_warning())
                return all_warnings

    def get_by_severity(self, severity: DiagnosticSeverity, uri: str | None = None) -> list[Diagnostic]:
        """Get diagnostics by severity level."""
        with self._lock:
            if uri:
                return [d for d in self.get(uri) if d.severity == severity]
            else:
                results = []
                for diags in self._diagnostics.values():
                    results.extend(d for d in diags if d.severity == severity)
                return results

    def clear(self, uri: str | None = None) -> None:
        """Clear diagnostics."""
        with self._lock:
            if uri:
                self._diagnostics.pop(uri, None)
                self._timestamps.pop(uri, None)
            else:
                self._diagnostics.clear()
                self._timestamps.clear()

    def cleanup_expired(self) -> int:
        """Remove expired diagnostics. Returns count of removed entries."""
        with self._lock:
            current_time = time.time()
            expired = [uri for uri, ts in self._timestamps.items() if current_time - ts > self._ttl]
            for uri in expired:
                self._diagnostics.pop(uri, None)
                self._timestamps.pop(uri, None)
            return len(expired)

    def get_statistics(self) -> dict[str, Any]:
        """Get diagnostics statistics."""
        with self._lock:
            return {
                "files_with_diagnostics": len(self._diagnostics),
                "total_diagnostics": sum(len(d) for d in self._diagnostics.values()),
                "total_received": self._total_received,
                "error_count": self._error_count,
                "warning_count": self._warning_count,
            }


class DiagnosticsSubscriber:
    """
    Diagnostics subscriber for LSP servers.

    Features:
    - Callback-based notification
    - Async support
    - Batched updates
    - File filtering
    """

    def __init__(self, store: DiagnosticsStore | None = None):
        """Initialize subscriber with optional shared store."""
        self._store = store or DiagnosticsStore()
        self._callbacks: list[DiagnosticsCallback] = []
        self._async_callbacks: list[Callable] = []
        self._lock = threading.RLock()

        # File filters (empty = all files)
        self._include_patterns: set[str] = set()
        self._exclude_patterns: set[str] = set()

    @property
    def store(self) -> DiagnosticsStore:
        """Get diagnostics store."""
        return self._store

    def on_diagnostics(self, callback: DiagnosticsCallback) -> None:
        """
        Register callback for diagnostics updates.

        Callback receives (uri: str, diagnostics: list[Diagnostic])
        """
        with self._lock:
            self._callbacks.append(callback)

    def on_diagnostics_async(self, callback: Callable[[str, list[Diagnostic]], Any]) -> None:
        """Register async callback for diagnostics updates."""
        with self._lock:
            self._async_callbacks.append(callback)

    def remove_callback(self, callback: DiagnosticsCallback) -> None:
        """Remove a registered callback."""
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def add_include_pattern(self, pattern: str) -> None:
        """Add file pattern to include (e.g., '*.py', 'src/**/*')."""
        with self._lock:
            self._include_patterns.add(pattern)

    def add_exclude_pattern(self, pattern: str) -> None:
        """Add file pattern to exclude (e.g., '*_test.py', 'vendor/*')."""
        with self._lock:
            self._exclude_patterns.add(pattern)

    def _should_process(self, uri: str) -> bool:
        """Check if URI should be processed based on patterns."""
        import fnmatch
        from urllib.parse import unquote, urlparse

        try:
            parsed = urlparse(uri)
            path_str = unquote(parsed.path)
        except Exception:
            path_str = uri

        # Check exclude patterns first
        for pattern in self._exclude_patterns:
            if fnmatch.fnmatch(path_str, pattern):
                return False

        # If no include patterns, accept all
        if not self._include_patterns:
            return True

        # Check include patterns
        for pattern in self._include_patterns:
            if fnmatch.fnmatch(path_str, pattern):
                return True

        return False

    def handle_publish_diagnostics(self, params: dict[str, Any]) -> None:
        """
        Handle textDocument/publishDiagnostics notification.

        This is the main entry point called by LSP clients.
        """
        uri = params.get("uri", "")

        if not self._should_process(uri):
            return

        # Parse diagnostics
        raw_diagnostics = params.get("diagnostics", [])
        diagnostics = [Diagnostic.from_lsp(uri, d) for d in raw_diagnostics]

        # Update store
        self._store.update(uri, diagnostics)

        # Notify callbacks
        with self._lock:
            callbacks = self._callbacks.copy()
            async_callbacks = self._async_callbacks.copy()

        for callback in callbacks:
            try:
                callback(uri, diagnostics)
            except Exception as e:
                logger.warning(f"Diagnostics callback error: {e}")

        # Fire async callbacks
        for async_callback in async_callbacks:
            try:
                asyncio.create_task(async_callback(uri, diagnostics))
            except RuntimeError:
                # No running event loop
                pass

    def get_diagnostics(self, file_path: Path) -> list[Diagnostic]:
        """Get diagnostics for a file."""
        return self._store.get_by_path(file_path)

    def get_all_errors(self) -> list[Diagnostic]:
        """Get all error-level diagnostics."""
        return self._store.get_errors()

    def get_all_warnings(self) -> list[Diagnostic]:
        """Get all warning-level diagnostics."""
        return self._store.get_warnings()

    def get_statistics(self) -> dict[str, Any]:
        """Get diagnostics statistics."""
        return self._store.get_statistics()


class DiagnosticsAggregator:
    """
    Aggregate diagnostics from multiple LSP servers.

    Useful for polyglot projects with multiple language servers.
    """

    def __init__(self):
        """Initialize aggregator."""
        self._subscribers: dict[str, DiagnosticsSubscriber] = {}
        self._shared_store = DiagnosticsStore()
        self._lock = threading.RLock()

    def create_subscriber(self, language: str) -> DiagnosticsSubscriber:
        """
        Create a subscriber for a language.

        All subscribers share the same store for unified access.
        """
        with self._lock:
            if language not in self._subscribers:
                subscriber = DiagnosticsSubscriber(store=self._shared_store)
                self._subscribers[language] = subscriber
            return self._subscribers[language]

    def get_subscriber(self, language: str) -> DiagnosticsSubscriber | None:
        """Get subscriber for a language."""
        with self._lock:
            return self._subscribers.get(language)

    def get_all_diagnostics(self, file_path: Path) -> list[Diagnostic]:
        """Get diagnostics from all subscribers for a file."""
        return self._shared_store.get_by_path(file_path)

    def get_all_errors(self) -> list[Diagnostic]:
        """Get all errors from all language servers."""
        return self._shared_store.get_errors()

    def get_all_warnings(self) -> list[Diagnostic]:
        """Get all warnings from all language servers."""
        return self._shared_store.get_warnings()

    def get_statistics(self) -> dict[str, Any]:
        """Get aggregated statistics."""
        stats = self._shared_store.get_statistics()
        stats["languages"] = list(self._subscribers.keys())
        return stats
