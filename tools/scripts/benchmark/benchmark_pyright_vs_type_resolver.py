#!/usr/bin/env python3
"""
Pyright vs Internal TypeResolver micro-benchmark.

목표:
- Pyright(외부 타입체커/LSP hover 기반)로 심볼 타입 조회 성능 측정
- 내부 TypeResolver(문자열 annotation → TypeEntity) 성능 측정
- 동일한 (N개의) 타입 선언 워크로드로 벽시계 시간 비교

Usage:
  python scripts/benchmark/benchmark_pyright_vs_type_resolver.py --vars 5000
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

# reduce log noise for benchmarking
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("PYTHONWARNINGS", "ignore")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_bench_source(var_count: int) -> tuple[str, list[str], list[tuple[int, int]], int]:
    """
    Returns:
      - source text
      - annotations list aligned with variables
      - locations (line, col) for variable name hover (1-indexed, 0-indexed)
      - first_var_line: line number where variables start
    """
    annos_pool = [
        "int",
        "str",
        "float",
        "bool",
        "bytes",
        "list[int]",
        "dict[str, int]",
        "set[str]",
        "tuple[int, str]",
        "Optional[str]",
        "Union[int, str]",
        "Path",
        "datetime",
        "MyLocal",
        "list[MyLocal]",
    ]

    header = [
        "from __future__ import annotations",
        "from dataclasses import dataclass",
        "from datetime import datetime",
        "from pathlib import Path",
        "from typing import Optional, Union",
        "",
        "@dataclass",
        "class MyLocal:",
        "    x: int = 1",
        "",
    ]
    first_var_line = len(header) + 1  # 1-indexed

    lines: list[str] = list(header)
    annotations: list[str] = []
    locations: list[tuple[int, int]] = []

    for i in range(var_count):
        anno = annos_pool[i % len(annos_pool)]
        var = f"v{i}"
        # simple value assignments to keep file valid
        if anno in {"int"}:
            value = "123"
        elif anno in {"str"}:
            value = '"hello"'
        elif anno in {"float"}:
            value = "3.14"
        elif anno in {"bool"}:
            value = "True"
        elif anno in {"bytes"}:
            value = 'b"hi"'
        elif anno.startswith("list["):
            value = "[]"
        elif anno.startswith("dict["):
            value = "{}"
        elif anno.startswith("set["):
            value = "set()"
        elif anno.startswith("tuple["):
            value = "(1, 'a')"
        elif "Optional" in anno or "Union" in anno:
            value = "None"
        elif anno == "Path":
            value = 'Path("x")'
        elif anno == "datetime":
            value = "datetime.now()"
        elif anno == "MyLocal":
            value = "MyLocal()"
        else:
            value = "None"

        line = f"{var}: {anno} = {value}"
        lines.append(line)
        annotations.append(anno)
        # hover at variable name start (col=0)
        locations.append((first_var_line + i, 0))

    return "\n".join(lines) + "\n", annotations, locations, first_var_line


def bench_internal_type_resolver(annotations: list[str]) -> dict[str, float]:
    from codegraph_engine.code_foundation.infrastructure.semantic_ir.typing.resolver import TypeResolver

    r = TypeResolver(repo_id="bench")
    r.set_context("scripts/benchmark/_temp/bench_target.py")

    # warmup
    for a in annotations[:200]:
        r.resolve_type(a)

    start = time.perf_counter()
    for a in annotations:
        r.resolve_type(a)
    elapsed = time.perf_counter() - start

    return {
        "elapsed_s": elapsed,
        "items": float(len(annotations)),
        "items_per_s": (len(annotations) / elapsed) if elapsed > 0 else 0.0,
    }


def bench_pyright_hover(file_rel: Path, source: str, locations: list[tuple[int, int]]) -> dict[str, float]:
    from codegraph_engine.code_foundation.infrastructure.ir.external_analyzers.pyright_adapter import (
        PyrightExternalAnalyzer,
    )

    root = repo_root()
    t0 = time.perf_counter()
    analyzer = PyrightExternalAnalyzer(root)
    analyzer.open_file(file_rel, source)
    t_open = time.perf_counter() - t0

    # "cold" first query: usually includes initial analysis cost
    warm_n = min(50, len(locations))
    t1 = time.perf_counter()
    analyzer.analyze_file_locations(file_rel, locations[:warm_n])
    t_first_batch = time.perf_counter() - t1

    # steady-state hover cost (after warm)
    t2 = time.perf_counter()
    analyzer.analyze_file_locations(file_rel, locations)
    t_all = time.perf_counter() - t2

    try:
        analyzer.shutdown()
    except Exception:
        pass

    return {
        "open_s": t_open,
        "first_batch_s": t_first_batch,
        "all_locations_s": t_all,
        "items": float(len(locations)),
        "items_per_s": (len(locations) / t_all) if t_all > 0 else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vars", type=int, default=5000, help="number of annotated variables")
    ap.add_argument("--out", default="_temp_test/type_resolver_bench/bench_target.py", help="output file path")
    args = ap.parse_args()

    root = repo_root()
    out_rel = Path(args.out)
    out_abs = root / out_rel
    out_abs.parent.mkdir(parents=True, exist_ok=True)

    source, annotations, locations, first_var_line = build_bench_source(args.vars)
    out_abs.write_text(source, encoding="utf-8")

    print("== Benchmark: Pyright vs Internal TypeResolver ==")
    print(f"file: {out_rel}")
    print(f"vars: {args.vars} (first_var_line={first_var_line})")

    internal = bench_internal_type_resolver(annotations)
    print("\n[Internal TypeResolver]")
    print(f"elapsed: {internal['elapsed_s'] * 1000:.2f} ms")
    print(f"throughput: {internal['items_per_s']:.0f} items/s")

    pyright = bench_pyright_hover(out_rel, source, locations)
    print("\n[Pyright hover (LSP)]")
    print(f"open: {pyright['open_s'] * 1000:.2f} ms")
    print(f"first_batch({min(50, args.vars)} loc): {pyright['first_batch_s'] * 1000:.2f} ms")
    print(f"all_locations: {pyright['all_locations_s'] * 1000:.2f} ms")
    print(f"throughput: {pyright['items_per_s']:.0f} items/s")

    if pyright["items_per_s"] > 0:
        ratio = internal["items_per_s"] / pyright["items_per_s"]
        print("\n[Comparison]")
        print(f"internal vs pyright throughput: {ratio:.2f}x")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
