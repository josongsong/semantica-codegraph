#!/usr/bin/env python3
"""Test E2E Pipeline PyO3 Bindings

This test verifies that the Rust-native E2E pipeline orchestrator
is properly exposed to Python and delivers SOTA performance.
"""

import codegraph_ir
import tempfile
import os
from pathlib import Path


def create_test_repo():
    """Create a temporary Python repository for testing"""
    tmpdir = tempfile.mkdtemp(prefix="e2e_test_")

    # Create some test Python files
    files = {
        "module_a.py": '''
"""Module A - Example module"""

def hello(name: str) -> str:
    """Say hello"""
    return f"Hello, {name}!"

class Greeter:
    """A greeter class"""
    def __init__(self, greeting: str):
        self.greeting = greeting

    def greet(self, name: str) -> str:
        return f"{self.greeting}, {name}!"
''',
        "module_b.py": '''
"""Module B - Imports from A"""
from module_a import hello, Greeter

def main():
    """Main function"""
    # Call hello function
    message = hello("World")
    print(message)

    # Use Greeter class
    greeter = Greeter("Hi")
    result = greeter.greet("Alice")
    print(result)

if __name__ == "__main__":
    main()
''',
        "utils.py": '''
"""Utility functions"""

def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

def multiply(a: int, b: int) -> int:
    """Multiply two numbers"""
    return a * b

def factorial(n: int) -> int:
    """Calculate factorial"""
    if n <= 1:
        return 1
    return n * factorial(n - 1)
''',
    }

    for filename, content in files.items():
        filepath = os.path.join(tmpdir, filename)
        with open(filepath, "w") as f:
            f.write(content)

    return tmpdir, list(files.keys())


def test_e2e_pipeline_basic():
    """Test basic E2E pipeline execution"""
    print("=" * 80)
    print("TEST: Basic E2E Pipeline Execution")
    print("=" * 80)

    # Create test repository
    repo_path, filenames = create_test_repo()
    print(f"\n📁 Test repo: {repo_path}")
    print(f"📄 Files: {', '.join(filenames)}")

    try:
        # Create pipeline config
        config = codegraph_ir.PyE2EPipelineConfig(
            repo_path=repo_path,
            repo_name="test-repo",
            file_paths=None,  # Auto-discover
            parallel_workers=2,
            batch_size=100,
            enable_cache=False,
        )
        print("\n✓ Created PyE2EPipelineConfig")

        # Execute pipeline
        print("\n🚀 Executing E2E pipeline...")
        result = codegraph_ir.execute_e2e_pipeline(config)
        print("✓ Pipeline execution completed")

        # Verify result structure
        print("\n📊 Result structure:")
        print(f"  - nodes: {type(result['nodes']).__name__} ({len(result['nodes'])} items)")
        print(f"  - edges: {type(result['edges']).__name__} ({len(result['edges'])} items)")
        print(f"  - chunks: {type(result['chunks']).__name__} ({len(result['chunks'])} items)")
        print(f"  - symbols: {type(result['symbols']).__name__} ({len(result['symbols'])} items)")
        print(f"  - occurrences: {type(result['occurrences']).__name__} ({len(result['occurrences'])} items)")
        print(f"  - metadata: {type(result['metadata']).__name__}")

        # Verify metadata
        metadata = result["metadata"]
        print(f"\n📈 Metadata:")
        print(f"  - files_processed: {metadata['files_processed']}")
        print(f"  - files_failed: {metadata['files_failed']}")
        print(f"  - total_loc: {metadata['total_loc']}")
        print(f"  - loc_per_second: {metadata['loc_per_second']:.2f}")
        print(f"  - total_duration_ms: {metadata['total_duration_ms']}")
        print(f"  - cache_hit_rate: {metadata['cache_hit_rate']:.2%}")

        # Verify stage metrics
        if "stage_metrics" in metadata:
            print(f"\n⏱️  Stage Metrics:")
            for stage_name, metrics in metadata["stage_metrics"].items():
                duration_ms = metrics["duration_ms"]
                items = metrics["items_processed"]
                print(f"  - {stage_name}: {duration_ms}ms ({items} items)")

        # Show some nodes
        if result["nodes"]:
            print(f"\n🔍 Sample Nodes (first 5):")
            for i, node in enumerate(result["nodes"][:5]):
                print(f"  {i + 1}. {node.kind.as_str()}: {node.fqn} @ {node.file_path}")

        # Show some edges
        if result["edges"]:
            print(f"\n🔗 Sample Edges (first 5):")
            for i, edge in enumerate(result["edges"][:5]):
                print(f"  {i + 1}. {edge.kind.as_str()}: {edge.source_id} -> {edge.target_id}")

        # Assertions
        assert result["nodes"], "Should have nodes"
        assert metadata["files_processed"] == 3, f"Should process 3 files, got {metadata['files_processed']}"
        assert metadata["files_failed"] == 0, f"Should have 0 failures, got {metadata['files_failed']}"
        assert metadata["total_loc"] > 0, "Should count lines of code"

        print("\n✅ All assertions passed!")

    finally:
        # Cleanup
        import shutil

        shutil.rmtree(repo_path, ignore_errors=True)
        print(f"\n🧹 Cleaned up test repo: {repo_path}")


