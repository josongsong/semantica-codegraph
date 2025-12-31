"""
Tests for LSP Diagnostics Subscriber

SOTA-grade testing for publishDiagnostics subscription.
"""

import time
from pathlib import Path

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.diagnostics import (
    Diagnostic,
    DiagnosticRange,
    DiagnosticRelatedInfo,
    DiagnosticsAggregator,
    DiagnosticSeverity,
    DiagnosticsStore,
    DiagnosticsSubscriber,
)


class TestDiagnosticSeverity:
    """Tests for DiagnosticSeverity enum."""

    def test_severity_values(self):
        """Test severity enum values match LSP spec."""
        assert DiagnosticSeverity.ERROR == 1
        assert DiagnosticSeverity.WARNING == 2
        assert DiagnosticSeverity.INFORMATION == 3
        assert DiagnosticSeverity.HINT == 4

    def test_severity_comparison(self):
        """Test severity comparison (lower = more severe)."""
        assert DiagnosticSeverity.ERROR < DiagnosticSeverity.WARNING
        assert DiagnosticSeverity.WARNING < DiagnosticSeverity.INFORMATION
        assert DiagnosticSeverity.INFORMATION < DiagnosticSeverity.HINT


class TestDiagnosticRange:
    """Tests for DiagnosticRange class."""

    def test_from_lsp(self):
        """Test creation from LSP range object."""
        lsp_range = {
            "start": {"line": 10, "character": 5},
            "end": {"line": 10, "character": 15},
        }

        range_obj = DiagnosticRange.from_lsp(lsp_range)

        assert range_obj.start_line == 10
        assert range_obj.start_column == 5
        assert range_obj.end_line == 10
        assert range_obj.end_column == 15

    def test_from_lsp_empty(self):
        """Test creation from empty LSP range."""
        range_obj = DiagnosticRange.from_lsp({})

        assert range_obj.start_line == 0
        assert range_obj.start_column == 0


class TestDiagnostic:
    """Tests for Diagnostic class."""

    def test_from_lsp_error(self):
        """Test parsing LSP error diagnostic."""
        uri = "file:///test/file.rs"
        lsp_diag = {
            "range": {
                "start": {"line": 5, "character": 0},
                "end": {"line": 5, "character": 10},
            },
            "message": "expected `;`",
            "severity": 1,
            "source": "rust-analyzer",
            "code": "E0308",
        }

        diag = Diagnostic.from_lsp(uri, lsp_diag)

        assert diag.file_path == Path("/test/file.rs")
        assert diag.message == "expected `;`"
        assert diag.severity == DiagnosticSeverity.ERROR
        assert diag.source == "rust-analyzer"
        assert diag.code == "E0308"
        assert diag.is_error()
        assert not diag.is_warning()

    def test_from_lsp_warning(self):
        """Test parsing LSP warning diagnostic."""
        uri = "file:///test/file.go"
        lsp_diag = {
            "range": {
                "start": {"line": 10, "character": 0},
                "end": {"line": 10, "character": 5},
            },
            "message": "unused variable",
            "severity": 2,
            "source": "gopls",
        }

        diag = Diagnostic.from_lsp(uri, lsp_diag)

        assert diag.is_warning()
        assert not diag.is_error()

    def test_deprecated_tag(self):
        """Test deprecated tag detection."""
        uri = "file:///test/file.ts"
        lsp_diag = {
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
            "message": "deprecated",
            "severity": 4,
            "tags": [2],  # LSP tag 2 = deprecated
        }

        diag = Diagnostic.from_lsp(uri, lsp_diag)

        assert diag.is_deprecated()
        assert not diag.is_unnecessary()

    def test_unnecessary_tag(self):
        """Test unnecessary tag detection."""
        uri = "file:///test/file.ts"
        lsp_diag = {
            "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
            "message": "unused import",
            "severity": 4,
            "tags": [1],  # LSP tag 1 = unnecessary
        }

        diag = Diagnostic.from_lsp(uri, lsp_diag)

        assert diag.is_unnecessary()
        assert not diag.is_deprecated()

    def test_related_information(self):
        """Test parsing related information."""
        uri = "file:///test/main.rs"
        lsp_diag = {
            "range": {"start": {"line": 10, "character": 0}, "end": {"line": 10, "character": 5}},
            "message": "mismatched types",
            "severity": 1,
            "relatedInformation": [
                {
                    "location": {
                        "uri": "file:///test/lib.rs",
                        "range": {
                            "start": {"line": 5, "character": 0},
                            "end": {"line": 5, "character": 10},
                        },
                    },
                    "message": "expected due to this",
                }
            ],
        }

        diag = Diagnostic.from_lsp(uri, lsp_diag)

        assert len(diag.related_information) == 1
        related = diag.related_information[0]
        assert related.file_path == Path("/test/lib.rs")
        assert related.message == "expected due to this"


