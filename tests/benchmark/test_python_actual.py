"""
Python Generator ACTUAL Benchmark (추정 아님!)

실제 Python generator로 측정.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "packages" / "codegraph-engine"))

try:
    from codegraph_engine.code_foundation.infrastructure.generators.python_generator import _PythonIRGenerator
    from codegraph_engine.code_foundation.infrastructure.parsing import SourceFile
    from codegraph_engine.code_foundation.domain.models import Language
except ImportError as e:
    print(f"❌ Import failed: {e}")
    print("⚠️  Run: pip install -e packages/codegraph-engine")
    sys.exit(1)

print("=" * 70)
print("🐍 Python Generator ACTUAL Benchmark")
print("=" * 70)

# Test code
code = """
import os
from typing import List, Dict

class DataProcessor:
    def __init__(self, name: str):
        self.name = name
    
    def process(self, items: List[int]) -> Dict[str, int]:
        result = {}
        for item in items:
            if item > 0:
                result[str(item)] = item * 2
        return result
    
    def validate(self, value: int) -> bool:
        return value > 0

class Calculator:
    def add(self, x: int, y: int) -> int:
        return x + y
    
    def subtract(self, x: int, y: int) -> int:
        return x - y

def helper(x, y):
    return x + y

def main():
    processor = DataProcessor("test")
    print(processor.process([1,2,3]))
"""

# Benchmark
configs = [
    (10, "10 files"),
    (100, "100 files"),
    (500, "500 files"),
]

print()

for num_files, label in configs:
    sources = []
    for i in range(num_files):
        source = SourceFile.from_content(
            file_path=f"file_{i}.py",
            content=code,
            language=Language.PYTHON,
        )
        sources.append(source)

    # Warmup
    for src in sources[:2]:
        gen = _PythonIRGenerator(src, "test-repo")
        gen.generate()

    # Measure
    start = time.perf_counter()

    for src in sources:
        gen = _PythonIRGenerator(src, "test-repo")
        nodes, edges = gen.generate()

    elapsed = time.perf_counter() - start

    per_file_ms = (elapsed / num_files) * 1000

    print(f"{label}:")
    print(f"  Total: {elapsed:.3f}s")
    print(f"  Per file: {per_file_ms:.2f}ms")
    print()

print("=" * 70)
print("✅ Python ACTUAL benchmark completed!")
print("=" * 70)
