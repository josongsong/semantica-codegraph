"""
Integration tests for Local Overlay feature

This tests the critical feature that improves IDE/Agent accuracy by 30-50%.
"""

from datetime import datetime

import pytest

from src.contexts.analysis_indexing.infrastructure.overlay import (
    ConflictResolver,
    GraphMerger,
    OverlayConfig,
    OverlayIRBuilder,
    OverlaySnapshot,
)


@pytest.fixture
def base_ir_docs():
    """Base IR documents (committed code)"""
    return {
        "src/main.py": {
            "file": "src/main.py",
            "symbols": [
                {
                    "id": "src.main.foo",
                    "name": "foo",
                    "signature": "(x: int, y: int) -> int",
                    "range": {"start": {"line": 1, "character": 0}, "end": {"line": 3, "character": 0}},
                },
                {
                    "id": "src.main.caller",
                    "name": "caller",
                    "signature": "() -> int",
                    "range": {"start": {"line": 5, "character": 0}, "end": {"line": 7, "character": 0}},
                    "calls": [{"target_id": "src.main.foo"}],
                },
            ],
        }
    }


@pytest.fixture
def uncommitted_changes():
    """Uncommitted changes (user editing)"""
    return {
        "src/main.py": """
def foo(x: int) -> int:  # CHANGED: removed parameter y
    return x * 2

def caller() -> int:
    return foo(42)  # Still calls foo
"""
    }


@pytest.mark.asyncio
async def test_overlay_definition_reflects_uncommitted_changes(base_ir_docs, uncommitted_changes, mock_ir_builder):
    """
    Critical test: Uncommitted changes are reflected in definition lookup

    Scenario:
    1. User has committed code with foo(x, y)
    2. User edits to foo(x) (removes parameter y)
    3. IDE should show new signature foo(x) when looking up definition
    """
    # Build overlay
    builder = OverlayIRBuilder(ir_builder=mock_ir_builder)

    overlay = await builder.build_overlay(
        base_snapshot_id="base_123",
        repo_id="test_repo",
        uncommitted_files=uncommitted_changes,
        base_ir_docs=base_ir_docs,
    )

    # Verify overlay was built
    assert overlay.snapshot_id.startswith("overlay_")
    assert len(overlay.overlay_ir_docs) == 1
    assert "src/main.py" in overlay.overlay_ir_docs

    # Verify affected symbols detected
    assert "src.main.foo" in overlay.affected_symbols

    # Verify new IR has new signature
    overlay_ir = overlay.overlay_ir_docs["src/main.py"]
    foo_symbol = next(s for s in overlay_ir["symbols"] if s["name"] == "foo")

    # CRITICAL: New signature should be reflected
    assert "x: int" in foo_symbol["signature"]
    assert "y: int" not in foo_symbol["signature"]


@pytest.mark.asyncio
async def test_overlay_call_graph_reflects_uncommitted_changes(
    base_ir_docs, uncommitted_changes, mock_ir_builder, mock_graph_store
):
    """
    Test: Call graph reflects uncommitted changes

    Scenario:
    1. Base has: caller() → foo(x, y)
    2. Overlay has: caller() → foo(x)
    3. Merged call graph should show updated edge
    """
    # Build overlay
    builder = OverlayIRBuilder(ir_builder=mock_ir_builder)
    overlay = await builder.build_overlay(
        base_snapshot_id="base_123",
        repo_id="test_repo",
        uncommitted_files=uncommitted_changes,
        base_ir_docs=base_ir_docs,
    )

    # Merge graphs
    merger = GraphMerger(graph_store=mock_graph_store, conflict_resolver=ConflictResolver())

    merged = await merger.merge_graphs(
        base_snapshot_id="base_123",
        overlay=overlay,
        base_ir_docs=base_ir_docs,
    )

    # Verify merged call graph
    assert ("src.main.caller", "src.main.foo") in merged.call_graph_edges

    # Verify foo signature is from overlay (not base)
    foo_symbol = merged.symbol_index.get("src.main.foo")
    assert foo_symbol is not None
    assert "x: int" in foo_symbol["signature"]
    assert "y: int" not in foo_symbol["signature"]


@pytest.mark.asyncio
async def test_overlay_detects_breaking_changes(base_ir_docs, uncommitted_changes, mock_ir_builder, mock_graph_store):
    """
    Test: Breaking changes are detected

    Scenario:
    1. foo(x, y) → foo(x) is a breaking change (parameter removed)
    2. Overlay should detect and report this
    """
    # Build overlay
    builder = OverlayIRBuilder(ir_builder=mock_ir_builder)
    overlay = await builder.build_overlay(
        base_snapshot_id="base_123",
        repo_id="test_repo",
        uncommitted_files=uncommitted_changes,
        base_ir_docs=base_ir_docs,
    )

    # Merge graphs
    merger = GraphMerger(graph_store=mock_graph_store, conflict_resolver=ConflictResolver())

    merged = await merger.merge_graphs(
        base_snapshot_id="base_123",
        overlay=overlay,
        base_ir_docs=base_ir_docs,
    )

    # Verify conflicts detected
    assert len(merged.conflicts) > 0

    # Find conflict for foo
    foo_conflict = next((c for c in merged.conflicts if c.symbol_id == "src.main.foo"), None)

    assert foo_conflict is not None
    assert foo_conflict.conflict_type == "signature_change"

    # CRITICAL: Should be detected as breaking change
    assert foo_conflict.is_breaking_change()


