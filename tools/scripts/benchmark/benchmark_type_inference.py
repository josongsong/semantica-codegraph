#!/usr/bin/env python3
"""
Type Inference Performance Benchmark

RFC-030: Self-contained Type Inference with Pyright Fallback

Measures:
1. Self-contained inference speed (no Pyright)
2. Coverage rate by inference source
3. Comparison with Pyright-only approach

Usage:
    python scripts/benchmark_type_inference.py
    python scripts/benchmark_type_inference.py --with-pyright
"""

import argparse
import random
import string
import time
from dataclasses import dataclass, field
from pathlib import Path

# Add project root to path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from codegraph_engine.code_foundation.domain.type_inference.models import (
    ExpressionTypeRequest,
    InferContext,
    InferSource,
)
from codegraph_engine.code_foundation.infrastructure.ir.models.core import Span
from codegraph_engine.code_foundation.infrastructure.type_inference import (
    InferredTypeResolver,
    YamlBuiltinMethodRegistry,
)
from codegraph_engine.code_foundation.infrastructure.type_inference.pyright_fallback import (
    NullPyrightFallback,
    PyrightFallbackAdapter,
)


@dataclass
class BenchmarkResult:
    """Benchmark result data."""

    name: str
    total_inferences: int
    elapsed_ms: float
    inferences_per_sec: float
    coverage_by_source: dict[str, float] = field(default_factory=dict)
    pyright_calls: int = 0


def generate_test_requests(count: int) -> list[ExpressionTypeRequest]:
    """Generate synthetic test requests."""
    requests = []

    # Distribution:
    # 30% - Literals (int, str, float, bool, list, dict)
    # 20% - Method calls on builtins
    # 20% - Variables with annotations (simulated)
    # 30% - Unknown (no info)

    literal_types = [
        (42, "int"),
        ("hello", "str"),
        (3.14, "float"),
        (True, "bool"),
        ([1, 2, 3], "list[int]"),
        ({"a": 1}, "dict[str, int]"),
    ]

    builtin_methods = [
        ("str", "upper"),
        ("str", "lower"),
        ("str", "split"),
        ("list", "append"),
        ("list", "pop"),
        ("dict", "get"),
        ("dict", "keys"),
    ]

    for i in range(count):
        rand = random.random()

        if rand < 0.3:
            # Literal
            value, _ = random.choice(literal_types)
            requests.append(
                ExpressionTypeRequest(
                    expr_id=f"expr_{i}",
                    var_name=f"var_{i}",
                    kind="literal",
                    literal_value=value,
                )
            )
        elif rand < 0.5:
            # Builtin method
            receiver, method = random.choice(builtin_methods)
            requests.append(
                ExpressionTypeRequest(
                    expr_id=f"expr_{i}",
                    var_name=f"result_{i}",
                    kind="method_call",
                    receiver_type=receiver,
                    method_name=method,
                )
            )
        elif rand < 0.7:
            # Simulated annotation (we'll add to context)
            requests.append(
                ExpressionTypeRequest(
                    expr_id=f"expr_{i}",
                    var_name=f"annotated_{i}",
                    kind="name",
                )
            )
        else:
            # Unknown
            requests.append(
                ExpressionTypeRequest(
                    expr_id=f"expr_{i}",
                    var_name=f"unknown_{i}",
                    kind="unknown",
                )
            )

    return requests


def create_context_with_annotations(requests: list[ExpressionTypeRequest]) -> InferContext:
    """Create context with annotations for some variables."""
    annotations = {}

    for req in requests:
        if req.var_name and req.var_name.startswith("annotated_"):
            # Simulate type annotation
            annotations[req.var_name] = random.choice(["int", "str", "float", "bool", "list", "dict"])

    # NOTE: file_path will be overwritten to point to a generated temp file
    return InferContext(file_path="benchmark_test.py", annotations=annotations)


def build_benchmark_file(
    requests: list[ExpressionTypeRequest],
    out_rel: Path = Path("_temp_test/type_inference_bench/benchmark_test.py"),
) -> Path:
    """
    Create a real python file so Pyright fallback can run (needs file+Span).
    Each request gets a stable Span pointing to var name at line start.
    """
    header = [
        "from __future__ import annotations",
        "from datetime import datetime",
        "from pathlib import Path",
        "from typing import Optional, Union",
        "",
    ]
    lines: list[str] = list(header)
    first_line = len(lines) + 1  # 1-indexed for Span

    def emit_value(req: ExpressionTypeRequest) -> str:
        if req.kind == "literal":
            v = req.literal_value
            return repr(v)
        if req.kind == "method_call" and req.receiver_type and req.method_name:
            if req.receiver_type == "str":
                return f"('hello').{req.method_name}()"
            if req.receiver_type == "list":
                # append/pop need different forms
                if req.method_name == "append":
                    return "([1,2,3] + [4])"
                return f"([1,2,3]).{req.method_name}()"
            if req.receiver_type == "dict":
                return f"({{'a':1}}).{req.method_name}('a')"
        # annotated or unknown: make Pyright infer something but keep internal request "unknown"
        return "Path('x') if True else datetime.now()"

    for i, req in enumerate(requests):
        var = req.var_name or f"v_{i}"
        if req.kind == "name" and var.startswith("annotated_"):
            anno = "int"
            value = "1"
            line = f"{var}: {anno} = {value}"
        else:
            line = f"{var} = {emit_value(req)}"
        lines.append(line)
        line_no = first_line + i
        req.span = Span(start_line=line_no, start_col=0, end_line=line_no, end_col=len(var))

    abs_path = Path(__file__).resolve().parents[2] / out_rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_rel