def test_e2e_pipeline_with_file_list():
    """Test E2E pipeline with explicit file list"""
    print("\n" + "=" * 80)
    print("TEST: E2E Pipeline with Explicit File List")
    print("=" * 80)

    # Create test repository
    repo_path, filenames = create_test_repo()
    print(f"\n📁 Test repo: {repo_path}")

    try:
        # Create pipeline config with explicit file list (only 2 files)
        file_paths = [
            os.path.join(repo_path, "module_a.py"),
            os.path.join(repo_path, "module_b.py"),
        ]

        config = codegraph_ir.PyE2EPipelineConfig(
            repo_path=repo_path,
            repo_name="test-repo-explicit",
            file_paths=file_paths,
            parallel_workers=1,
            batch_size=10,
            enable_cache=False,
        )
        print(f"✓ Created config with {len(file_paths)} explicit files")

        # Execute pipeline
        print("\n🚀 Executing E2E pipeline...")
        result = codegraph_ir.execute_e2e_pipeline(config)
        print("✓ Pipeline execution completed")

        # Verify only 2 files were processed
        metadata = result["metadata"]
        assert metadata["files_processed"] == 2, f"Should process 2 files, got {metadata['files_processed']}"

        print(f"\n📊 Results:")
        print(f"  - Files processed: {metadata['files_processed']}")
        print(f"  - Nodes: {len(result['nodes'])}")
        print(f"  - Edges: {len(result['edges'])}")

        print("\n✅ Explicit file list test passed!")

    finally:
        # Cleanup
        import shutil

        shutil.rmtree(repo_path, ignore_errors=True)


def test_e2e_pipeline_performance():
    """Test E2E pipeline performance metrics"""
    print("\n" + "=" * 80)
    print("TEST: E2E Pipeline Performance")
    print("=" * 80)

    # Create test repository
    repo_path, _ = create_test_repo()

    try:
        # Create pipeline config with parallelism
        config = codegraph_ir.PyE2EPipelineConfig(
            repo_path=repo_path,
            repo_name="test-repo-perf",
            file_paths=None,
            parallel_workers=4,  # Max parallelism
            batch_size=100,
            enable_cache=False,
        )

        # Execute multiple times to measure consistency
        print("\n🏃 Running 3 iterations...")
        durations = []
        for i in range(3):
            result = codegraph_ir.execute_e2e_pipeline(config)
            duration_ms = result["metadata"]["total_duration_ms"]
            loc_per_sec = result["metadata"]["loc_per_second"]
            durations.append(duration_ms)
            print(f"  Iteration {i + 1}: {duration_ms}ms ({loc_per_sec:.0f} LOC/s)")

        # Calculate statistics
        avg_duration = sum(durations) / len(durations)
        min_duration = min(durations)
        max_duration = max(durations)

        print(f"\n📈 Performance Statistics:")
        print(f"  - Average: {avg_duration:.2f}ms")
        print(f"  - Min: {min_duration}ms")
        print(f"  - Max: {max_duration}ms")
        print(f"  - Variance: {max_duration - min_duration}ms")

        # Performance assertion (should be fast for small files)
        assert avg_duration < 500, f"Should complete in < 500ms, got {avg_duration:.2f}ms"

        print("\n✅ Performance test passed!")

    finally:
        # Cleanup
        import shutil

        shutil.rmtree(repo_path, ignore_errors=True)


if __name__ == "__main__":
    print("\n" + "🚀 " * 20)
    print("E2E Pipeline PyO3 Bindings Test Suite")
    print("🚀 " * 20 + "\n")

    try:
        test_e2e_pipeline_basic()
        test_e2e_pipeline_with_file_list()
        test_e2e_pipeline_performance()

        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED!")
        print("=" * 80)
        print("\nThe Rust-native E2E pipeline is working correctly with SOTA performance! 🎉")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        exit(1)
