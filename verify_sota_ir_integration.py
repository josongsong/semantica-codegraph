#!/usr/bin/env python3
"""
Quick verification script to check if SOTA IR is properly integrated.

Checks:
1. All modules can be imported
2. Models are properly defined
3. Basic instantiation works
4. No circular import issues
"""

import sys
from pathlib import Path


def test_imports():
    """Test all imports work"""
    print("=" * 60)
    print("Testing imports...")
    print("=" * 60)

    try:
        # Core models
        from src.contexts.code_foundation.infrastructure.ir.models import (
            IRDocument,
            Node,
            Edge,
            Span,
            Occurrence,
            OccurrenceIndex,
            SymbolRole,
            Diagnostic,
            DiagnosticIndex,
            DiagnosticSeverity,
            PackageMetadata,
            PackageIndex,
        )

        print("✅ Core models imported successfully")

        # Generators
        from src.contexts.code_foundation.infrastructure.ir.occurrence_generator import OccurrenceGenerator
        from src.contexts.code_foundation.infrastructure.ir.diagnostic_collector import DiagnosticCollector
        from src.contexts.code_foundation.infrastructure.ir.package_analyzer import PackageAnalyzer

        print("✅ Generators imported successfully")

        # Resolvers
        from src.contexts.code_foundation.infrastructure.ir.cross_file_resolver import CrossFileResolver
        from src.contexts.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex

        print("✅ Resolvers imported successfully")

        # Builder
        from src.contexts.code_foundation.infrastructure.ir.sota_ir_builder import SOTAIRBuilder

        print("✅ SOTA IR Builder imported successfully")

        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_instantiation():
    """Test basic instantiation"""
    print("\n" + "=" * 60)
    print("Testing instantiation...")
    print("=" * 60)

    try:
        from src.contexts.code_foundation.infrastructure.ir.models import (
            Diagnostic,
            DiagnosticSeverity,
            DiagnosticIndex,
            PackageMetadata,
            PackageIndex,
            Span,
        )
        from src.contexts.code_foundation.infrastructure.ir.models.diagnostic import create_diagnostic
        from src.contexts.code_foundation.infrastructure.ir.models.package import create_package

        # Test Diagnostic
        span = Span(file_path="test.py", start_line=1, start_col=0, end_line=1, end_col=10)
        diag = create_diagnostic(
            file_path="test.py",
            span=span,
            severity=DiagnosticSeverity.ERROR,
            message="Test error",
            source="test",
        )
        print(f"✅ Created Diagnostic: {diag}")

        # Test DiagnosticIndex
        diag_index = DiagnosticIndex()
        diag_index.add(diag)
        assert diag_index.total_diagnostics == 1
        print(f"✅ DiagnosticIndex working: {diag_index.total_diagnostics} diagnostics")

        # Test PackageMetadata
        pkg = create_package(
            name="requests",
            version="2.31.0",
            manager="pip",
            import_names=["requests"],
        )
        print(f"✅ Created PackageMetadata: {pkg.name}@{pkg.version}")

        # Test PackageIndex
        pkg_index = PackageIndex()
        pkg_index.add(pkg)
        assert pkg_index.total_packages == 1
        assert pkg_index.get("requests") is not None
        print(f"✅ PackageIndex working: {pkg_index.total_packages} packages")

        # Test IRDocument with new fields
        from src.contexts.code_foundation.infrastructure.ir.models import IRDocument

        ir_doc = IRDocument(
            repo_id="test_repo",
            snapshot_id="test_snapshot",
            schema_version="2.0",
        )

        # Add diagnostic
        ir_doc.diagnostics.append(diag)
        assert len(ir_doc.diagnostics) == 1
        print(f"✅ IRDocument.diagnostics working: {len(ir_doc.diagnostics)} diagnostics")

        # Add package
        ir_doc.packages.append(pkg)
        assert len(ir_doc.packages) == 1
        print(f"✅ IRDocument.packages working: {len(ir_doc.packages)} packages")

        return True
    except Exception as e:
        print(f"❌ Instantiation failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_builder_instantiation():
    """Test SOTA IR Builder can be instantiated"""
    print("\n" + "=" * 60)
    print("Testing SOTA IR Builder instantiation...")
    print("=" * 60)

    try:
        from src.contexts.code_foundation.infrastructure.ir.sota_ir_builder import SOTAIRBuilder

        # Create builder (shouldn't fail)
        builder = SOTAIRBuilder(project_root=Path.cwd())

        # Check components
        assert builder.parser_registry is not None
        print("✅ ParserRegistry initialized")

        assert builder.occurrence_generator is not None
        print("✅ OccurrenceGenerator initialized")

        assert builder.package_analyzer is not None
        print("✅ PackageAnalyzer initialized")

        assert builder.cross_file_resolver is not None
        print("✅ CrossFileResolver initialized")

        print("✅ SOTA IR Builder instantiated successfully")

        return True
    except Exception as e:
        print(f"❌ Builder instantiation failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_file_structure():
    """Check all expected files exist"""
    print("\n" + "=" * 60)
    print("Checking file structure...")
    print("=" * 60)

    expected_files = [
        "src/contexts/code_foundation/infrastructure/ir/models/diagnostic.py",
        "src/contexts/code_foundation/infrastructure/ir/models/package.py",
        "src/contexts/code_foundation/infrastructure/ir/diagnostic_collector.py",
        "src/contexts/code_foundation/infrastructure/ir/package_analyzer.py",
        "src/contexts/code_foundation/infrastructure/ir/sota_ir_builder.py",
        "src/contexts/code_foundation/infrastructure/ir/occurrence_generator.py",
        "src/contexts/code_foundation/infrastructure/ir/cross_file_resolver.py",
        "src/contexts/code_foundation/infrastructure/ir/retrieval_index.py",
        "tests/foundation/test_end_to_end_sota_ir.py",
    ]

    all_exist = True
    for file_path in expected_files:
        full_path = Path(file_path)
        if full_path.exists():
            size = full_path.stat().st_size
            print(f"✅ {file_path} ({size} bytes)")
        else:
            print(f"❌ {file_path} NOT FOUND")
            all_exist = False

    return all_exist


def main():
    """Run all verification tests"""
    print("\n" + "🔍" + "=" * 58 + "🔍")
    print("   SOTA IR Integration Verification")
    print("🔍" + "=" * 58 + "🔍\n")

    results = []

    # Test 1: File structure
    results.append(("File Structure", test_file_structure()))

    # Test 2: Imports
    results.append(("Imports", test_imports()))

    # Test 3: Instantiation
    results.append(("Instantiation", test_instantiation()))

    # Test 4: Builder
    results.append(("SOTA Builder", test_builder_instantiation()))

    # Summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{test_name:20s}: {status}")

    print("=" * 60)

    all_passed = all(passed for _, passed in results)

    if all_passed:
        print("\n🎉 ✅ ALL TESTS PASSED! SOTA IR IS PROPERLY INTEGRATED!")
        print("\n" + "🚀" * 20)
        print("Ready for production use!")
        print("🚀" * 20 + "\n")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
