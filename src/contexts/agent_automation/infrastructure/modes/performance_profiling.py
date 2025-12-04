"""
Performance Profiling Mode

Analyzes and optimizes code performance.

Features:
- Hotspot detection
- Memory usage analysis
- Algorithmic complexity estimation
- Performance bottleneck identification
- Optimization suggestions
"""

import ast
import re
from typing import Any

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

logger = get_logger(__name__)


@mode_registry.register(AgentMode.PERFORMANCE_PROFILING)
class PerformanceProfilingMode(BaseModeHandler):
    """
    Performance Profiling mode for performance analysis and optimization.

    Flow:
    1. Analyze code structure
    2. Estimate algorithmic complexity
    3. Detect potential hotspots
    4. Identify memory issues
    5. Generate optimization suggestions

    Transitions:
    - perf_optimal → IDLE (no issues found)
    - perf_issues → IMPLEMENTATION (optimizations needed)
    - critical_perf → REFACTOR (major refactoring needed)
    """

    def __init__(self, llm_client=None):
        """
        Initialize Performance Profiling mode.

        Args:
            llm_client: Optional LLM client for intelligent suggestions
        """
        super().__init__(AgentMode.PERFORMANCE_PROFILING)
        self.llm = llm_client

    async def enter(self, context: ModeContext) -> None:
        """Enter performance profiling mode."""
        await super().enter(context)
        self.logger.info("⚡ Performance Profiling mode: Analyzing performance")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute performance analysis.

        Args:
            task: Profiling task
            context: Shared mode context

        Returns:
            Result with performance analysis
        """
        self.logger.info(f"Profiling: {task.query}")

        # 1. Analyze code complexity
        complexity_analysis = self._analyze_complexity(context.pending_changes)

        # 2. Detect hotspots
        hotspots = self._detect_hotspots(context.pending_changes)

        # 3. Analyze memory patterns
        memory_analysis = self._analyze_memory(context.pending_changes)

        # 4. Identify bottlenecks
        bottlenecks = self._identify_bottlenecks(complexity_analysis, hotspots, memory_analysis)

        # 5. Generate optimization suggestions
        suggestions = await self._generate_suggestions(bottlenecks)

        # 6. Calculate performance score
        score = self._calculate_score(bottlenecks)

        report = {
            "complexity": complexity_analysis,
            "hotspots": hotspots,
            "memory": memory_analysis,
            "bottlenecks": bottlenecks,
            "suggestions": suggestions,
            "score": score,
        }

        # 7. Determine trigger
        trigger = self._determine_trigger(score, bottlenecks)

        return self._create_result(
            data=report,
            trigger=trigger,
            explanation=f"Performance score: {score}/100, {len(bottlenecks)} bottlenecks, {len(hotspots)} hotspots",
        )

    def _analyze_complexity(self, pending_changes: list[dict]) -> dict[str, Any]:
        """Analyze algorithmic complexity of code."""
        analysis = {"functions": [], "overall_complexity": "O(1)", "warnings": []}

        for change in pending_changes:
            content = change.get("content", "")
            file_path = change.get("file_path", "")

            if not file_path.endswith(".py"):
                continue

            try:
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        func_analysis = self._analyze_function_complexity(node)
                        func_analysis["file"] = file_path
                        analysis["functions"].append(func_analysis)

            except SyntaxError:
                continue

        # Determine overall complexity
        complexities = [f["complexity"] for f in analysis["functions"]]
        if any("O(n²)" in c or "O(n^2)" in c for c in complexities):
            analysis["overall_complexity"] = "O(n²)"
        elif any("O(n log n)" in c for c in complexities):
            analysis["overall_complexity"] = "O(n log n)"
        elif any("O(n)" in c for c in complexities):
            analysis["overall_complexity"] = "O(n)"

        return analysis

    def _analyze_function_complexity(self, func_node: ast.FunctionDef) -> dict:
        """Analyze complexity of a single function."""
        result = {
            "name": func_node.name,
            "line": func_node.lineno,
            "complexity": "O(1)",
            "nested_loops": 0,
            "recursive": False,
        }

        loop_depth = 0
        max_loop_depth = 0

        for node in ast.walk(func_node):
            # Count nested loops
            if isinstance(node, ast.For | ast.While):
                loop_depth += 1
                max_loop_depth = max(max_loop_depth, loop_depth)

            # Check for recursion
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == func_node.name:
                    result["recursive"] = True

        result["nested_loops"] = max_loop_depth

        # Estimate complexity based on loops
        if max_loop_depth == 0:
            result["complexity"] = "O(1)"
        elif max_loop_depth == 1:
            result["complexity"] = "O(n)"
        elif max_loop_depth == 2:
            result["complexity"] = "O(n²)"
        else:
            result["complexity"] = f"O(n^{max_loop_depth})"

        if result["recursive"]:
            result["complexity"] += " (recursive)"

        return result

    def _detect_hotspots(self, pending_changes: list[dict]) -> list[dict]:
        """Detect potential performance hotspots."""
        hotspots = []

        patterns = [
            (r"for .+ in .+:\s*for .+ in", "Nested loop", "high"),
            (r"\.append\(.+\) in .+loop", "List append in loop", "medium"),
            (r"\+ \"|\' \+", "String concatenation", "low"),
            (r"time\.sleep", "Sleep/blocking call", "medium"),
            (r"open\(.+\).*for .+ in", "File I/O in loop", "high"),
            (r"requests\.(get|post|put|delete)", "HTTP request", "medium"),
            (r"\.query\(|\.execute\(", "Database query", "medium"),
        ]

        for change in pending_changes:
            content = change.get("content", "")
            file_path = change.get("file_path", "")
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                for pattern, description, severity in patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        hotspots.append(
                            {
                                "file": file_path,
                                "line": i,
                                "type": description,
                                "severity": severity,
                                "code": line.strip()[:50],
                            }
                        )

        return hotspots

    def _analyze_memory(self, pending_changes: list[dict]) -> dict[str, Any]:
        """Analyze memory usage patterns."""
        analysis = {"issues": [], "large_objects": [], "memory_leaks_potential": []}

        for change in pending_changes:
            content = change.get("content", "")
            file_path = change.get("file_path", "")

            # Check for potential memory issues
            if "global " in content:
                analysis["issues"].append(
                    {"file": file_path, "type": "global_variable", "message": "Global variables can cause memory leaks"}
                )

            # Large list/dict comprehensions
            if re.search(r"\[.{50,}\]", content):
                analysis["large_objects"].append(
                    {"file": file_path, "type": "large_comprehension", "message": "Large list comprehension detected"}
                )

            # Unclosed resources
            if "open(" in content and "with " not in content:
                analysis["memory_leaks_potential"].append(
                    {
                        "file": file_path,
                        "type": "unclosed_file",
                        "message": "File opened without context manager",
                    }
                )

        return analysis

    def _identify_bottlenecks(self, complexity: dict, hotspots: list[dict], memory: dict) -> list[dict]:
        """Identify performance bottlenecks."""
        bottlenecks = []

        # High complexity functions
        for func in complexity.get("functions", []):
            if "O(n²)" in func["complexity"] or func["nested_loops"] >= 2:
                bottlenecks.append(
                    {
                        "type": "complexity",
                        "location": f"{func['file']}:{func['line']}",
                        "function": func["name"],
                        "severity": "high",
                        "description": f"High complexity: {func['complexity']}",
                    }
                )

        # High severity hotspots
        for hotspot in hotspots:
            if hotspot["severity"] == "high":
                bottlenecks.append(
                    {
                        "type": "hotspot",
                        "location": f"{hotspot['file']}:{hotspot['line']}",
                        "severity": "high",
                        "description": hotspot["type"],
                    }
                )

        # Memory issues
        for issue in memory.get("memory_leaks_potential", []):
            bottlenecks.append(
                {
                    "type": "memory",
                    "location": issue["file"],
                    "severity": "medium",
                    "description": issue["message"],
                }
            )

        return bottlenecks

    async def _generate_suggestions(self, bottlenecks: list[dict]) -> list[dict]:
        """Generate optimization suggestions."""
        suggestions = []

        optimization_tips = {
            "complexity": [
                "Consider using more efficient algorithms",
                "Use caching/memoization for repeated calculations",
                "Consider using generators instead of lists",
            ],
            "hotspot": [
                "Move I/O operations outside loops",
                "Use batch operations where possible",
                "Consider async/concurrent processing",
            ],
            "memory": [
                "Use context managers for resource handling",
                "Consider using generators for large datasets",
                "Clear unused variables explicitly",
            ],
        }

        for bottleneck in bottlenecks:
            b_type = bottleneck["type"]
            tips = optimization_tips.get(b_type, ["Review and optimize manually"])

            suggestions.append(
                {
                    "bottleneck": bottleneck,
                    "tips": tips,
                    "priority": "high" if bottleneck["severity"] == "high" else "medium",
                }
            )

        return suggestions

    def _calculate_score(self, bottlenecks: list[dict]) -> int:
        """Calculate performance score (0-100)."""
        score = 100

        for b in bottlenecks:
            if b["severity"] == "high":
                score -= 20
            elif b["severity"] == "medium":
                score -= 10
            else:
                score -= 5

        return max(0, score)

    def _determine_trigger(self, score: int, bottlenecks: list[dict]) -> str:
        """Determine appropriate trigger based on analysis."""
        critical = sum(1 for b in bottlenecks if b["severity"] == "high")

        if critical >= 3 or score < 50:
            return "critical_perf"
        elif score < 80:
            return "perf_issues"
        else:
            return "perf_optimal"

    async def exit(self, context: ModeContext) -> None:
        """Exit performance profiling mode."""
        self.logger.info("Performance profiling complete")
        await super().exit(context)
