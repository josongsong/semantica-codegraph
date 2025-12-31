#!/usr/bin/env python3
"""
Test TRCR Integration

Validates that TRCR can be imported and used within codegraph.
"""

import sys
from pathlib import Path

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "codegraph-trcr"))


def test_import():
    """Test basic import"""
    print("🧪 Test 1: Import TRCR...")
    try:
        from trcr import TaintRuleCompiler, TaintRuleExecutor

        print("   ✅ Import successful")
        return True
    except ImportError as e:
        print(f"   ❌ Import failed: {e}")
        return False


def test_compile_cwe_rules():
    """Test compiling Python atoms rules"""
    print("\n🧪 Test 2: Compile Python atoms rules...")
    try:
        from trcr import TaintRuleCompiler

        # Path to Python atoms YAML
        atoms_path = (
            Path(__file__).parent.parent / "packages" / "codegraph-trcr" / "rules" / "atoms" / "python.atoms.yaml"
        )

        if not atoms_path.exists():
            print(f"   ⚠️  Python atoms file not found: {atoms_path}")
            return False

        compiler = TaintRuleCompiler()
        executables = compiler.compile_file(str(atoms_path))

        print(f"   ✅ Compiled {len(executables)} rules from Python atoms")

        # Print first few rules
        for i, rule in enumerate(executables[:3]):
            print(f"      - Rule {i + 1}: {rule.rule_id}")

        return True
    except Exception as e:
        print(f"   ❌ Compilation failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_execute_rules():
    """Test executing rules against mock entities"""
    print("\n🧪 Test 3: Execute rules...")
    try:
        from trcr import TaintRuleCompiler, TaintRuleExecutor
        from trcr.types.entity import MockEntity

        # Compile rules
        atoms_path = (
            Path(__file__).parent.parent / "packages" / "codegraph-trcr" / "rules" / "atoms" / "python.atoms.yaml"
        )
        compiler = TaintRuleCompiler()
        executables = compiler.compile_file(str(atoms_path))

        # Create mock entities using TRCR's MockEntity
        entities = [
            MockEntity(entity_id="e1", kind="call", call="input"),
            MockEntity(
                entity_id="e2",
                kind="call",
                base_type="sqlite3.Cursor",
                call="execute",
                args=["query"],
                is_const={0: False},
            ),
        ]

        # Execute rules
        executor = TaintRuleExecutor(executables, enable_cache=True)
        matches = executor.execute(entities)

        print(f"   ✅ Found {len(matches)} matches")

        # Print matches
        for match in matches[:5]:
            print(f"      - {match.rule_id}: {match.effect_kind} (confidence={match.confidence:.2f})")

        return len(matches) > 0
    except Exception as e:
        print(f"   ❌ Execution failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("TRCR Integration Test Suite")
    print("=" * 60)

    results = []

    # Run tests
    results.append(("Import", test_import()))
    results.append(("Compile CWE Rules", test_compile_cwe_rules()))
    results.append(("Execute Rules", test_execute_rules()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")

    print(f"\nTotal: {passed}/{total} passed")

    if passed == total:
        print("\n🎉 All tests passed! TRCR integration is working.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Check the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