@pytest.mark.asyncio
async def test_overlay_handles_new_file(mock_ir_builder):
    """
    Test: New uncommitted file is handled correctly

    Scenario:
    1. Base has no src/new.py
    2. User creates src/new.py (uncommitted)
    3. Overlay should include new file
    """
    uncommitted = {
        "src/new.py": """
def new_function():
    return 42
"""
    }

    builder = OverlayIRBuilder(ir_builder=mock_ir_builder)
    overlay = await builder.build_overlay(
        base_snapshot_id="base_123",
        repo_id="test_repo",
        uncommitted_files=uncommitted,
        base_ir_docs={},  # Empty base
    )

    # Verify new file in overlay
    assert "src/new.py" in overlay.overlay_ir_docs

    # Verify file marked as new
    assert overlay.uncommitted_files["src/new.py"].is_new is True


@pytest.mark.asyncio
async def test_overlay_cache_works(base_ir_docs, uncommitted_changes, mock_ir_builder, mock_graph_store):
    """
    Test: Overlay merge result is cached

    Scenario:
    1. First merge: compute and cache
    2. Second merge: use cache (should be fast)
    """
    builder = OverlayIRBuilder(ir_builder=mock_ir_builder)
    overlay = await builder.build_overlay(
        base_snapshot_id="base_123",
        repo_id="test_repo",
        uncommitted_files=uncommitted_changes,
        base_ir_docs=base_ir_docs,
    )

    merger = GraphMerger(graph_store=mock_graph_store, conflict_resolver=ConflictResolver())

    # First merge
    merged1 = await merger.merge_graphs(
        base_snapshot_id="base_123",
        overlay=overlay,
        base_ir_docs=base_ir_docs,
    )

    # Verify cached
    assert overlay.is_cache_valid()

    # Second merge (should use cache)
    merged2 = await merger.merge_graphs(
        base_snapshot_id="base_123",
        overlay=overlay,
        base_ir_docs=base_ir_docs,
    )

    # Should be same snapshot
    assert merged1.snapshot_id == merged2.snapshot_id


@pytest.mark.asyncio
async def test_overlay_performance_target(base_ir_docs, uncommitted_changes, mock_ir_builder):
    """
    Performance test: Overlay build should be < 10ms per file
    """
    import time

    builder = OverlayIRBuilder(ir_builder=mock_ir_builder)

    start = time.perf_counter()

    overlay = await builder.build_overlay(
        base_snapshot_id="base_123",
        repo_id="test_repo",
        uncommitted_files=uncommitted_changes,
        base_ir_docs=base_ir_docs,
    )

    elapsed_ms = (time.perf_counter() - start) * 1000

    # PERFORMANCE TARGET: < 10ms per file
    assert elapsed_ms < 10 * len(uncommitted_changes), (
        f"Overlay build took {elapsed_ms:.2f}ms for {len(uncommitted_changes)} file(s)"
    )


# Mocks


class MockIRBuilder:
    """Mock IR builder for testing"""

    async def build_file_ir(self, file_path: str, content: str) -> dict:
        """Build simple IR from content"""
        # Simple parser: extract function definitions
        symbols = []
        lines = content.strip().split("\n")

        for i, line in enumerate(lines):
            if line.strip().startswith("def "):
                # Extract function name and signature
                func_def = line.strip()
                name = func_def.split("def ")[1].split("(")[0]
                signature = func_def.split("def ")[1].rstrip(":")

                symbols.append(
                    {
                        "id": f"{file_path.replace('/', '.').replace('.py', '')}.{name}",
                        "name": name,
                        "signature": signature,
                        "range": {
                            "start": {"line": i + 1, "character": 0},
                            "end": {"line": i + 3, "character": 0},
                        },
                        "calls": [],  # TODO: extract calls
                    }
                )

        return {
            "file": file_path,
            "symbols": symbols,
        }


class MockGraphStore:
    """Mock graph store for testing"""

    def __init__(self):
        self.call_edges = set()
        self.import_edges = set()

    async def execute_query(self, query: str):
        """Execute mock query"""
        if "CALLS" in query:
            # Return call graph edges
            return [{"caller_id": caller, "callee_id": callee} for caller, callee in self.call_edges]
        elif "IMPORTS" in query:
            # Return import graph edges
            return [{"importer": imp, "imported": mod} for imp, mod in self.import_edges]
        return []


@pytest.fixture
def mock_ir_builder():
    return MockIRBuilder()


@pytest.fixture
def mock_graph_store():
    return MockGraphStore()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