def run_benchmark(
    name: str,
    resolver: InferredTypeResolver,
    requests: list[ExpressionTypeRequest],
    context: InferContext,
) -> BenchmarkResult:
    """Run benchmark and collect results."""

    # Warmup
    for req in requests[:100]:
        resolver.infer(req, context)
    resolver.reset_stats()

    # Actual benchmark
    start = time.perf_counter()

    for req in requests:
        resolver.infer(req, context)

    elapsed = time.perf_counter() - start
    elapsed_ms = elapsed * 1000

    # Collect stats
    stats = resolver.stats
    total = stats["total_inferences"]
    inferences_per_sec = total / elapsed if elapsed > 0 else 0

    coverage = resolver.get_coverage_report()

    return BenchmarkResult(
        name=name,
        total_inferences=total,
        elapsed_ms=elapsed_ms,
        inferences_per_sec=inferences_per_sec,
        coverage_by_source=coverage["by_source"],
        pyright_calls=stats.get("pyright_total_calls", 0),
    )


def print_result(result: BenchmarkResult):
    """Print benchmark result."""
    print(f"\n{'=' * 60}")
    print(f"Benchmark: {result.name}")
    print(f"{'=' * 60}")
    print(f"Total Inferences:    {result.total_inferences:,}")
    print(f"Elapsed Time:        {result.elapsed_ms:.2f} ms")
    print(f"Throughput:          {result.inferences_per_sec:,.0f} inferences/sec")

    if result.pyright_calls > 0:
        print(f"Pyright Calls:       {result.pyright_calls:,}")

    print(f"\nCoverage by Source:")
    for source, rate in sorted(result.coverage_by_source.items(), key=lambda x: -x[1]):
        bar = "█" * int(rate * 40)
        print(f"  {source:15s} {rate * 100:5.1f}% {bar}")


def main():
    parser = argparse.ArgumentParser(description="Type Inference Benchmark")
    parser.add_argument("--with-pyright", action="store_true", help="Enable Pyright fallback")
    parser.add_argument("--count", type=int, default=10000, help="Number of inferences")
    parser.add_argument(
        "--write-benchmark-file",
        action="store_true",
        help="Generate a real python file + spans so Pyright fallback can be exercised",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("RFC-030: Type Inference Performance Benchmark")
    print("=" * 60)
    print(f"Inference Count: {args.count:,}")
    print(f"Pyright Enabled: {args.with_pyright}")

    # Generate test data
    print("\nGenerating test requests...")
    requests = generate_test_requests(args.count)
    context = create_context_with_annotations(requests)
    if args.write_benchmark_file or args.with_pyright:
        out_rel = build_benchmark_file(requests)
        context.file_path = str(out_rel)

    # Create resolvers
    builtin_registry = YamlBuiltinMethodRegistry()

    # 1. Self-contained only (no Pyright)
    print("\n[1/2] Running self-contained benchmark...")
    resolver_self = InferredTypeResolver(
        builtin_registry=builtin_registry,
        pyright_fallback=None,
        enable_pyright=False,
    )
    result_self = run_benchmark(
        "Self-Contained (No Pyright)",
        resolver_self,
        requests,
        context,
    )
    print_result(result_self)

    # 2. With Pyright fallback (if enabled)
    if args.with_pyright:
        print("\n[2/2] Running with Pyright fallback...")
        repo_root = Path(__file__).resolve().parents[2]
        pyright_fallback = PyrightFallbackAdapter(repo_root)

        if pyright_fallback.is_available():
            resolver_pyright = InferredTypeResolver(
                builtin_registry=builtin_registry,
                pyright_fallback=pyright_fallback,
                enable_pyright=True,
            )
            result_pyright = run_benchmark(
                "With Pyright Fallback",
                resolver_pyright,
                requests,
                context,
            )
            print_result(result_pyright)

            # Comparison
            print(f"\n{'=' * 60}")
            print("Comparison")
            print(f"{'=' * 60}")
            speedup = (
                result_self.inferences_per_sec / result_pyright.inferences_per_sec
                if result_pyright.inferences_per_sec > 0
                else 0
            )
            print(f"Self-contained is {speedup:.1f}x faster")
            print(f"Pyright calls saved: {result_pyright.pyright_calls:,} → 0")
        else:
            print("Pyright not available, skipping...")

    # Summary
    print(f"\n{'=' * 60}")
    print("Summary")
    print(f"{'=' * 60}")

    self_contained_rate = sum(
        result_self.coverage_by_source.get(s, 0) for s in ["annotation", "literal", "builtin_method", "call_graph"]
    )
    print(f"Self-Contained Coverage: {self_contained_rate * 100:.1f}%")
    print(f"Pyright Fallback Needed: {result_self.coverage_by_source.get('unknown', 0) * 100:.1f}%")

    print("\nConclusion:")
    if self_contained_rate >= 0.8:
        print("✅ Self-contained inference covers 80%+ of cases!")
        print("   Pyright fallback only needed for complex cases.")
    elif self_contained_rate >= 0.5:
        print("🟡 Self-contained inference covers 50-80% of cases.")
        print("   Consider expanding builtin method table.")
    else:
        print("🔴 Self-contained inference covers <50% of cases.")
        print("   Pyright fallback recommended for production.")


if __name__ == "__main__":
    main()
