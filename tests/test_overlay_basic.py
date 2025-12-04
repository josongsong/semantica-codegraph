"""
Basic integration test for Local Overlay

Simple test to verify basic overlay functionality.
"""

import pytest
from pathlib import Path
from datetime import datetime

from src.contexts.analysis_indexing.infrastructure.overlay import (
    OverlayIRBuilder,
    GraphMerger,
    ConflictResolver,
    OverlaySnapshot,
    OverlayConfig,
)


@pytest.mark.asyncio
async def test_overlay_builder_basic():
    """
    Basic test: OverlayIRBuilder can be instantiated and build overlay
    """
    # Create builder (will use real SOTA IR Builder)
    project_root = Path(__file__).parent.parent  # codegraph root
    builder = OverlayIRBuilder(project_root=project_root)
    
    # Verify builder is created
    assert builder is not None
    assert builder.ir_builder is not None
    assert builder.config is not None


@pytest.mark.asyncio
async def test_overlay_snapshot_creation():
    """
    Test: OverlaySnapshot can be created and managed
    """
    snapshot = OverlaySnapshot(
        snapshot_id="test_overlay_123",
        base_snapshot_id="base_123",
        repo_id="test_repo",
    )
    
    # Verify snapshot
    assert snapshot.snapshot_id == "test_overlay_123"
    assert snapshot.base_snapshot_id == "base_123"
    assert len(snapshot.uncommitted_files) == 0
    assert len(snapshot.affected_symbols) == 0
    
    # Test cache invalidation
    assert not snapshot.is_cache_valid()
    
    # Cache something
    snapshot.cache_merged_snapshot({"test": "data"})
    assert snapshot.is_cache_valid()
    
    # Invalidate
    snapshot._invalidate_cache()
    assert not snapshot.is_cache_valid()


@pytest.mark.asyncio
async def test_graph_merger_basic():
    """
    Test: GraphMerger can be instantiated
    """
    merger = GraphMerger()
    
    # Verify merger
    assert merger is not None
    assert merger.graph_store is not None
    assert merger.conflict_resolver is not None


@pytest.mark.asyncio
async def test_conflict_resolver_basic():
    """
    Test: ConflictResolver can resolve conflicts
    """
    from src.contexts.analysis_indexing.infrastructure.overlay.models import SymbolConflict
    
    resolver = ConflictResolver()
    
    # Create a test conflict
    conflict = SymbolConflict(
        symbol_id="test.foo",
        base_signature="(x: int, y: int) -> int",
        overlay_signature="(x: int) -> int",
        conflict_type="signature_change",
    )
    
    # Resolve
    resolved = resolver.resolve(conflict)
    
    # Verify resolution
    assert resolved.resolution == "overlay_wins"
    assert resolved.symbol_id == "test.foo"
    
    # Check if breaking change
    is_breaking = resolved.is_breaking_change()
    assert is_breaking is True  # Parameter removed


@pytest.mark.asyncio
async def test_overlay_config():
    """
    Test: OverlayConfig can be customized
    """
    config = OverlayConfig(
        max_overlay_files=100,
        invalidation_timeout=10000,
        overlay_priority=True,
    )
    
    assert config.max_overlay_files == 100
    assert config.invalidation_timeout == 10000
    assert config.overlay_priority is True


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])

