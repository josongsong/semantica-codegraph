#!/usr/bin/env python3
"""
Test if optimizations affected Points-to Analysis precision.

Compares:
- Before: field_sensitive=True, max_iterations=0 (unlimited)
- After:  field_sensitive=False, max_iterations=20
"""

import sys
sys.path.insert(0, "packages/codegraph-ir")

from codegraph_ir.features.points_to import PointsToAnalyzer, AnalysisConfig, AnalysisMode

def test_simple_alias():
    """Test basic aliasing detection."""
    # Before config (original)
    config_before = AnalysisConfig(
        mode=AnalysisMode.Precise,
        field_sensitive=True,
        max_iterations=0,  # unlimited
        enable_scc=True,
        enable_wave=True,
        enable_parallel=True,
    )

    # After config (optimized)
    config_after = AnalysisConfig(
        mode=AnalysisMode.Precise,
        field_sensitive=False,  # ⚠️ Changed
        max_iterations=20,       # ⚠️ Changed
        enable_scc=True,
        enable_wave=True,
        enable_parallel=True,
    )

    # Test case: x = new A(); y = x;
    for name, config in [("BEFORE", config_before), ("AFTER", config_after)]:
        analyzer = PointsToAnalyzer(config)
        analyzer.add_alloc("x", "alloc:1:A")
        analyzer.add_copy("y", "x")

        result = analyzer.solve()

        print(f"\n{name} CONFIG:")
        print(f"  x aliases y: {result.graph.may_alias_by_name('x', 'y')}")
        print(f"  Points-to sets: x={result.graph.points_to_size_by_name('x')}, y={result.graph.points_to_size_by_name('y')}")
        print(f"  Iterations: {result.stats.iterations}")
        print(f"  Duration: {result.stats.duration_ms:.2f}ms")

def test_field_sensitivity():
    """Test field-sensitive analysis (this WILL differ)."""
    # Before: distinguishes obj.f1 vs obj.f2
    config_before = AnalysisConfig(
        mode=AnalysisMode.Precise,
        field_sensitive=True,
        max_iterations=0,
    )

    # After: treats obj.f1 and obj.f2 as same
    config_after = AnalysisConfig(
        mode=AnalysisMode.Precise,
        field_sensitive=False,
        max_iterations=20,
    )

    for name, config in [("BEFORE (field-sensitive)", config_before),
                         ("AFTER (field-insensitive)", config_after)]:
        analyzer = PointsToAnalyzer(config)

        # obj = new Object()
        # obj.field1 = new A()
        # obj.field2 = new B()
        # x = obj.field1
        # y = obj.field2

        analyzer.add_alloc("obj", "alloc:1:Object")
        analyzer.add_alloc("a", "alloc:2:A")
        analyzer.add_alloc("b", "alloc:3:B")
        analyzer.add_store("obj", "a")   # obj.* = a
        analyzer.add_store("obj", "b")   # obj.* = b
        analyzer.add_load("x", "obj")    # x = obj.*
        analyzer.add_load("y", "obj")    # y = obj.*

        result = analyzer.solve()

        print(f"\n{name}:")
        print(f"  x aliases y: {result.graph.may_alias_by_name('x', 'y')}")
        print(f"  Expected: field-sensitive=False → x aliases y (less precise)")
        print(f"           field-sensitive=True → x may NOT alias y (more precise)")

if __name__ == "__main__":
    print("="*70)
    print("PRECISION IMPACT TEST")
    print("="*70)

    test_simple_alias()
    print("\n" + "="*70)
    test_field_sensitivity()
    print("\n" + "="*70)
