#!/usr/bin/env python3
"""
Test Pattern Registry Integration with BiAbduction

This script tests that the pattern registry is properly integrated
into the BiAbduction effect analysis system.
"""

import sys
sys.path.insert(0, "packages/codegraph-engine")
sys.path.insert(0, "packages/codegraph-shared")
sys.path.insert(0, "packages/codegraph-rust/target/debug")

try:
    from codegraph_ir import IRDocument, Node, Edge, NodeKind, EdgeKind
    from codegraph_ir import BiAbductionStrategy, LocalEffectAnalyzer
    print("✅ Successfully imported codegraph_ir")
except ImportError as e:
    print(f"❌ Failed to import codegraph_ir: {e}")
    print("\nTrying to build Rust extension...")
    import subprocess
    result = subprocess.run(
        ["maturin", "develop"],
        cwd="packages/codegraph-rust/codegraph-ir",
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"❌ Build failed:\n{result.stderr}")
        sys.exit(1)
    print("✅ Build succeeded, trying import again...")
    from codegraph_ir import IRDocument, Node, Edge, NodeKind, EdgeKind
    from codegraph_ir import BiAbductionStrategy, LocalEffectAnalyzer

def create_test_node(id, kind, name, language="python"):
    """Create a test node"""
    return Node(
        id=id,
        kind=kind,
        fqn=name,
        file_path="test.py",
        span={"start_line": 1, "start_col": 0, "end_line": 10, "end_col": 0},
        language=language,
        name=name,
    )

def test_pattern_registry_integration():
    """Test that pattern registry is working"""
    print("\n" + "="*60)
    print("TEST: Pattern Registry Integration")
    print("="*60)

    # Test 1: Python print function
    print("\n1. Testing Python 'print' pattern...")
    func1 = create_test_node("func1", NodeKind.Function, "do_print", "python")
    print_var = create_test_node("var1", NodeKind.Variable, "print", "python")

    ir_doc = IRDocument(
        file_path="test.py",
        nodes=[func1, print_var],
        edges=[Edge(source_id="func1", target_id="var1", kind=EdgeKind.Contains)],
    )

    local_analyzer = LocalEffectAnalyzer()
    strategy = BiAbductionStrategy(local_analyzer)
    result = strategy.analyze_all(ir_doc)

    func1_effects = result.get("func1")
    if func1_effects:
        effects_list = list(func1_effects.effects)
        print(f"   Effects: {effects_list}")
        print(f"   Confidence: {func1_effects.confidence:.2f}")

        # Check if Io effect is present
        if "Io" in [str(e) for e in effects_list]:
            print("   ✅ PASS: Io effect detected via pattern registry")
        else:
            print(f"   ❌ FAIL: Expected Io effect, got {effects_list}")
            return False
    else:
        print("   ❌ FAIL: No effects returned")
        return False

    # Test 2: Database query
    print("\n2. Testing Python 'db_query' pattern...")
    func2 = create_test_node("func2", NodeKind.Function, "fetch_data", "python")
    db_var = create_test_node("var2", NodeKind.Variable, "db_query", "python")

    ir_doc2 = IRDocument(
        file_path="test.py",
        nodes=[func2, db_var],
        edges=[Edge(source_id="func2", target_id="var2", kind=EdgeKind.Contains)],
    )

    result2 = strategy.analyze_all(ir_doc2)
    func2_effects = result2.get("func2")

    if func2_effects:
        effects_list = list(func2_effects.effects)
        print(f"   Effects: {effects_list}")
        print(f"   Confidence: {func2_effects.confidence:.2f}")

        # Check if DbRead effect is present
        if "DbRead" in [str(e) for e in effects_list]:
            print("   ✅ PASS: DbRead effect detected via pattern registry")
        else:
            print(f"   ❌ FAIL: Expected DbRead effect, got {effects_list}")
            return False
    else:
        print("   ❌ FAIL: No effects returned")
        return False

    # Test 3: Empty function (should be Pure)
    print("\n3. Testing empty function...")
    func3 = create_test_node("func3", NodeKind.Function, "empty", "python")

    ir_doc3 = IRDocument(
        file_path="test.py",
        nodes=[func3],
        edges=[],
    )

    result3 = strategy.analyze_all(ir_doc3)
    func3_effects = result3.get("func3")

    if func3_effects:
        effects_list = list(func3_effects.effects)
        print(f"   Effects: {effects_list}")
        print(f"   Confidence: {func3_effects.confidence:.2f}")

        # Check if Pure effect is present
        if "Pure" in [str(e) for e in effects_list]:
            print("   ✅ PASS: Pure effect detected for empty function")
        else:
            print(f"   ❌ FAIL: Expected Pure effect, got {effects_list}")
            return False
    else:
        print("   ❌ FAIL: No effects returned")
        return False

    # Test 4: Generic network pattern (language-agnostic)
    print("\n4. Testing generic 'http_get' pattern (JavaScript)...")
    func4 = create_test_node("func4", NodeKind.Function, "fetch_api", "javascript")
    http_var = create_test_node("var4", NodeKind.Variable, "http_get", "javascript")

    ir_doc4 = IRDocument(
        file_path="test.js",
        nodes=[func4, http_var],
        edges=[Edge(source_id="func4", target_id="var4", kind=EdgeKind.Contains)],
    )

    result4 = strategy.analyze_all(ir_doc4)
    func4_effects = result4.get("func4")

    if func4_effects:
        effects_list = list(func4_effects.effects)
        print(f"   Effects: {effects_list}")
        print(f"   Confidence: {func4_effects.confidence:.2f}")

        # Check if Network effect is present
        if "Network" in [str(e) for e in effects_list]:
            print("   ✅ PASS: Network effect detected via generic pattern")
        else:
            print(f"   ❌ FAIL: Expected Network effect, got {effects_list}")
            return False
    else:
        print("   ❌ FAIL: No effects returned")
        return False

    print("\n" + "="*60)
    print("✅ ALL TESTS PASSED")
    print("="*60)
    print("\nPattern Registry Integration Summary:")
    print("- Python-specific patterns: ✅ Working")
    print("- Database patterns: ✅ Working")
    print("- Empty function detection: ✅ Working")
    print("- Generic patterns (cross-language): ✅ Working")
    print("\nThe 130-line hardcoded function has been successfully")
    print("replaced with the extensible pattern registry system!")

    return True

if __name__ == "__main__":
    try:
        success = test_pattern_registry_integration()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST FAILED WITH EXCEPTION:")
        print(f"{type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
