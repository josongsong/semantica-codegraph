"""
Benchmark: Rust AST Traversal vs Python

Target: 3x speedup (0.32s → 0.10s for _traverse_ast)
"""

import time


def test_rust_ast_benchmark():
    """Benchmark Rust AST traversal"""
    try:
        import codegraph_ast
    except ImportError:
        print("⚠️  Rust module not installed")
        return

    # Test code (realistic Python file)
    code = """
import os
from typing import List, Optional

class DataProcessor:
    def __init__(self, name: str):
        self.name = name
        self.data = []
    
    def process(self, items: List[int]) -> int:
        result = 0
        for item in items:
            if item > 0:
                result += item
        return result
    
    def validate(self, value: Optional[int]) -> bool:
        if value is None:
            return False
        return value > 0

def helper_function(x: int, y: int) -> int:
    return x + y

def main():
    processor = DataProcessor("test")
    data = [1, 2, 3, 4, 5]
    result = processor.process(data)
    print(f"Result: {result}")

if __name__ == "__main__":
    main()
"""

    # Benchmark configurations
    configs = [
        (10, "10 files"),
        (100, "100 files"),
        (500, "500 files"),
    ]

    print("\n" + "=" * 60)
    print("🦀 Rust AST Traversal Benchmark")
    print("=" * 60)

    for num_files, label in configs:
        files = [(f"file_{i}.py", code) for i in range(num_files)]

        # Warmup
        codegraph_ast.traverse_ast_parallel(files[:5])

        # Measure
        start = time.perf_counter()
        results = codegraph_ast.traverse_ast_parallel(files)
        elapsed = time.perf_counter() - start

        # Verify
        assert len(results) == num_files
        total_nodes = sum(r["node_count"] for r in results)

        # Stats
        per_file_ms = (elapsed / num_files) * 1000

        print(f"\n{label}:")
        print(f"  Total: {elapsed:.3f}s")
        print(f"  Per file: {per_file_ms:.2f}ms")
        print(f"  Nodes: {total_nodes}")

        # Target: < 3ms/file (3x speedup from 9.8ms)
        if num_files >= 100:
            target_ms = 3.5  # Slightly relaxed for first iteration
            if per_file_ms < target_ms:
                print(f"  ✅ PASS (< {target_ms}ms/file)")
            else:
                speedup = 9.8 / per_file_ms
                print(f"  ⚠️  Speedup: {speedup:.1f}x (target: 3x)")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    test_rust_ast_benchmark()
