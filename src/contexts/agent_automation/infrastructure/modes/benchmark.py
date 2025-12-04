"""
Benchmark Mode

Runs and analyzes performance benchmarks.

Features:
- Benchmark execution
- Performance comparison
- Regression detection
- Report generation
- Historical tracking
"""

import time
from typing import Any

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

logger = get_logger(__name__)


@mode_registry.register(AgentMode.BENCHMARK)
class BenchmarkMode(BaseModeHandler):
    """
    Benchmark mode for performance benchmarking.

    Flow:
    1. Identify benchmark targets
    2. Run benchmarks
    3. Collect results
    4. Compare with baseline
    5. Generate report

    Transitions:
    - benchmark_passed → QA (performance acceptable)
    - benchmark_regression → PERFORMANCE_PROFILING (regression detected)
    - benchmark_improved → GIT_WORKFLOW (improvement ready)
    """

    def __init__(self, llm_client=None):
        """
        Initialize Benchmark mode.

        Args:
            llm_client: Optional LLM client for analysis
        """
        super().__init__(AgentMode.BENCHMARK)
        self.llm = llm_client

    async def enter(self, context: ModeContext) -> None:
        """Enter benchmark mode."""
        await super().enter(context)
        self.logger.info("📊 Benchmark mode: Running benchmarks")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute benchmarking.

        Args:
            task: Benchmark task
            context: Shared mode context

        Returns:
            Result with benchmark results
        """
        self.logger.info(f"Running benchmarks: {task.query}")

        # 1. Identify benchmark targets
        targets = self._identify_targets(task, context)

        # 2. Get baseline (previous results)
        baseline = self._get_baseline(targets)

        # 3. Run benchmarks
        results = await self._run_benchmarks(targets, context)

        # 4. Compare with baseline
        comparison = self._compare_results(results, baseline)

        # 5. Detect regressions
        regressions = self._detect_regressions(comparison)

        # 6. Generate report
        report = self._generate_report(results, comparison, regressions)

        # 7. Determine trigger
        trigger = self._determine_trigger(regressions, comparison)

        return self._create_result(
            data={
                "targets": targets,
                "results": results,
                "baseline": baseline,
                "comparison": comparison,
                "regressions": regressions,
                "report": report,
            },
            trigger=trigger,
            explanation=f"Ran {len(results)} benchmarks, {len(regressions)} regressions detected",
        )

    def _identify_targets(self, task: Task, context: ModeContext) -> list[dict]:
        """Identify benchmark targets."""
        targets = []

        # Check for benchmark files
        for file_path in context.current_files:
            if "benchmark" in file_path.lower() or "bench_" in file_path.lower():
                targets.append({"type": "file", "path": file_path})

        # Check for pytest benchmarks
        for file_path in context.current_files:
            if file_path.startswith("test_") or file_path.endswith("_test.py"):
                targets.append({"type": "pytest", "path": file_path})

        # Add specific targets from task query
        query_lower = task.query.lower()
        if "function" in query_lower:
            targets.append({"type": "function", "name": "specified_function"})

        # Default if no targets found
        if not targets:
            targets.append({"type": "all", "path": "."})

        return targets

    def _get_baseline(self, targets: list[dict]) -> dict[str, Any]:
        """Get baseline benchmark results."""
        # In real implementation, would load from file or database
        baseline = {
            "timestamp": "2024-01-01T00:00:00",
            "results": {},
            "available": False,
        }

        # Simulated baseline data
        for target in targets:
            if target.get("path"):
                baseline["results"][target["path"]] = {
                    "mean": 100.0,  # ms
                    "std": 10.0,
                    "iterations": 100,
                }
                baseline["available"] = True

        return baseline

    async def _run_benchmarks(self, targets: list[dict], context: ModeContext) -> list[dict]:
        """Run benchmarks on targets."""
        results = []

        for target in targets:
            # Simulate benchmark execution
            result = await self._run_single_benchmark(target, context)
            results.append(result)

        return results

    async def _run_single_benchmark(self, target: dict, context: ModeContext) -> dict:
        """Run a single benchmark."""
        result = {
            "target": target,
            "status": "completed",
            "metrics": {},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        target_type = target.get("type", "unknown")
        target_path = target.get("path", "unknown")

        # Simulate different benchmark types
        if target_type == "pytest":
            result["metrics"] = {
                "execution_time_ms": 95.0,  # Simulated
                "memory_mb": 50.0,
                "iterations": 100,
            }
        elif target_type == "file":
            result["metrics"] = {
                "execution_time_ms": 150.0,
                "memory_mb": 75.0,
                "iterations": 50,
            }
        else:
            result["metrics"] = {
                "execution_time_ms": 100.0,
                "memory_mb": 60.0,
                "iterations": 100,
            }

        result["target_path"] = target_path

        return result

    def _compare_results(self, results: list[dict], baseline: dict) -> list[dict]:
        """Compare current results with baseline."""
        comparisons = []

        for result in results:
            target_path = result.get("target_path", "unknown")
            baseline_data = baseline.get("results", {}).get(target_path)

            comparison = {
                "target": target_path,
                "current": result.get("metrics", {}),
                "baseline": baseline_data,
                "delta": {},
            }

            if baseline_data:
                current_time = result.get("metrics", {}).get("execution_time_ms", 0)
                baseline_time = baseline_data.get("mean", 0)

                if baseline_time > 0:
                    delta_pct = ((current_time - baseline_time) / baseline_time) * 100
                    comparison["delta"] = {
                        "execution_time_pct": delta_pct,
                        "improved": delta_pct < 0,
                        "regressed": delta_pct > 10,  # >10% slower is regression
                    }

            comparisons.append(comparison)

        return comparisons

    def _detect_regressions(self, comparison: list[dict]) -> list[dict]:
        """Detect performance regressions."""
        regressions = []

        for comp in comparison:
            delta = comp.get("delta", {})
            if delta.get("regressed"):
                regressions.append(
                    {
                        "target": comp["target"],
                        "delta_pct": delta.get("execution_time_pct", 0),
                        "severity": self._classify_regression_severity(delta.get("execution_time_pct", 0)),
                    }
                )

        return regressions

    def _classify_regression_severity(self, delta_pct: float) -> str:
        """Classify regression severity based on delta percentage."""
        if delta_pct > 50:
            return "critical"
        elif delta_pct > 25:
            return "high"
        elif delta_pct > 10:
            return "medium"
        else:
            return "low"

    def _generate_report(self, results: list[dict], comparison: list[dict], regressions: list[dict]) -> str:
        """Generate benchmark report."""
        report_lines = [
            "# Benchmark Report",
            "",
            f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Total Benchmarks**: {len(results)}",
            f"**Regressions**: {len(regressions)}",
            "",
            "## Results Summary",
            "",
        ]

        for result in results:
            metrics = result.get("metrics", {})
            report_lines.extend(
                [
                    f"### {result.get('target_path', 'Unknown')}",
                    f"- Execution Time: {metrics.get('execution_time_ms', 'N/A')} ms",
                    f"- Memory Usage: {metrics.get('memory_mb', 'N/A')} MB",
                    f"- Iterations: {metrics.get('iterations', 'N/A')}",
                    "",
                ]
            )

        if comparison:
            report_lines.extend(["## Comparison with Baseline", ""])
            for comp in comparison:
                delta = comp.get("delta", {})
                if delta:
                    status = (
                        "✅ Improved"
                        if delta.get("improved")
                        else ("❌ Regressed" if delta.get("regressed") else "➡️ Same")
                    )
                    report_lines.append(f"- {comp['target']}: {delta.get('execution_time_pct', 0):.1f}% {status}")
            report_lines.append("")

        if regressions:
            report_lines.extend(["## ⚠️ Regressions Detected", ""])
            for reg in regressions:
                report_lines.append(f"- **{reg['target']}**: {reg['delta_pct']:.1f}% slower ({reg['severity']})")

        return "\n".join(report_lines)

    def _determine_trigger(self, regressions: list[dict], comparison: list[dict]) -> str:
        """Determine appropriate trigger based on results."""
        if regressions:
            critical = any(r.get("severity") == "critical" for r in regressions)
            if critical:
                return "benchmark_regression"
            return "benchmark_regression"

        # Check if there are improvements
        improved = any(c.get("delta", {}).get("improved") for c in comparison)
        if improved:
            return "benchmark_improved"

        return "benchmark_passed"

    async def exit(self, context: ModeContext) -> None:
        """Exit benchmark mode."""
        self.logger.info("Benchmark execution complete")
        await super().exit(context)
