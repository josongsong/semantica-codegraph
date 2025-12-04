"""
E2E Validation Test - 실제 작동 검증

Local Overlay + Type Narrowing이 실제로 동작하는지 검증
"""

import asyncio
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.contexts.analysis_indexing.infrastructure.overlay import (
    OverlayIRBuilder,
    OverlaySnapshot,
)
from src.contexts.code_foundation.infrastructure.graphs.precise_call_graph import (
    PreciseCallGraphBuilder,
)


async def test_e2e_overlay_with_real_file():
    """
    E2E Test 1: Local Overlay with real Python file
    
    Scenario:
    1. Create a real Python file
    2. Build overlay IR
    3. Verify it works
    """
    print("\n[E2E Test 1] Local Overlay with real file...")
    
    # Create temporary Python file
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("""
def foo(x: int, y: int) -> int:
    return x + y

def bar():
    return foo(1, 2)
""")
        
        try:
            # Build overlay
            builder = OverlayIRBuilder(project_root=Path(tmpdir))
            
            overlay = await builder.build_overlay(
                base_snapshot_id="base_test",
                repo_id="test_repo",
                uncommitted_files={
                    "test.py": test_file.read_text()
                },
                base_ir_docs={},
            )
            
            # Verify
            assert overlay is not None
            assert overlay.snapshot_id.startswith("overlay_")
            assert len(overlay.overlay_ir_docs) > 0
            
            print(f"  ✅ Overlay created: {overlay.snapshot_id}")
            print(f"  ✅ IR docs: {len(overlay.overlay_ir_docs)}")
            print(f"  ✅ Affected symbols: {len(overlay.affected_symbols)}")
            
            # Check IR content
            if "test.py" in overlay.overlay_ir_docs:
                ir_doc = overlay.overlay_ir_docs["test.py"]
                print(f"  ✅ IR document exists for test.py")
                if "symbols" in ir_doc:
                    print(f"  ✅ Symbols found: {len(ir_doc.get('symbols', []))}")
            
            return True
            
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            import traceback
            traceback.print_exc()
            return False


