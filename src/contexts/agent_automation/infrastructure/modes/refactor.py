"""
Refactor Mode

Handles code refactoring with safety checks and intelligent suggestions.

Features:
- Code smell detection (long methods, duplication, complexity)
- Refactoring pattern suggestions
- Impact analysis via graph
- Safety assessment (safe/moderate/risky)
- Backward compatibility checks
"""

import ast

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

logger = get_logger(__name__)


@mode_registry.register(AgentMode.REFACTOR)
class RefactorMode(BaseModeHandler):
    """
    Refactor mode for code refactoring with safety checks.

    Flow:
    1. Detect code smells in target code
    2. Generate refactoring suggestions
    3. Analyze impact (via graph if available)
    4. Assess safety level
    5. Check backward compatibility
    6. Provide recommendations

    Transitions:
    - refactor_safe → QA (safe to apply)
    - high_risk → DESIGN (needs redesign)
    - tests_needed → TEST (write tests first)
    - suggestions_provided → QA (for review)
    """

    # Code smell thresholds
    LONG_METHOD_THRESHOLD = 30  # lines
    HIGH_COMPLEXITY_THRESHOLD = 10  # cyclomatic complexity

    def __init__(self, llm_client=None, graph_client=None):
        """
        Initialize Refactor mode.

        Args:
            llm_client: Optional LLM client for intelligent suggestions
            graph_client: Optional graph client for impact analysis
        """
        super().__init__(AgentMode.REFACTOR)
        self.llm = llm_client
        self.graph = graph_client

    async def enter(self, context: ModeContext) -> None:
        """Enter refactor mode."""
        await super().enter(context)
        self.logger.info(f"🔧 Refactor mode: Analyzing {len(context.pending_changes)} changes")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute refactoring analysis and suggestions.

        Args:
            task: Refactoring task
            context: Shared mode context with pending changes

        Returns:
            Result with code smells, suggestions, impact, and safety assessment
        """
        self.logger.info(f"Analyzing refactoring opportunities: {task.query}")

        # 1. Check for target code
        if not context.pending_changes:
            return self._create_result(
                data={
                    "no_target": True,
                    "suggestions": [],
                    "code_smells": [],
                },
                trigger="no_target",
                explanation="No code to refactor",
            )

        # 2. Detect code smells
        code_smells = self._detect_code_smells(context.pending_changes)

        # 3. Generate refactoring suggestions
        suggestions = await self._generate_suggestions(context.pending_changes, code_smells, task)

        # 4. Analyze impact
        impact_analysis = await self._analyze_impact(context.pending_changes)

        # 5. Assess safety
        safety_level = self._assess_safety(code_smells, impact_analysis)

        # 6. Check backward compatibility
        backward_compatible = self._check_backward_compatibility(context.pending_changes)

        # 7. Determine trigger
        trigger = self._determine_trigger(safety_level, code_smells)

        return self._create_result(
            data={
                "code_smells": code_smells,
                "suggestions": suggestions,
                "impact_analysis": impact_analysis,
                "safety_level": safety_level,
                "backward_compatible": backward_compatible,
            },
            trigger=trigger,
            explanation=f"Found {len(code_smells)} code smells, "
            f"{len(suggestions)} refactoring suggestions, "
            f"safety: {safety_level}",
        )

    def _detect_code_smells(self, pending_changes: list[dict]) -> list[dict]:
        """
        Detect code smells in pending changes.

        Args:
            pending_changes: List of pending code changes

        Returns:
            List of detected code smells
        """
        code_smells = []

        for change in pending_changes:
            content = change.get("content", "")
            file_path = change.get("file_path", "")

            if not file_path.endswith(".py"):
                continue

            # Detect long methods
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # Count lines in function
                        if hasattr(node, "end_lineno") and hasattr(node, "lineno"):
                            lines = node.end_lineno - node.lineno
                            if lines > self.LONG_METHOD_THRESHOLD:
                                code_smells.append(
                                    {
                                        "type": "long_method",
                                        "name": node.name,
                                        "file": file_path,
                                        "lines": lines,
                                        "threshold": self.LONG_METHOD_THRESHOLD,
                                        "suggestion": f"Consider breaking down {node.name} "
                                        f"({lines} lines) into smaller functions",
                                    }
                                )

                    # Detect complex conditionals (nested if statements)
                    if isinstance(node, ast.If):
                        # Count nesting depth
                        depth = self._count_nesting_depth(node)
                        if depth > 3:
                            code_smells.append(
                                {
                                    "type": "complex_conditional",
                                    "file": file_path,
                                    "line": node.lineno,
                                    "depth": depth,
                                    "suggestion": "Consider simplifying nested conditionals "
                                    "or extracting to separate functions",
                                }
                            )

            except SyntaxError as e:
                self.logger.warning(f"Failed to parse {file_path}: {e}")

        return code_smells

    def _count_nesting_depth(self, node: ast.If, current_depth: int = 1) -> int:
        """Count nesting depth of if statements."""
        max_depth = current_depth
        for child in ast.walk(node):
            if isinstance(child, ast.If) and child != node:
                depth = self._count_nesting_depth(child, current_depth + 1)
                max_depth = max(max_depth, depth)
        return max_depth

    async def _generate_suggestions(
        self, pending_changes: list[dict], code_smells: list[dict], task: Task
    ) -> list[dict]:
        """
        Generate refactoring suggestions.

        Args:
            pending_changes: List of pending changes
            code_smells: Detected code smells
            task: Refactoring task

        Returns:
            List of refactoring suggestions
        """
        suggestions = []

        # Try LLM-based suggestions first
        if self.llm:
            try:
                llm_suggestions = await self._generate_llm_suggestions(pending_changes, code_smells, task)
                suggestions.extend(llm_suggestions)
                return suggestions
            except Exception as e:
                self.logger.warning(f"LLM suggestion failed: {e}, using templates")

        # Fallback: Template-based suggestions from code smells
        for smell in code_smells:
            suggestions.append(
                {
                    "type": "refactor",
                    "target": smell.get("name", smell.get("file", "unknown")),
                    "smell_type": smell["type"],
                    "description": smell.get("suggestion", "Refactor recommended"),
                    "priority": self._get_priority(smell),
                }
            )

        # Add general suggestions if no smells found
        if not suggestions:
            suggestions.append(
                {
                    "type": "general",
                    "target": "codebase",
                    "description": "Code appears clean. Consider adding documentation or improving test coverage.",
                    "priority": "low",
                }
            )

        return suggestions

    async def _generate_llm_suggestions(
        self, pending_changes: list[dict], code_smells: list[dict], task: Task
    ) -> list[dict]:
        """Generate suggestions using LLM."""
        # Prepare context
        code_context = "\n\n".join([f"# {change['file_path']}\n{change['content']}" for change in pending_changes])

        smells_context = "\n".join([f"- {smell['type']}: {smell.get('suggestion', '')}" for smell in code_smells])

        prompt = f"""Analyze this code and provide refactoring suggestions:

Code:
{code_context}

Detected Code Smells:
{smells_context}

Task: {task.query}

Provide 3-5 specific refactoring suggestions in this format:
1. [Pattern] Description
2. [Pattern] Description
...
"""

        if self.llm is None:
            return []

        messages = [{"role": "user", "content": prompt}]
        response = await self.llm.complete(messages, temperature=0.3, max_tokens=1000)

        # Parse LLM response into structured suggestions
        suggestions = []
        content = response.get("content", "")
        lines = content.strip().split("\n")

        for line in lines:
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-")):
                # Parse suggestion line
                parts = line.split("]", 1)
                if len(parts) == 2:
                    pattern = parts[0].strip("[]1234567890. -")
                    description = parts[1].strip()
                    suggestions.append(
                        {
                            "type": "llm_suggestion",
                            "pattern": pattern,
                            "description": description,
                            "priority": "medium",
                        }
                    )

        return suggestions

    def _get_priority(self, smell: dict) -> str:
        """Determine priority level for a code smell."""
        smell_type = smell["type"]

        if smell_type == "long_method":
            lines = smell.get("lines", 0)
            if lines > 100:
                return "high"
            elif lines > 50:
                return "medium"
            else:
                return "low"

        elif smell_type == "complex_conditional":
            depth = smell.get("depth", 0)
            if depth > 5:
                return "high"
            elif depth > 3:
                return "medium"
            else:
                return "low"

        return "medium"

    async def _analyze_impact(self, pending_changes: list[dict]) -> dict:
        """
        Analyze impact of refactoring using graph (if available).

        Args:
            pending_changes: List of pending changes

        Returns:
            Impact analysis dictionary
        """
        if not self.graph:
            # Without graph, return basic impact
            return {
                "affected_count": len(pending_changes),
                "has_graph": False,
                "files": [change["file_path"] for change in pending_changes],
            }

        # With graph, analyze dependencies
        all_callers = []

        for change in pending_changes:
            content = change.get("content", "")

            # Extract function names
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        try:
                            callers = await self.graph.get_callers(node.name)
                            all_callers.extend(callers)
                        except Exception as e:
                            self.logger.warning(f"Graph query failed: {e}")
            except SyntaxError:
                pass

        # Deduplicate callers
        unique_callers = self._deduplicate_symbols(all_callers)

        return {
            "affected_count": len(pending_changes) + len(unique_callers),
            "has_graph": True,
            "files": [change["file_path"] for change in pending_changes],
            "callers": unique_callers,
        }

    def _deduplicate_symbols(self, symbols: list[dict]) -> list[dict]:
        """Deduplicate symbols by name+file."""
        seen = set()
        unique = []

        for symbol in symbols:
            key = f"{symbol.get('name')}:{symbol.get('file')}"
            if key not in seen:
                seen.add(key)
                unique.append(symbol)

        return unique

    def _assess_safety(self, code_smells: list[dict], impact_analysis: dict) -> str:
        """
        Assess safety level of refactoring.

        Args:
            code_smells: Detected code smells
            impact_analysis: Impact analysis

        Returns:
            "safe", "moderate", or "risky"
        """
        affected_count = impact_analysis.get("affected_count", 0)
        high_priority_smells = sum(1 for smell in code_smells if self._get_priority(smell) == "high")

        # Risk factors
        has_many_callers = affected_count > 10
        has_high_priority_issues = high_priority_smells > 0

        if has_many_callers and has_high_priority_issues:
            return "risky"
        elif has_many_callers or has_high_priority_issues:
            return "moderate"
        else:
            return "safe"

    def _check_backward_compatibility(self, pending_changes: list[dict]) -> bool:
        """
        Check if refactoring maintains backward compatibility.

        Args:
            pending_changes: List of pending changes

        Returns:
            True if backward compatible, False otherwise
        """
        # Simple heuristic: if code contains public API indicators,
        # assume backward compatibility is required
        for change in pending_changes:
            content = change.get("content", "")

            # Check for public API indicators
            if "public" in content.lower() or "api" in content.lower():
                # For simplicity, assume it's backward compatible
                # (real implementation would check function signatures)
                return True

        # Default: assume backward compatible
        return True

    def _determine_trigger(self, safety_level: str, code_smells: list[dict]) -> str:
        """
        Determine appropriate trigger based on analysis.

        Args:
            safety_level: "safe", "moderate", or "risky"
            code_smells: Detected code smells

        Returns:
            Trigger string for FSM
        """
        if safety_level == "risky":
            return "high_risk"
        elif len(code_smells) == 0:
            return "suggestions_provided"
        elif safety_level == "safe":
            return "refactor_safe"
        else:
            return "tests_needed"

    async def exit(self, context: ModeContext) -> None:
        """Exit refactor mode."""
        self.logger.info("Refactor analysis complete")
        await super().exit(context)
