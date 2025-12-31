#!/usr/bin/env python3
"""
UnifiedOrchestrator 벤치마크 러너

실제 대규모 리포지토리로 인덱싱 성능을 측정하고 리포트를 생성합니다.

Usage:
    python scripts/run_unified_benchmark.py
    python scripts/run_unified_benchmark.py --clone  # 리포지토리 클론부터 시작
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Any
import time


class BenchmarkRepo:
    """벤치마크 대상 리포지토리"""

    def __init__(self, name: str, git_url: str, size_category: str):
        self.name = name
        self.git_url = git_url
        self.size_category = size_category  # small, medium, large

    def __repr__(self):
        return f"BenchmarkRepo({self.name}, {self.size_category})"


# 벤치마크 대상 리포지토리들
BENCHMARK_REPOS = [
    # Small (< 1MB, < 100 files)
    BenchmarkRepo("typer", "https://github.com/tiangolo/typer.git", "small"),
    BenchmarkRepo("attrs", "https://github.com/python-attrs/attrs.git", "small"),
    # Medium (1-10MB, 100-1000 files)
    BenchmarkRepo("rich", "https://github.com/Textualize/rich.git", "medium"),
    BenchmarkRepo("httpx", "https://github.com/encode/httpx.git", "medium"),
    # Large (> 10MB, > 1000 files)
    BenchmarkRepo("django", "https://github.com/django/django.git", "large"),
    BenchmarkRepo("flask", "https://github.com/pallets/flask.git", "large"),
    BenchmarkRepo("pydantic", "https://github.com/pydantic/pydantic.git", "large"),
]


class UnifiedBenchmarkRunner:
    """UnifiedOrchestrator 벤치마크 실행 및 분석"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.repos_dir = base_dir / "tools" / "benchmark" / "repo-test"
        self.results_dir = base_dir / "packages" / "codegraph-ir" / "target" / "benchmark_results"
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def clone_repositories(self, force: bool = False):
        """벤치마크 리포지토리 클론"""
        print("\n" + "=" * 60)
        print("📦 Cloning Benchmark Repositories")
        print("=" * 60 + "\n")

        for repo in BENCHMARK_REPOS:
            category_dir = self.repos_dir / repo.size_category
            repo_path = category_dir / repo.name

            if repo_path.exists() and not force:
                print(f"✓ {repo.name} already exists, skipping")
                continue

            category_dir.mkdir(parents=True, exist_ok=True)

            print(f"🔄 Cloning {repo.name} ({repo.size_category})...")
            try:
                subprocess.run(
                    ["git", "clone", "--depth=1", repo.git_url, str(repo_path)], check=True, capture_output=True
                )
                print(f"✓ {repo.name} cloned successfully")
            except subprocess.CalledProcessError as e:
                print(f"✗ Failed to clone {repo.name}: {e}")

    def run_rust_benchmark(self) -> bool:
        """Rust 벤치마크 실행 (cargo test)"""
        print("\n" + "=" * 60)
        print("🚀 Running Rust Benchmark Suite")
        print("=" * 60 + "\n")

        try:
            result = subprocess.run(
                [
                    "cargo",
                    "test",
                    "--package",
                    "codegraph-ir",
                    "--bench",
                    "unified_orchestrator_bench",
                    "--",
                    "--ignored",
                    "--nocapture",
                ],
                cwd=self.base_dir,
                check=True,
                capture_output=False,  # Print to console
            )
            return result.returncode == 0
        except subprocess.CalledProcessError as e:
            print(f"\n❌ Benchmark failed: {e}")
            return False

    def run_single_repo_benchmark(self, repo: BenchmarkRepo) -> Dict[str, Any]:
        """단일 리포지토리 벤치마크 실행 (Python에서 직접)"""
        category_dir = self.repos_dir / repo.size_category
        repo_path = category_dir / repo.name

        if not repo_path.exists():
            print(f"⚠️  Repository not found: {repo_path}")
            return {}

        print(f"\n🔍 Benchmarking: {repo.name}")
        print(f"   Path: {repo_path}")

        # Rust 벤치마크 실행
        start_time = time.time()

        try:
            # TODO: Python 바인딩 구현 후 직접 호출 가능
            # from codegraph_ir import UnifiedOrchestrator, UnifiedOrchestratorConfig
            # config = UnifiedOrchestratorConfig(str(repo_path), repo.name)
            # orchestrator = UnifiedOrchestrator(config)
            # orchestrator.index_repository()

            # 현재는 Rust 벤치마크 사용
            result = subprocess.run(
                [
                    "cargo",
                    "test",
                    "--package",
                    "codegraph-ir",
                    "--bench",
                    "unified_orchestrator_bench",
                    "bench_small_fixture",
                    "--",
                    "--nocapture",
                ],
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                check=False,
            )

            duration = time.time() - start_time

            return {
                "repo_name": repo.name,
                "size_category": repo.size_category,
                "duration": duration,
                "success": result.returncode == 0,
                "output": result.stdout,
            }

        except Exception as e:
            print(f"❌ Failed: {e}")
            return {
                "repo_name": repo.name,
                "size_category": repo.size_category,
                "success": False,
                "error": str(e),
            }

    def analyze_results(self):
        """벤치마크 결과 분석 및 리포트 생성"""
        csv_path = self.results_dir / "benchmark_results.csv"

        if not csv_path.exists():
            print(f"\n⚠️  No results found at {csv_path}")
            return

        print("\n" + "=" * 60)
        print("📊 Analyzing Benchmark Results")
        print("=" * 60 + "\n")

        # CSV 파싱
        import csv

        results = []
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                results.append(row)

        if not results:
            print("⚠️  No results to analyze")
            return

        # 결과 출력
        print(f"📋 Total benchmarks: {len(results)}\n")

        for result in results:
            print(f"• {result['repo_name']}")
            print(f"  - Size: {float(result['size_mb']):.2f} MB")
            print(f"  - Nodes: {result['nodes']}")
            print(f"  - Duration: {float(result['duration_sec']):.2f}s")
            print(f"  - Throughput: {float(result['throughput_nodes_sec']):.0f} nodes/sec")
            print()

        # 통계
        total_nodes = sum(int(r["nodes"]) for r in results)
        total_duration = sum(float(r["duration_sec"]) for r in results)
        avg_throughput = sum(float(r["throughput_nodes_sec"]) for r in results) / len(results)

        print("📈 Summary Statistics:")
        print(f"  - Total nodes processed: {total_nodes:,}")
        print(f"  - Total duration: {total_duration:.2f}s")
        print(f"  - Average throughput: {avg_throughput:.0f} nodes/sec")

        # JSON 리포트 생성
        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_benchmarks": len(results),
            "total_nodes": total_nodes,
            "total_duration": total_duration,
            "average_throughput": avg_throughput,
            "results": results,
        }

        report_path = self.results_dir / "benchmark_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n📄 Report saved to: {report_path}")

    def generate_markdown_report(self):
        """마크다운 리포트 생성"""
        csv_path = self.results_dir / "benchmark_results.csv"

        if not csv_path.exists():
            return

        import csv

        results = []
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            results = list(reader)

        if not results:
            return

        md_content = f"""# UnifiedOrchestrator Benchmark Report

**Generated**: {time.strftime("%Y-%m-%d %H:%M:%S")}

## 📊 Summary

- **Total Benchmarks**: {len(results)}
- **Total Nodes**: {sum(int(r["nodes"]) for r in results):,}
- **Average Throughput**: {sum(float(r["throughput_nodes_sec"]) for r in results) / len(results):.0f} nodes/sec

## 📋 Detailed Results

| Repository | Size (MB) | Files | Nodes | Edges | Duration (s) | Throughput (nodes/s) |
|------------|-----------|-------|-------|-------|--------------|---------------------|
"""

        for r in results:
            md_content += f"| {r['repo_name']} | {float(r['size_mb']):.2f} | {r['file_count']} | {r['nodes']} | {r['edges']} | {float(r['duration_sec']):.2f} | {float(r['throughput_nodes_sec']):.0f} |\n"

        md_content += """
## 🏆 Performance Highlights

"""

        # Find best performers
        fastest = max(results, key=lambda r: float(r["throughput_nodes_sec"]))
        largest = max(results, key=lambda r: int(r["nodes"]))

        md_content += (
            f"- **Fastest**: {fastest['repo_name']} ({float(fastest['throughput_nodes_sec']):.0f} nodes/sec)\n"
        )
        md_content += f"- **Largest**: {largest['repo_name']} ({largest['nodes']} nodes)\n"

        md_path = self.results_dir / "BENCHMARK_REPORT.md"
        with open(md_path, "w") as f:
            f.write(md_content)

        print(f"📄 Markdown report saved to: {md_path}")


def main():
    parser = argparse.ArgumentParser(description="UnifiedOrchestrator Benchmark Runner")
    parser.add_argument("--clone", action="store_true", help="Clone repositories first")
    parser.add_argument("--force-clone", action="store_true", help="Force re-clone repositories")
    parser.add_argument("--analyze-only", action="store_true", help="Only analyze existing results")

    args = parser.parse_args()

    # Find codegraph root
    base_dir = Path(__file__).parent.parent

    runner = UnifiedBenchmarkRunner(base_dir)

    # Clone repositories if requested
    if args.clone or args.force_clone:
        runner.clone_repositories(force=args.force_clone)

    # Run benchmarks (skip if analyze-only)
    if not args.analyze_only:
        success = runner.run_rust_benchmark()

        if not success:
            print("\n❌ Benchmark failed!")
            sys.exit(1)

    # Analyze results
    runner.analyze_results()
    runner.generate_markdown_report()

    print("\n✅ Benchmark complete!")


if __name__ == "__main__":
    main()