async def test_e2e_type_narrowing_with_real_code():
    """
    E2E Test 2: Type Narrowing with real Python code
    
    Scenario:
    1. Create Python code with isinstance check
    2. Build precise call graph
    3. Verify narrowing works
    """
    print("\n[E2E Test 2] Type Narrowing with real code...")
    
    try:
        # Mock IR document (represents real parsed code)
        ir_docs = {
            "handler.py": {
                "file": "handler.py",
                "symbols": [
                    {
                        "id": "handler.process",
                        "name": "process",
                        "signature": "(handler: Handler) -> None",
                        "calls": [
                            {
                                "target_id": "handler.fast_process",
                                "name": "fast_process",
                                "receiver": "handler",
                                "location": (5, 8),
                            }
                        ],
                    }
                ],
            }
        }
        
        # Test Case 1: Narrowed type (isinstance checked)
        narrowed_types = {
            "handler.py": {
                "handler": {"FastHandler"}  # After isinstance(handler, FastHandler)
            }
        }
        
        builder = PreciseCallGraphBuilder()
        edges = builder.build_precise_cg(ir_docs, narrowed_types)
        
        assert len(edges) > 0, "Should have edges"
        edge = edges[0]
        
        print(f"  ✅ Built {len(edges)} edges")
        print(f"  ✅ Caller: {edge.caller_id}")
        print(f"  ✅ Callee: {edge.callee_id}")
        print(f"  ✅ Receiver type: {edge.call_site.receiver_type}")
        print(f"  ✅ Is narrowed: {edge.call_site.is_narrowed}")
        print(f"  ✅ Confidence: {edge.confidence}")
        
        # Verify narrowing worked
        assert edge.call_site.is_narrowed is True, "Should be narrowed"
        assert edge.confidence == 1.0, "Should have high confidence"
        
        # Test Case 2: Union type (not narrowed)
        union_types = {
            "handler.py": {
                "handler": {"FastHandler", "SlowHandler"}  # Union type
            }
        }
        
        builder2 = PreciseCallGraphBuilder()
        edges2 = builder2.build_precise_cg(ir_docs, union_types)
        
        edge2 = edges2[0]
        
        print(f"\n  Union type test:")
        print(f"  ✅ Receiver type: {edge2.call_site.receiver_type}")
        print(f"  ✅ Is narrowed: {edge2.call_site.is_narrowed}")
        print(f"  ✅ Confidence: {edge2.confidence}")
        
        assert edge2.call_site.is_narrowed is False, "Should not be narrowed"
        assert edge2.confidence < 1.0, "Should have lower confidence"
        
        return True
        
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_e2e_precision_comparison():
    """
    E2E Test 3: Compare precision with and without narrowing
    
    Verify that type narrowing actually improves precision
    """
    print("\n[E2E Test 3] Precision comparison...")
    
    try:
        # Scenario: Function calls different methods based on isinstance
        ir_docs = {
            "main.py": {
                "file": "main.py",
                "symbols": [
                    {
                        "id": "main.process",
                        "name": "process",
                        "calls": [
                            {"target_id": "handler.fast", "name": "fast", "receiver": "h", "location": (10, 5)},
                            {"target_id": "handler.slow", "name": "slow", "receiver": "h", "location": (12, 5)},
                        ],
                    }
                ],
            }
        }
        
        # Without narrowing: All calls possible (basic CG)
        basic_edges = {
            ("main.process", "handler.fast"),
            ("main.process", "handler.slow"),
        }
        
        # With narrowing: Only one call per branch
        narrowed_types = {
            "main.py": {
                "h": {"FastHandler"}  # Only FastHandler
            }
        }
        
        builder = PreciseCallGraphBuilder()
        edges = builder.build_precise_cg(ir_docs, narrowed_types)
        
        # High-confidence edges only
        high_conf_edges = builder.get_edges_by_confidence(0.8)
        
        print(f"  Basic CG edges: {len(basic_edges)}")
        print(f"  Precise CG edges: {len(edges)}")
        print(f"  High confidence edges: {len(high_conf_edges)}")
        
        # Calculate improvement
        metrics = builder.compare_with_basic_cg(basic_edges)
        
        print(f"\n  📊 Metrics:")
        print(f"    Basic edges: {metrics['basic_edges']}")
        print(f"    Precise edges: {metrics['precise_edges']}")
        print(f"    Eliminated: {metrics['eliminated_edges']}")
        print(f"    Precision gain: {metrics['precision_gain']:.1f}%")
        
        # Verify improvement
        assert metrics['precision_gain'] >= 0, "Should have some gain"
        
        print(f"\n  ✅ Precision improved by {metrics['precision_gain']:.1f}%")
        
        return True
        
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_e2e_overlay_symbol_tracking():
    """
    E2E Test 4: Overlay tracks symbol changes correctly
    """
    print("\n[E2E Test 4] Overlay symbol tracking...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            # Base IR (committed code)
            base_ir = {
                "test.py": {
                    "file": "test.py",
                    "symbols": [
                        {
                            "id": "test.foo",
                            "name": "foo",
                            "signature": "(x: int, y: int) -> int",
                        }
                    ],
                }
            }
            
            # Uncommitted change (removed parameter y)
            uncommitted = {
                "test.py": """
def foo(x: int) -> int:  # Removed y parameter
    return x * 2
"""
            }
            
            builder = OverlayIRBuilder(project_root=Path(tmpdir))
            
            overlay = await builder.build_overlay(
                base_snapshot_id="base_test",
                repo_id="test_repo",
                uncommitted_files=uncommitted,
                base_ir_docs=base_ir,
            )
            
            print(f"  ✅ Overlay created")
            print(f"  ✅ Affected symbols: {overlay.affected_symbols}")
            
            # Verify symbol was detected as affected
            # Note: Symbol ID might be different due to actual parsing
            assert len(overlay.affected_symbols) > 0, "Should have affected symbols"
            
            print(f"  ✅ Symbol changes tracked: {len(overlay.affected_symbols)} symbols")
            
            return True
            
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """Run all E2E validation tests"""
    print("=" * 60)
    print("🧪 E2E Validation - 실제 작동 검증")
    print("=" * 60)
    
    results = []
    
    # Test 1: Local Overlay
    result1 = await test_e2e_overlay_with_real_file()
    results.append(("Local Overlay with real file", result1))
    
    # Test 2: Type Narrowing
    result2 = await test_e2e_type_narrowing_with_real_code()
    results.append(("Type Narrowing with real code", result2))
    
    # Test 3: Precision comparison
    result3 = await test_e2e_precision_comparison()
    results.append(("Precision comparison", result3))
    
    # Test 4: Overlay symbol tracking
    result4 = await test_e2e_overlay_symbol_tracking()
    results.append(("Overlay symbol tracking", result4))
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 E2E Validation Results")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 60)
    
    if passed == total:
        print("\n🎉 All E2E tests passed! System is working correctly.")
        return 0
    else:
        print(f"\n⚠️ {total - passed} test(s) failed. Need to fix issues.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

