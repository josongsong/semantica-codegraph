"""
Spec Compliance Mode

Validates code against specifications, standards, and coding guidelines.

Features:
- Code style compliance (PEP8, ESLint rules)
- API specification validation (OpenAPI, GraphQL schema)
- Type checking compliance
- Documentation standards
- Custom rule enforcement
"""

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

logger = get_logger(__name__)


@mode_registry.register(AgentMode.SPEC_COMPLIANCE)
class SpecComplianceMode(BaseModeHandler):
    """
    Spec Compliance mode for validating code against standards.

    Flow:
    1. Identify applicable specifications
    2. Run compliance checks
    3. Categorize violations
    4. Generate fix suggestions
    5. Create compliance report

    Transitions:
    - compliant → QA (all checks passed)
    - violations_found → IMPLEMENTATION (fixes needed)
    - critical_violation → DEBUG (critical issues)
    """

    def __init__(self, llm_client=None):
        """
        Initialize Spec Compliance mode.

        Args:
            llm_client: Optional LLM client for intelligent suggestions
        """
        super().__init__(AgentMode.SPEC_COMPLIANCE)
        self.llm = llm_client

    async def enter(self, context: ModeContext) -> None:
        """Enter spec compliance mode."""
        await super().enter(context)
        self.logger.info("📋 Spec Compliance mode: Checking standards")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute spec compliance checking.

        Args:
            task: Compliance check task
            context: Shared mode context

        Returns:
            Result with compliance report
        """
        self.logger.info(f"Checking compliance: {task.query}")

        # 1. Identify applicable specs
        specs = self._identify_specs(task, context)

        # 2. Run compliance checks
        violations = await self._run_checks(context.pending_changes, specs)

        # 3. Categorize violations
        categorized = self._categorize_violations(violations)

        # 4. Generate fix suggestions
        suggestions = await self._generate_suggestions(violations)

        # 5. Calculate compliance score
        score = self._calculate_score(violations, context.pending_changes)

        # 6. Create report
        report = {
            "specs_checked": specs,
            "violations": violations,
            "categorized": categorized,
            "suggestions": suggestions,
            "score": score,
            "passed": score >= 80,
        }

        # 7. Determine trigger
        trigger = self._determine_trigger(violations, score)

        return self._create_result(
            data=report,
            trigger=trigger,
            explanation=f"Compliance score: {score}/100, {len(violations)} violations found",
        )

    def _identify_specs(self, task: Task, context: ModeContext) -> list[dict]:
        """Identify applicable specifications."""
        specs = []
        query_lower = task.query.lower()

        # Check for specific spec mentions
        if "pep8" in query_lower or "pep 8" in query_lower or "style" in query_lower:
            specs.append({"name": "PEP8", "type": "style", "strictness": "standard"})

        if "type" in query_lower or "typing" in query_lower:
            specs.append({"name": "Type Hints", "type": "typing", "strictness": "standard"})

        if "openapi" in query_lower or "api" in query_lower:
            specs.append({"name": "OpenAPI", "type": "api", "strictness": "strict"})

        if "docstring" in query_lower or "documentation" in query_lower:
            specs.append({"name": "Docstrings", "type": "documentation", "strictness": "standard"})

        # Default specs if none specified
        if not specs:
            specs = [
                {"name": "PEP8", "type": "style", "strictness": "standard"},
                {"name": "Type Hints", "type": "typing", "strictness": "lenient"},
                {"name": "Docstrings", "type": "documentation", "strictness": "lenient"},
            ]

        return specs

    async def _run_checks(self, pending_changes: list[dict], specs: list[dict]) -> list[dict]:
        """Run compliance checks against specs."""
        violations = []

        for change in pending_changes:
            content = change.get("content", "")
            file_path = change.get("file_path", "")

            if not file_path.endswith(".py"):
                continue

            # Check each spec
            for spec in specs:
                spec_violations = self._check_spec(content, file_path, spec)
                violations.extend(spec_violations)

        return violations

    def _check_spec(self, content: str, file_path: str, spec: dict) -> list[dict]:
        """Check content against a specific spec."""
        violations = []
        spec_name = spec["name"]
        lines = content.split("\n")

        if spec_name == "PEP8":
            violations.extend(self._check_pep8(lines, file_path))
        elif spec_name == "Type Hints":
            violations.extend(self._check_type_hints(content, file_path))
        elif spec_name == "Docstrings":
            violations.extend(self._check_docstrings(content, file_path))

        return violations

    def _check_pep8(self, lines: list[str], file_path: str) -> list[dict]:
        """Check PEP8 style compliance."""
        violations = []

        for i, line in enumerate(lines, 1):
            # Line length check
            if len(line) > 120:
                violations.append(
                    {
                        "spec": "PEP8",
                        "rule": "E501",
                        "file": file_path,
                        "line": i,
                        "severity": "warning",
                        "message": f"Line too long ({len(line)} > 120 characters)",
                    }
                )

            # Trailing whitespace
            if line.rstrip() != line and line.strip():
                violations.append(
                    {
                        "spec": "PEP8",
                        "rule": "W291",
                        "file": file_path,
                        "line": i,
                        "severity": "warning",
                        "message": "Trailing whitespace",
                    }
                )

            # Mixed tabs and spaces
            if "\t" in line and "    " in line:
                violations.append(
                    {
                        "spec": "PEP8",
                        "rule": "E101",
                        "file": file_path,
                        "line": i,
                        "severity": "error",
                        "message": "Mixed tabs and spaces",
                    }
                )

        return violations

    def _check_type_hints(self, content: str, file_path: str) -> list[dict]:
        """Check type hint compliance."""
        violations = []

        # Simple check for functions without return type hints
        import re

        func_pattern = r"def (\w+)\([^)]*\):"
        matches = re.finditer(func_pattern, content)

        for match in matches:
            func_name = match.group(1)
            if func_name.startswith("_"):
                continue  # Skip private methods for lenient checking

            # Check if return type hint exists
            if "->" not in content[match.start() : match.end() + 50]:
                violations.append(
                    {
                        "spec": "Type Hints",
                        "rule": "TH001",
                        "file": file_path,
                        "line": content[: match.start()].count("\n") + 1,
                        "severity": "info",
                        "message": f"Function '{func_name}' missing return type hint",
                    }
                )

        return violations

    def _check_docstrings(self, content: str, file_path: str) -> list[dict]:
        """Check docstring compliance."""
        violations = []

        import re

        # Check for functions without docstrings
        func_pattern = r"def (\w+)\([^)]*\):[^\n]*\n(\s*)(\"\"\"|\'\'\')?"
        matches = re.finditer(func_pattern, content)

        for match in matches:
            func_name = match.group(1)
            has_docstring = match.group(3) is not None

            if not has_docstring and not func_name.startswith("_"):
                violations.append(
                    {
                        "spec": "Docstrings",
                        "rule": "D100",
                        "file": file_path,
                        "line": content[: match.start()].count("\n") + 1,
                        "severity": "info",
                        "message": f"Function '{func_name}' missing docstring",
                    }
                )

        return violations

    def _categorize_violations(self, violations: list[dict]) -> dict[str, list[dict]]:
        """Categorize violations by severity and spec."""
        categorized: dict[str, list[dict]] = {"critical": [], "error": [], "warning": [], "info": []}

        for v in violations:
            severity = v.get("severity", "info")
            if severity in categorized:
                categorized[severity].append(v)
            else:
                categorized["info"].append(v)

        return categorized

    async def _generate_suggestions(self, violations: list[dict]) -> list[dict]:
        """Generate fix suggestions for violations."""
        suggestions = []

        for v in violations:
            suggestion = {
                "violation": v,
                "fix": self._get_fix_for_violation(v),
                "auto_fixable": v.get("rule") in ["W291", "E101"],  # Some rules can be auto-fixed
            }
            suggestions.append(suggestion)

        return suggestions

    def _get_fix_for_violation(self, violation: dict) -> str:
        """Get fix suggestion for a specific violation."""
        rule = violation.get("rule", "")

        fixes = {
            "E501": "Break line into multiple lines or use line continuation",
            "W291": "Remove trailing whitespace",
            "E101": "Convert all indentation to spaces (4 spaces per level)",
            "TH001": "Add return type hint (e.g., -> None, -> str, -> int)",
            "D100": "Add docstring with description, args, and return value",
        }

        return fixes.get(rule, "Review and fix manually")

    def _calculate_score(self, violations: list[dict], pending_changes: list[dict]) -> int:
        """Calculate compliance score (0-100)."""
        if not pending_changes:
            return 100

        # Start with perfect score
        score = 100

        # Deduct points for violations
        for v in violations:
            severity = v.get("severity", "info")
            if severity == "critical":
                score -= 20
            elif severity == "error":
                score -= 10
            elif severity == "warning":
                score -= 5
            else:  # info
                score -= 1

        return max(0, score)

    def _determine_trigger(self, violations: list[dict], score: int) -> str:
        """Determine appropriate trigger based on results."""
        critical = any(v.get("severity") == "critical" for v in violations)

        if critical:
            return "critical_violation"
        elif score < 80:
            return "violations_found"
        else:
            return "compliant"

    async def exit(self, context: ModeContext) -> None:
        """Exit spec compliance mode."""
        self.logger.info("Spec compliance check complete")
        await super().exit(context)
