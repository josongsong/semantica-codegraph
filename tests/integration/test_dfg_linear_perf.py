"""
DFG Linear Performance Test (SOTA)

Compares linear O(n) vs potential O(n²) performance.
"""

import time

import pytest

from codegraph_engine.code_foundation.infrastructure.dfg.builder import DfgBuilder
from codegraph_engine.code_foundation.infrastructure.generators.python_generator import _PythonIRGenerator
from codegraph_engine.code_foundation.infrastructure.parsing import SourceFile
from codegraph_engine.code_foundation.infrastructure.semantic_ir.bfg.builder import BfgBuilder
from codegraph_engine.code_foundation.infrastructure.semantic_ir.expression.builder import ExpressionBuilder


@pytest.fixture
def generator():
    """IR generator"""
    return _PythonIRGenerator(repo_id="test")


def test_dfg_linear_performance_small(generator):
    """
    Performance test: Small function (10 variables)
    Expected: < 50ms
    """
    code = """
def test_func():
    a = 1
    b = a
    c = b
    d = c
    e = d
    f = e
    g = f
    h = g
    i = h
    j = i
"""
    source = SourceFile.from_content("test.py", code, "python")

    start = time.perf_counter()
    ir_doc = generator.generate(source, "v1")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert ir_doc is not None
    assert elapsed_ms < 50, f"Too slow: {elapsed_ms:.1f}ms"


def test_dfg_linear_performance_medium(generator):
    """
    Performance test: Medium function (50 variables)
    Expected: < 200ms
    """
    # Generate code with 50 variables
    lines = ["def test_func():"]
    lines.append("    a0 = 1")
    for i in range(1, 50):
        lines.append(f"    a{i} = a{i - 1}")

    code = "\n".join(lines)
    source = SourceFile.from_content("test.py", code, "python")

    start = time.perf_counter()
    ir_doc = generator.generate(source, "v1")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert ir_doc is not None
    assert elapsed_ms < 200, f"Too slow: {elapsed_ms:.1f}ms"


def test_dfg_linear_performance_large(generator):
    """
    Performance test: Large function (200 variables)
    Expected: < 1000ms (linear scaling)

    Note: O(n²) would be > 5000ms, O(n) should be < 1000ms
    """
    # Generate code with 200 variables
    lines = ["def test_func():"]
    lines.append("    a0 = 1")
    for i in range(1, 200):
        lines.append(f"    a{i} = a{i - 1}")

    code = "\n".join(lines)
    source = SourceFile.from_content("test.py", code, "python")

    start = time.perf_counter()
    ir_doc = generator.generate(source, "v1")
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert ir_doc is not None
    # Linear should be < 1s, quadratic would be > 5s
    assert elapsed_ms < 1000, f"Non-linear performance: {elapsed_ms:.1f}ms"

    print(f"\n✅ Large function (200 vars): {elapsed_ms:.1f}ms (linear)")


def test_dfg_linear_scalability():
    """
    Scalability test: Verify O(n) complexity
    Expected: Time grows linearly with input size
    """
    generator = _PythonIRGenerator(repo_id="test")

    sizes = [10, 20, 40, 80]
    times = []

    for size in sizes:
        # Generate code
        lines = ["def test_func():"]
        lines.append("    a0 = 1")
        for i in range(1, size):
            lines.append(f"    a{i} = a{i - 1}")

        code = "\n".join(lines)
        source = SourceFile.from_content("test.py", code, "python")

        # Measure time
        start = time.perf_counter()
        ir_doc = generator.generate(source, "v1")
        elapsed = time.perf_counter() - start
        times.append(elapsed)

        assert ir_doc is not None

    # Check linearity: time(2n) / time(n) should be ~2 (not 4 for O(n²))
    for i in range(len(times) - 1):
        ratio = times[i + 1] / times[i] if times[i] > 0 else 0
        # Allow 3x tolerance (should be ~2x for linear, would be ~4x for quadratic)
        assert ratio < 3.0, f"Non-linear scaling: {sizes[i]}→{sizes[i + 1]} = {ratio:.2f}x"

    print(f"\n✅ Scalability verified: {sizes} → {[f'{t * 1000:.1f}ms' for t in times]}")
