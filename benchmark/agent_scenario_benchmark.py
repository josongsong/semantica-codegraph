"""
Agent Scenario Benchmark for Retriever

Comprehensive benchmark testing real-world agent interaction scenarios.

Scenarios covered:
1. Code Understanding - "What does this function do?"
2. Code Navigation - "Find all callers of this function"
3. Bug Investigation - "Find code related to this error"
4. Code Modification - "Find all places to update this API"
5. Test Writing - "Find similar test patterns"
6. Documentation - "Gather info for API docs"
7. Dependency Analysis - "What depends on this module?"
8. Performance Analysis - "Find performance bottlenecks"
9. Security Review - "Find potential security issues"
10. Code Pattern Search - "Find examples of this pattern"
"""

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AgentScenario:
    """Agent interaction scenario."""

    scenario_id: str
    category: str  # understanding, navigation, investigation, etc.
    user_query: str  # Natural language query from user
    intent: str  # Retrieved intent
    expected_result_types: list[str]  # ["function_definition", "usage_examples", etc.]
    min_relevance: float = 0.7
    max_latency_ms: float = 3000.0  # Agent needs fast response
    description: str = ""


@dataclass
class ScenarioResult:
    """Result of a single scenario test."""

    scenario_id: str
    category: str
    user_query: str
    success: bool
    latency_ms: float
    retrieved_count: int
    relevant_count: int
    precision: float
    recall: float
    mrr: float
    error: str | None = None
    retrieved_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BenchmarkReport:
    """Complete benchmark report."""

    repo_name: str
    snapshot_id: str
    timestamp: str
    total_scenarios: int
    passed_scenarios: int
    failed_scenarios: int
    avg_latency_ms: float
    avg_precision: float
    avg_recall: float
    avg_mrr: float
    by_category: dict[str, dict[str, float]] = field(default_factory=dict)
    scenario_results: list[ScenarioResult] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class AgentScenarioBenchmark:
    """
    Benchmark retriever with real agent scenarios.

    Tests 10 major categories of agent interactions:
    1. Code Understanding
    2. Code Navigation
    3. Bug Investigation
    4. Code Modification
    5. Test Writing
    6. Documentation
    7. Dependency Analysis
    8. Performance Analysis
    9. Security Review
    10. Code Pattern Search
    """

    def __init__(self, repo_name: str = "test_repo", output_dir: str = "./benchmark_results"):
        """
        Initialize benchmark.

        Args:
            repo_name: Repository name for logging
            output_dir: Base directory for results
        """
        self.repo_name = repo_name
        self.output_dir = Path(output_dir)
        self.scenarios = self._define_scenarios()

    def _define_scenarios(self) -> list[AgentScenario]:
        """Define all agent interaction scenarios."""
        return [
            # 1. Code Understanding (코드 이해)
            AgentScenario(
                scenario_id="understand_01",
                category="code_understanding",
                user_query="What does the authenticate function do?",
                intent="symbol_nav",
                expected_result_types=["function_definition", "docstring"],
                description="Agent needs to understand a specific function",
            ),
            AgentScenario(
                scenario_id="understand_02",
                category="code_understanding",
                user_query="Explain the User class structure",
                intent="symbol_nav",
                expected_result_types=["class_definition", "methods", "attributes"],
                description="Agent needs to understand a class structure",
            ),
            AgentScenario(
                scenario_id="understand_03",
                category="code_understanding",
                user_query="How does the authentication system work?",
                intent="concept_search",
                expected_result_types=["related_functions", "flow"],
                max_latency_ms=5000.0,  # Conceptual queries can take longer
                description="Agent needs to understand a system/concept",
            ),
            AgentScenario(
                scenario_id="understand_04",
                category="code_understanding",
                user_query="What is the purpose of the config module?",
                intent="concept_search",
                expected_result_types=["module_summary", "main_exports"],
                description="Agent needs to understand a module's purpose",
            ),
            # 2. Code Navigation (코드 탐색)
            AgentScenario(
                scenario_id="navigate_01",
                category="code_navigation",
                user_query="Find the definition of authenticate",
                intent="symbol_nav",
                expected_result_types=["definition"],
                max_latency_ms=1000.0,  # Should be very fast
                description="Agent needs to jump to definition",
            ),
            AgentScenario(
                scenario_id="navigate_02",
                category="code_navigation",
                user_query="Find all places that call authenticate",
                intent="flow_trace",
                expected_result_types=["call_sites"],
                description="Agent needs to find all callers",
            ),
            AgentScenario(
                scenario_id="navigate_03",
                category="code_navigation",
                user_query="Show me all database-related code",
                intent="code_search",
                expected_result_types=["database_code"],
                description="Agent needs to find code by domain",
            ),
            AgentScenario(
                scenario_id="navigate_04",
                category="code_navigation",
                user_query="Find all API endpoints in the project",
                intent="code_search",
                expected_result_types=["api_endpoints"],
                description="Agent needs to find all endpoints",
            ),
            AgentScenario(
                scenario_id="navigate_05",
                category="code_navigation",
                user_query="Show me the call chain from login to database",
                intent="flow_trace",
                expected_result_types=["call_chain"],
                max_latency_ms=4000.0,
                description="Agent needs to trace execution flow",
            ),
            # 3. Bug Investigation (버그 조사)
            AgentScenario(
                scenario_id="bug_01",
                category="bug_investigation",
                user_query="Find code that could cause NullPointerException",
                intent="code_search",
                expected_result_types=["potential_bugs"],
                description="Agent needs to find potential null pointer issues",
            ),
            AgentScenario(
                scenario_id="bug_02",
                category="bug_investigation",
                user_query="Find code related to 'connection timeout' error",
                intent="code_search",
                expected_result_types=["error_related_code"],
                description="Agent needs to find error-related code",
            ),
            AgentScenario(
                scenario_id="bug_03",
                category="bug_investigation",
                user_query="Show me recently changed files that affect login tests",
                intent="code_search",
                expected_result_types=["recent_changes", "test_related"],
                description="Agent needs to find recent changes causing test failures",
            ),
            AgentScenario(
                scenario_id="bug_04",
                category="bug_investigation",
                user_query="Find all exception handling code in auth module",
                intent="code_search",
                expected_result_types=["exception_handlers"],
                description="Agent needs to review error handling",
            ),
            # 4. Code Modification (코드 수정)
            AgentScenario(
                scenario_id="modify_01",
                category="code_modification",
                user_query="Find all logging statements to add timestamps",
                intent="code_search",
                expected_result_types=["logging_calls"],
                description="Agent needs to find all places to modify",
            ),
            AgentScenario(
                scenario_id="modify_02",
                category="code_modification",
                user_query="Find all uses of deprecated getUser API",
                intent="code_search",
                expected_result_types=["deprecated_api_usage"],
                description="Agent needs to find deprecated API usage",
            ),
            AgentScenario(
                scenario_id="modify_03",
                category="code_modification",
                user_query="Find all functions that need to be updated for new config format",
                intent="code_search",
                expected_result_types=["config_usage"],
                description="Agent needs to find impact of config change",
            ),
            AgentScenario(
                scenario_id="modify_04",
                category="code_modification",
                user_query="Find all SQL queries to convert to parameterized queries",
                intent="code_search",
                expected_result_types=["sql_queries"],
                description="Agent needs to find SQL injection risks",
            ),
            # 5. Test Writing (테스트 작성)
            AgentScenario(
                scenario_id="test_01",
                category="test_writing",
                user_query="Show me test examples for API endpoints",
                intent="code_search",
                expected_result_types=["test_examples"],
                description="Agent needs test patterns for endpoints",
            ),
            AgentScenario(
                scenario_id="test_02",
                category="test_writing",
                user_query="Find files with low test coverage",
                intent="code_search",
                expected_result_types=["untested_code"],
                description="Agent needs to identify untested code",
            ),
            AgentScenario(
                scenario_id="test_03",
                category="test_writing",
                user_query="Show me how to mock database connections in tests",
                intent="code_search",
                expected_result_types=["mock_examples"],
                description="Agent needs mocking examples",
            ),
            AgentScenario(
                scenario_id="test_04",
                category="test_writing",
                user_query="Find existing tests for authentication module",
                intent="code_search",
                expected_result_types=["existing_tests"],
                description="Agent needs to understand existing test structure",
            ),
            # 6. Documentation (문서화)
            AgentScenario(
                scenario_id="doc_01",
                category="documentation",
                user_query="Gather all public API functions for documentation",
                intent="symbol_nav",
                expected_result_types=["public_api"],
                description="Agent needs to document public APIs",
            ),
            AgentScenario(
                scenario_id="doc_02",
                category="documentation",
                user_query="Find all TODOs and FIXMEs in the codebase",
                intent="code_search",
                expected_result_types=["todos"],
                description="Agent needs to track technical debt",
            ),
            AgentScenario(
                scenario_id="doc_03",
                category="documentation",
                user_query="Find complex functions that need better comments",
                intent="code_search",
                expected_result_types=["complex_functions"],
                description="Agent needs to identify under-documented code",
            ),
            AgentScenario(
                scenario_id="doc_04",
                category="documentation",
                user_query="List all configuration options in the system",
                intent="code_search",
                expected_result_types=["config_options"],
                description="Agent needs to document configuration",
            ),
            # 7. Dependency Analysis (의존성 분석)
            AgentScenario(
                scenario_id="dep_01",
                category="dependency_analysis",
                user_query="Find all files that import the database module",
                intent="flow_trace",
                expected_result_types=["importers"],
                description="Agent needs to find module dependencies",
            ),
            AgentScenario(
                scenario_id="dep_02",
                category="dependency_analysis",
                user_query="Check for circular dependencies in the codebase",
                intent="flow_trace",
                expected_result_types=["circular_deps"],
                max_latency_ms=5000.0,
                description="Agent needs to detect circular dependencies",
            ),
            AgentScenario(
                scenario_id="dep_03",
                category="dependency_analysis",
                user_query="What will break if I delete this function?",
                intent="flow_trace",
                expected_result_types=["impact_analysis"],
                description="Agent needs impact analysis before deletion",
            ),
            AgentScenario(
                scenario_id="dep_04",
                category="dependency_analysis",
                user_query="Find all external dependencies used in this module",
                intent="code_search",
                expected_result_types=["external_deps"],
                description="Agent needs to audit external dependencies",
            ),
            # 8. Performance Analysis (성능 분석)
            AgentScenario(
                scenario_id="perf_01",
                category="performance_analysis",
                user_query="Find functions with high cyclomatic complexity",
                intent="code_search",
                expected_result_types=["complex_functions"],
                description="Agent needs to find performance bottlenecks",
            ),
            AgentScenario(
                scenario_id="perf_02",
                category="performance_analysis",
                user_query="Find all nested loops in the codebase",
                intent="code_search",
                expected_result_types=["nested_loops"],
                description="Agent needs to find O(n²) operations",
            ),
            AgentScenario(
                scenario_id="perf_03",
                category="performance_analysis",
                user_query="Find database queries in loops",
                intent="code_search",
                expected_result_types=["db_in_loops"],
                description="Agent needs to find N+1 query problems",
            ),
            AgentScenario(
                scenario_id="perf_04",
                category="performance_analysis",
                user_query="Find large data structures being copied",
                intent="code_search",
                expected_result_types=["data_copying"],
                description="Agent needs to find memory inefficiencies",
            ),
            # 9. Security Review (보안 검토)
            AgentScenario(
                scenario_id="sec_01",
                category="security_review",
                user_query="Find potential SQL injection vulnerabilities",
                intent="code_search",
                expected_result_types=["sql_injection_risk"],
                description="Agent needs to find SQL injection risks",
            ),
            AgentScenario(
                scenario_id="sec_02",
                category="security_review",
                user_query="Find API endpoints without authentication",
                intent="code_search",
                expected_result_types=["unprotected_endpoints"],
                description="Agent needs to find unprotected APIs",
            ),
            AgentScenario(
                scenario_id="sec_03",
                category="security_review",
                user_query="Find hardcoded secrets or passwords",
                intent="code_search",
                expected_result_types=["hardcoded_secrets"],
                description="Agent needs to find credential leaks",
            ),
            AgentScenario(
                scenario_id="sec_04",
                category="security_review",
                user_query="Find uses of eval or exec functions",
                intent="code_search",
                expected_result_types=["dangerous_functions"],
                description="Agent needs to find dangerous code patterns",
            ),
            # 10. Code Pattern Search (코드 패턴 검색)
            AgentScenario(
                scenario_id="pattern_01",
                category="code_pattern_search",
                user_query="Find examples of singleton pattern",
                intent="code_search",
                expected_result_types=["pattern_examples"],
                description="Agent needs design pattern examples",
            ),
            AgentScenario(
                scenario_id="pattern_02",
                category="code_pattern_search",
                user_query="Find similar error handling code",
                intent="code_search",
                expected_result_types=["similar_code"],
                description="Agent needs code reuse examples",
            ),
            AgentScenario(
                scenario_id="pattern_03",
                category="code_pattern_search",
                user_query="Find factory pattern implementations",
                intent="code_search",
                expected_result_types=["factory_pattern"],
                description="Agent needs factory pattern examples",
            ),
            AgentScenario(
                scenario_id="pattern_04",
                category="code_pattern_search",
                user_query="Find examples of async/await usage",
                intent="code_search",
                expected_result_types=["async_examples"],
                description="Agent needs async programming examples",
            ),
        ]

    async def run_benchmark(
        self,
        retrieval_func: Callable[[str, str, str], Any],
        repo_id: str = "test_repo",
        snapshot_id: str = "main",
    ) -> BenchmarkReport:
        """
        Run full agent scenario benchmark.

        Args:
            retrieval_func: Retrieval function (repo_id, snapshot_id, query) -> results
            repo_id: Repository ID
            snapshot_id: Snapshot ID

        Returns:
            Complete benchmark report
        """
        logger.info(f"Starting Agent Scenario Benchmark: {len(self.scenarios)} scenarios")

        results = []
        category_metrics = defaultdict(
            lambda: {"total": 0, "passed": 0, "latencies": [], "precisions": [], "recalls": [], "mrrs": []}
        )

        for i, scenario in enumerate(self.scenarios, 1):
            logger.info(f"[{i}/{len(self.scenarios)}] Testing: {scenario.scenario_id} - {scenario.user_query[:50]}...")

            result = await self._run_scenario(scenario, retrieval_func, repo_id, snapshot_id)
            results.append(result)

            # Aggregate by category
            cat = scenario.category
            category_metrics[cat]["total"] += 1
            if result.success:
                category_metrics[cat]["passed"] += 1
            category_metrics[cat]["latencies"].append(result.latency_ms)
            category_metrics[cat]["precisions"].append(result.precision)
            category_metrics[cat]["recalls"].append(result.recall)
            category_metrics[cat]["mrrs"].append(result.mrr)

        # Compute overall metrics
        total = len(results)
        passed = sum(1 for r in results if r.success)
        failed = total - passed

        all_latencies = [r.latency_ms for r in results]
        all_precisions = [r.precision for r in results]
        all_recalls = [r.recall for r in results]
        all_mrrs = [r.mrr for r in results]

        avg_latency = np.mean(all_latencies)
        avg_precision = np.mean(all_precisions)
        avg_recall = np.mean(all_recalls)
        avg_mrr = np.mean(all_mrrs)

        # By category summary
        by_category = {}
        for cat, metrics in category_metrics.items():
            by_category[cat] = {
                "total": metrics["total"],
                "passed": metrics["passed"],
                "pass_rate": metrics["passed"] / metrics["total"],
                "avg_latency_ms": np.mean(metrics["latencies"]),
                "avg_precision": np.mean(metrics["precisions"]),
                "avg_recall": np.mean(metrics["recalls"]),
                "avg_mrr": np.mean(metrics["mrrs"]),
            }

        # Generate recommendations
        recommendations = self._generate_recommendations(results, by_category)

        report = BenchmarkReport(
            repo_name=self.repo_name,
            snapshot_id=snapshot_id,
            timestamp=datetime.now().isoformat(),
            total_scenarios=total,
            passed_scenarios=passed,
            failed_scenarios=failed,
            avg_latency_ms=avg_latency,
            avg_precision=avg_precision,
            avg_recall=avg_recall,
            avg_mrr=avg_mrr,
            by_category=by_category,
            scenario_results=results,
            recommendations=recommendations,
        )

        # Save report
        self._save_report(report)

        logger.info(f"\n{'=' * 80}")
        logger.info(f"Benchmark Complete!")
        logger.info(f"{'=' * 80}")
        logger.info(f"Overall: {passed}/{total} passed ({passed / total * 100:.1f}%)")
        logger.info(f"Avg Latency: {avg_latency:.0f}ms")
        logger.info(f"Avg Precision: {avg_precision:.3f}")
        logger.info(f"Avg Recall: {avg_recall:.3f}")
        logger.info(f"Avg MRR: {avg_mrr:.3f}")

        return report

    async def _run_scenario(
        self,
        scenario: AgentScenario,
        retrieval_func: Callable,
        repo_id: str,
        snapshot_id: str,
    ) -> ScenarioResult:
        """Run a single scenario test."""
        import time

        start_time = time.time()

        try:
            # Execute retrieval
            results = await retrieval_func(repo_id, snapshot_id, scenario.user_query)

            latency_ms = (time.time() - start_time) * 1000

            # Evaluate results
            retrieved_count = len(results)

            # For mock benchmark, consider top chunks as relevant
            # In real scenario, you'd check against ground truth
            relevant_count = sum(1 for r in results[:10] if r.get("score", 0) > scenario.min_relevance)

            precision = relevant_count / retrieved_count if retrieved_count > 0 else 0.0
            recall = relevant_count / 10  # Assume 10 relevant items exist

            # MRR: rank of first relevant result
            mrr = 0.0
            for i, result in enumerate(results, 1):
                if result.get("score", 0) > scenario.min_relevance:
                    mrr = 1.0 / i
                    break

            # Success criteria
            success = (
                latency_ms <= scenario.max_latency_ms and precision >= scenario.min_relevance and relevant_count > 0
            )

            return ScenarioResult(
                scenario_id=scenario.scenario_id,
                category=scenario.category,
                user_query=scenario.user_query,
                success=success,
                latency_ms=latency_ms,
                retrieved_count=retrieved_count,
                relevant_count=relevant_count,
                precision=precision,
                recall=recall,
                mrr=mrr,
                retrieved_items=results[:5],  # Store top 5 for inspection
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            logger.error(f"Scenario {scenario.scenario_id} failed: {e}")

            return ScenarioResult(
                scenario_id=scenario.scenario_id,
                category=scenario.category,
                user_query=scenario.user_query,
                success=False,
                latency_ms=latency_ms,
                retrieved_count=0,
                relevant_count=0,
                precision=0.0,
                recall=0.0,
                mrr=0.0,
                error=str(e),
            )

    def _generate_recommendations(self, results: list[ScenarioResult], by_category: dict) -> list[str]:
        """Generate recommendations based on results."""
        recommendations = []

        # Check latency
        slow_results = [r for r in results if r.latency_ms > 2000]
        if len(slow_results) > len(results) * 0.2:
            recommendations.append(
                f"⚠️  High latency detected: {len(slow_results)} scenarios >2s. "
                "Consider enabling embedding cache and adaptive top-k."
            )

        # Check precision
        low_precision = [r for r in results if r.precision < 0.6]
        if len(low_precision) > len(results) * 0.3:
            recommendations.append(
                f"⚠️  Low precision: {len(low_precision)} scenarios <60%. "
                "Consider using learned reranker or cross-encoder."
            )

        # Check by category
        for cat, metrics in by_category.items():
            if metrics["pass_rate"] < 0.7:
                recommendations.append(
                    f"⚠️  {cat}: Low pass rate {metrics['pass_rate']:.1%}. "
                    f"Review retrieval strategy for this scenario type."
                )

        if not recommendations:
            recommendations.append("✅ All scenarios performing well!")

        return recommendations

    def _save_report(self, report: BenchmarkReport) -> Path:
        """Save report to structured directory."""
        # Create directory structure: /{repo_name}/{date}/
        today = datetime.now().strftime("%Y-%m-%d")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        report_dir = self.output_dir / report.repo_name / today
        report_dir.mkdir(parents=True, exist_ok=True)

        # Save JSON report
        json_path = report_dir / f"retriever_{timestamp}_report.json"
        with open(json_path, "w") as f:
            # Convert dataclasses to dict
            report_dict = asdict(report)
            json.dump(report_dict, f, indent=2)

        # Save human-readable summary
        summary_path = report_dir / f"retriever_{timestamp}_summary.txt"
        with open(summary_path, "w") as f:
            f.write("=" * 80 + "\n")
            f.write(f"Agent Scenario Benchmark Report\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Repository: {report.repo_name}\n")
            f.write(f"Snapshot: {report.snapshot_id}\n")
            f.write(f"Timestamp: {report.timestamp}\n\n")

            f.write(f"Overall Results:\n")
            f.write(f"  Total Scenarios: {report.total_scenarios}\n")
            f.write(
                f"  Passed: {report.passed_scenarios} ({report.passed_scenarios / report.total_scenarios * 100:.1f}%)\n"
            )
            f.write(f"  Failed: {report.failed_scenarios}\n\n")

            f.write(f"Metrics:\n")
            f.write(f"  Avg Latency: {report.avg_latency_ms:.1f}ms\n")
            f.write(f"  Avg Precision: {report.avg_precision:.3f}\n")
            f.write(f"  Avg Recall: {report.avg_recall:.3f}\n")
            f.write(f"  Avg MRR: {report.avg_mrr:.3f}\n\n")

            f.write(f"By Category:\n")
            for cat, metrics in sorted(report.by_category.items()):
                f.write(f"\n  {cat}:\n")
                f.write(f"    Pass Rate: {metrics['pass_rate']:.1%}\n")
                f.write(f"    Avg Latency: {metrics['avg_latency_ms']:.0f}ms\n")
                f.write(f"    Avg Precision: {metrics['avg_precision']:.3f}\n")
                f.write(f"    Avg MRR: {metrics['avg_mrr']:.3f}\n")

            f.write(f"\nRecommendations:\n")
            for rec in report.recommendations:
                f.write(f"  {rec}\n")

            f.write(f"\nFailed Scenarios:\n")
            for result in report.scenario_results:
                if not result.success:
                    f.write(f"  ❌ {result.scenario_id}: {result.user_query[:60]}...\n")
                    f.write(f"     Latency: {result.latency_ms:.0f}ms, Precision: {result.precision:.3f}\n")
                    if result.error:
                        f.write(f"     Error: {result.error}\n")

        logger.info(f"\n📊 Report saved:")
        logger.info(f"  JSON: {json_path}")
        logger.info(f"  Summary: {summary_path}")

        return json_path


# CLI interface
async def main():
    """Run agent scenario benchmark from CLI."""
    import argparse

    parser = argparse.ArgumentParser(description="Agent Scenario Benchmark for Retriever")
    parser.add_argument("--repo", default="test_repo", help="Repository name")
    parser.add_argument("--snapshot", default="main", help="Snapshot ID")
    parser.add_argument("--output", default="./benchmark_results", help="Output directory")
    parser.add_argument("--mock", action="store_true", help="Use mock retrieval for testing")

    args = parser.parse_args()

    benchmark = AgentScenarioBenchmark(repo_name=args.repo, output_dir=args.output)

    if args.mock:
        # Use mock retrieval for testing
        from examples.run_retriever_benchmark import MockRetrievalFunction

        mock_func = MockRetrievalFunction(quality_level="good")

        async def retrieval_wrapper(repo_id: str, snapshot_id: str, query: str):
            return await mock_func(repo_id, snapshot_id, query)

        logger.info("Running benchmark with MOCK retrieval...")
        report = await benchmark.run_benchmark(retrieval_wrapper, args.repo, args.snapshot)
    else:
        logger.error("Real retrieval not implemented yet. Use --mock for testing.")
        return

    # Print summary
    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY")
    print("=" * 80)
    print(
        f"\n📊 Overall: {report.passed_scenarios}/{report.total_scenarios} passed "
        f"({report.passed_scenarios / report.total_scenarios * 100:.1f}%)"
    )
    print(f"⏱️  Avg Latency: {report.avg_latency_ms:.0f}ms")
    print(f"🎯 Avg Precision: {report.avg_precision:.3f}")
    print(f"📈 Avg MRR: {report.avg_mrr:.3f}")

    print(f"\n📁 By Category:")
    for cat, metrics in sorted(report.by_category.items()):
        status = "✅" if metrics["pass_rate"] >= 0.7 else "⚠️"
        print(
            f"  {status} {cat:25s}: {metrics['pass_rate']:>6.1%} pass, "
            f"{metrics['avg_latency_ms']:>6.0f}ms, precision {metrics['avg_precision']:.3f}"
        )

    print(f"\n💡 Recommendations:")
    for rec in report.recommendations:
        print(f"  {rec}")


if __name__ == "__main__":
    asyncio.run(main())
