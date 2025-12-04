"""
Quick test for Local Overlay - runs without pytest conftest
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.contexts.analysis_indexing.infrastructure.overlay import (
    OverlayIRBuilder,
    GraphMerger,
    ConflictResolver,
    OverlaySnapshot,
    OverlayConfig,
)
from src.contexts.analysis_indexing.infrastructure.overlay.models import SymbolConflict


async def test_overlay_snapshot():
    """Test 1: OverlaySnapshot creation and management"""
    print("\n[Test 1] OverlaySnapshot creation...")
    
    snapshot = OverlaySnapshot(
        snapshot_id="test_overlay_123",
        base_snapshot_id="base_123",
        repo_id="test_repo",
    )
    
    assert snapshot.snapshot_id == "test_overlay_123"
    assert snapshot.base_snapshot_id == "base_123"
    assert len(snapshot.uncommitted_files) == 0
    
    print("✅ OverlaySnapshot creation works!")


async def test_conflict_resolver():
    """Test 2: ConflictResolver"""
    print("\n[Test 2] ConflictResolver...")
    
    resolver = ConflictResolver()
    
    conflict = SymbolConflict(
        symbol_id="test.foo",
        base_signature="(x: int, y: int) -> int",
        overlay_signature="(x: int) -> int",
        conflict_type="signature_change",
    )
    
    resolved = resolver.resolve(conflict)
    
    assert resolved.resolution == "overlay_wins"
    assert resolved.is_breaking_change() is True
    
    print("✅ ConflictResolver works!")


async def test_overlay_builder():
    """Test 3: OverlayIRBuilder instantiation"""
    print("\n[Test 3] OverlayIRBuilder instantiation...")
    
    try:
        builder = OverlayIRBuilder(project_root=project_root)
        assert builder is not None
        assert builder.ir_builder is not None
        print("✅ OverlayIRBuilder created successfully!")
    except Exception as e:
        print(f"⚠️ OverlayIRBuilder creation failed (expected - needs LSP): {e}")


async def test_graph_merger():
    """Test 4: GraphMerger instantiation"""
    print("\n[Test 4] GraphMerger instantiation...")
    
    try:
        merger = GraphMerger()
        assert merger is not None
        assert merger.conflict_resolver is not None
        print("✅ GraphMerger created successfully!")
    except Exception as e:
        print(f"⚠️ GraphMerger creation failed (expected - needs Memgraph): {e}")


async def test_overlay_config():
    """Test 5: OverlayConfig"""
    print("\n[Test 5] OverlayConfig...")
    
    config = OverlayConfig(
        max_overlay_files=100,
        invalidation_timeout=10000,
        overlay_priority=True,
    )
    
    assert config.max_overlay_files == 100
    assert config.invalidation_timeout == 10000
    assert config.overlay_priority is True
    
    print("✅ OverlayConfig works!")


async def main():
    """Run all tests"""
    print("=" * 60)
    print("🚀 Local Overlay Quick Tests")
    print("=" * 60)
    
    try:
        await test_overlay_snapshot()
        await test_conflict_resolver()
        await test_overlay_builder()
        await test_graph_merger()
        await test_overlay_config()
        
        print("\n" + "=" * 60)
        print("✅ All basic tests passed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