class TestDiagnosticsStore:
    """Tests for DiagnosticsStore class."""

    def setup_method(self):
        """Setup test fixtures."""
        self.store = DiagnosticsStore(ttl_seconds=60.0)

    def test_update_and_get(self):
        """Test basic update and retrieval."""
        uri = "file:///test/file.rs"
        diagnostics = [
            Diagnostic(
                file_path=Path("/test/file.rs"),
                range=DiagnosticRange(0, 0, 0, 10),
                message="error 1",
                severity=DiagnosticSeverity.ERROR,
            ),
            Diagnostic(
                file_path=Path("/test/file.rs"),
                range=DiagnosticRange(1, 0, 1, 10),
                message="warning 1",
                severity=DiagnosticSeverity.WARNING,
            ),
        ]

        self.store.update(uri, diagnostics)
        result = self.store.get(uri)

        assert len(result) == 2
        assert result[0].message == "error 1"
        assert result[1].message == "warning 1"

    def test_get_errors(self):
        """Test filtering errors."""
        uri = "file:///test/file.rs"
        diagnostics = [
            Diagnostic(
                file_path=Path("/test/file.rs"),
                range=DiagnosticRange(0, 0, 0, 10),
                message="error",
                severity=DiagnosticSeverity.ERROR,
            ),
            Diagnostic(
                file_path=Path("/test/file.rs"),
                range=DiagnosticRange(1, 0, 1, 10),
                message="warning",
                severity=DiagnosticSeverity.WARNING,
            ),
        ]

        self.store.update(uri, diagnostics)
        errors = self.store.get_errors(uri)

        assert len(errors) == 1
        assert errors[0].message == "error"

    def test_get_warnings(self):
        """Test filtering warnings."""
        uri = "file:///test/file.rs"
        diagnostics = [
            Diagnostic(
                file_path=Path("/test/file.rs"),
                range=DiagnosticRange(0, 0, 0, 10),
                message="error",
                severity=DiagnosticSeverity.ERROR,
            ),
            Diagnostic(
                file_path=Path("/test/file.rs"),
                range=DiagnosticRange(1, 0, 1, 10),
                message="warning",
                severity=DiagnosticSeverity.WARNING,
            ),
        ]

        self.store.update(uri, diagnostics)
        warnings = self.store.get_warnings(uri)

        assert len(warnings) == 1
        assert warnings[0].message == "warning"

    def test_clear_single_file(self):
        """Test clearing diagnostics for single file."""
        uri1 = "file:///test/a.rs"
        uri2 = "file:///test/b.rs"

        self.store.update(
            uri1,
            [
                Diagnostic(
                    file_path=Path("/test/a.rs"),
                    range=DiagnosticRange(0, 0, 0, 10),
                    message="error",
                )
            ],
        )
        self.store.update(
            uri2,
            [
                Diagnostic(
                    file_path=Path("/test/b.rs"),
                    range=DiagnosticRange(0, 0, 0, 10),
                    message="error",
                )
            ],
        )

        self.store.clear(uri1)

        assert len(self.store.get(uri1)) == 0
        assert len(self.store.get(uri2)) == 1

    def test_clear_all(self):
        """Test clearing all diagnostics."""
        uri1 = "file:///test/a.rs"
        uri2 = "file:///test/b.rs"

        self.store.update(
            uri1,
            [
                Diagnostic(
                    file_path=Path("/test/a.rs"),
                    range=DiagnosticRange(0, 0, 0, 10),
                    message="error",
                )
            ],
        )
        self.store.update(
            uri2,
            [
                Diagnostic(
                    file_path=Path("/test/b.rs"),
                    range=DiagnosticRange(0, 0, 0, 10),
                    message="error",
                )
            ],
        )

        self.store.clear()

        assert len(self.store.get(uri1)) == 0
        assert len(self.store.get(uri2)) == 0

    def test_statistics(self):
        """Test statistics tracking."""
        uri = "file:///test/file.rs"
        diagnostics = [
            Diagnostic(
                file_path=Path("/test/file.rs"),
                range=DiagnosticRange(0, 0, 0, 10),
                message="error",
                severity=DiagnosticSeverity.ERROR,
            ),
            Diagnostic(
                file_path=Path("/test/file.rs"),
                range=DiagnosticRange(1, 0, 1, 10),
                message="warning",
                severity=DiagnosticSeverity.WARNING,
            ),
        ]

        self.store.update(uri, diagnostics)
        stats = self.store.get_statistics()

        assert stats["files_with_diagnostics"] == 1
        assert stats["total_diagnostics"] == 2
        assert stats["error_count"] >= 1
        assert stats["warning_count"] >= 1


