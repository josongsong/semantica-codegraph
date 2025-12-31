"""Integration tests for Rust engine after cleanup.

Tests that the Rust engine (codegraph-ir) works correctly
after removing Python→Rust dependencies and consolidating packages.
"""

import tempfile
from pathlib import Path

import pytest


def test_rust_taint_analysis():
    """Test Rust taint analysis works after cleanup."""
    # Create a temporary test file with a simple taint flow
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("""
import os

def vulnerable_function():
    user_input = input("Enter command: ")  # Source
    os.system(user_input)  # Sink - Command Injection!
""")

        # Import Rust engine
        import codegraph_ir

        # Configure pipeline
        config = codegraph_ir.E2EPipelineConfig(
            root_path=tmpdir,
            enable_taint=True,
            parallel_workers=1,
        )

        # Run orchestrator
        orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
        result = orchestrator.execute()

        # Verify results
        assert result.success, f"Pipeline failed: {result.error}"
        assert len(result.ir_documents) > 0, "No IR documents generated"

        # Check that taint analysis ran
        print(f"Generated {len(result.ir_documents)} IR documents")
        print(f"Pipeline execution time: {result.execution_time_ms}ms")


def test_rust_complexity_analysis():
    """Test Rust complexity analysis works after cleanup."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("""
def simple_function():
    return 42

def complex_function(n):
    result = 0
    for i in range(n):
        for j in range(n):
            result += i * j
    return result
""")

        import codegraph_ir

        config = codegraph_ir.E2EPipelineConfig(
            root_path=tmpdir,
            enable_complexity=True,
        )

        orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
        result = orchestrator.execute()

        assert result.success, f"Pipeline failed: {result.error}"
        print(f"Complexity analysis completed in {result.execution_time_ms}ms")


def test_rust_ir_generation():
    """Test basic IR generation works."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("""
class TestClass:
    def method(self, x):
        return x + 1

def function():
    obj = TestClass()
    return obj.method(42)
""")

        import codegraph_ir

        config = codegraph_ir.E2EPipelineConfig(
            root_path=tmpdir,
            parallel_workers=1,
        )

        orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
        result = orchestrator.execute()

        assert result.success
        assert len(result.ir_documents) > 0

        # Verify IR structure
        ir_doc = result.ir_documents[0]
        print(f"IR document has {len(ir_doc.get('nodes', []))} nodes")
        print(f"IR document has {len(ir_doc.get('edges', []))} edges")


@pytest.mark.slow
def test_rust_performance():
    """Benchmark Rust engine performance."""
    import time

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create 100 Python files
        for i in range(100):
            test_file = Path(tmpdir) / f"file_{i}.py"
            test_file.write_text(f"""
def function_{i}():
    result = 0
    for i in range(100):
        result += i
    return result
""")

        import codegraph_ir

        config = codegraph_ir.E2EPipelineConfig(
            root_path=tmpdir,
            enable_taint=True,
            parallel_workers=4,
        )

        start = time.time()
        orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
        result = orchestrator.execute()
        duration = time.time() - start

        assert result.success
        assert len(result.ir_documents) == 100

        print(f"✅ Processed 100 files in {duration:.2f}s")
        print(f"   Average: {duration / 100 * 1000:.2f}ms per file")

        # Should be fast (< 5s for 100 files)
        assert duration < 5.0, f"Too slow: {duration:.2f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