class TestDiagnosticsSubscriber:
    """Tests for DiagnosticsSubscriber class."""

    def setup_method(self):
        """Setup test fixtures."""
        self.subscriber = DiagnosticsSubscriber()

    def test_callback_registration(self):
        """Test callback registration and invocation."""
        received = []

        def callback(uri: str, diagnostics: list):
            received.append((uri, diagnostics))

        self.subscriber.on_diagnostics(callback)

        # Simulate publishDiagnostics
        params = {
            "uri": "file:///test/file.rs",
            "diagnostics": [
                {
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 10},
                    },
                    "message": "error",
                    "severity": 1,
                }
            ],
        }

        self.subscriber.handle_publish_diagnostics(params)

        assert len(received) == 1
        assert received[0][0] == "file:///test/file.rs"
        assert len(received[0][1]) == 1

    def test_remove_callback(self):
        """Test callback removal."""
        received = []

        def callback(uri: str, diagnostics: list):
            received.append((uri, diagnostics))

        self.subscriber.on_diagnostics(callback)
        self.subscriber.remove_callback(callback)

        params = {
            "uri": "file:///test/file.rs",
            "diagnostics": [],
        }

        self.subscriber.handle_publish_diagnostics(params)

        assert len(received) == 0

    def test_include_pattern(self):
        """Test file include pattern filtering."""
        received = []

        def callback(uri: str, diagnostics: list):
            received.append(uri)

        self.subscriber.on_diagnostics(callback)
        self.subscriber.add_include_pattern("*.rs")

        # Should be processed
        self.subscriber.handle_publish_diagnostics({"uri": "file:///test/file.rs", "diagnostics": []})
        # Should be filtered out
        self.subscriber.handle_publish_diagnostics({"uri": "file:///test/file.ts", "diagnostics": []})

        assert len(received) == 1
        assert "file.rs" in received[0]

    def test_exclude_pattern(self):
        """Test file exclude pattern filtering."""
        received = []

        def callback(uri: str, diagnostics: list):
            received.append(uri)

        self.subscriber.on_diagnostics(callback)
        self.subscriber.add_exclude_pattern("*_test.rs")

        # Should be processed
        self.subscriber.handle_publish_diagnostics({"uri": "file:///test/main.rs", "diagnostics": []})
        # Should be filtered out
        self.subscriber.handle_publish_diagnostics({"uri": "file:///test/main_test.rs", "diagnostics": []})

        assert len(received) == 1
        assert "main.rs" in received[0]

    def test_get_diagnostics(self):
        """Test getting diagnostics for a file."""
        params = {
            "uri": "file:///test/file.rs",
            "diagnostics": [
                {
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 10},
                    },
                    "message": "error",
                    "severity": 1,
                }
            ],
        }

        self.subscriber.handle_publish_diagnostics(params)

        diagnostics = self.subscriber.get_diagnostics(Path("/test/file.rs"))

        assert len(diagnostics) == 1
        assert diagnostics[0].message == "error"

    def test_get_all_errors(self):
        """Test getting all errors."""
        self.subscriber.handle_publish_diagnostics(
            {
                "uri": "file:///test/a.rs",
                "diagnostics": [
                    {
                        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
                        "message": "error 1",
                        "severity": 1,
                    }
                ],
            }
        )
        self.subscriber.handle_publish_diagnostics(
            {
                "uri": "file:///test/b.rs",
                "diagnostics": [
                    {
                        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
                        "message": "warning 1",
                        "severity": 2,
                    }
                ],
            }
        )

        errors = self.subscriber.get_all_errors()

        assert len(errors) == 1
        assert errors[0].message == "error 1"


class TestDiagnosticsAggregator:
    """Tests for DiagnosticsAggregator class."""

    def setup_method(self):
        """Setup test fixtures."""
        self.aggregator = DiagnosticsAggregator()

    def test_create_subscriber(self):
        """Test creating subscribers for different languages."""
        rust_subscriber = self.aggregator.create_subscriber("rust")
        go_subscriber = self.aggregator.create_subscriber("go")
        ts_subscriber = self.aggregator.create_subscriber("typescript")

        assert rust_subscriber is not None
        assert go_subscriber is not None
        assert ts_subscriber is not None

    def test_shared_store(self):
        """Test that all subscribers share the same store."""
        rust_subscriber = self.aggregator.create_subscriber("rust")
        go_subscriber = self.aggregator.create_subscriber("go")

        # Rust diagnostics
        rust_subscriber.handle_publish_diagnostics(
            {
                "uri": "file:///test/file.rs",
                "diagnostics": [
                    {
                        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
                        "message": "rust error",
                        "severity": 1,
                    }
                ],
            }
        )

        # Go diagnostics
        go_subscriber.handle_publish_diagnostics(
            {
                "uri": "file:///test/file.go",
                "diagnostics": [
                    {
                        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
                        "message": "go error",
                        "severity": 1,
                    }
                ],
            }
        )

        # Get all errors from aggregator
        all_errors = self.aggregator.get_all_errors()

        assert len(all_errors) == 2
        messages = {e.message for e in all_errors}
        assert "rust error" in messages
        assert "go error" in messages

    def test_statistics(self):
        """Test aggregated statistics."""
        rust_subscriber = self.aggregator.create_subscriber("rust")
        go_subscriber = self.aggregator.create_subscriber("go")

        rust_subscriber.handle_publish_diagnostics(
            {
                "uri": "file:///test/file.rs",
                "diagnostics": [
                    {
                        "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}},
                        "message": "error",
                        "severity": 1,
                    }
                ],
            }
        )

        stats = self.aggregator.get_statistics()

        assert "rust" in stats["languages"]
        assert "go" in stats["languages"]
        assert stats["files_with_diagnostics"] >= 1
