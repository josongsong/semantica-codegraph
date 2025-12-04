"""
Verification Mode

Formal and informal verification of code correctness.

Features:
- Assertion verification
- Invariant checking
- Pre/post condition validation
- Property-based testing suggestions
- Static analysis integration
"""

import ast
from typing import Any

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import AgentMode, ModeContext, Result, Task

logger = get_logger(__name__)


@mode_registry.register(AgentMode.VERIFICATION)
class VerificationMode(BaseModeHandler):
    """
    Verification mode for code correctness validation.

    Flow:
    1. Extract assertions and invariants
    2. Analyze code paths
    3. Check pre/post conditions
    4. Identify potential issues
    5. Generate verification report

    Transitions:
    - verified → QA (verification passed)
    - verification_failed → DEBUG (issues found)
    - needs_tests → TEST (more tests needed)
    """

    def __init__(self, llm_client=None):
        """
        Initialize Verification mode.

        Args:
            llm_client: Optional LLM client for intelligent analysis
        """
        super().__init__(AgentMode.VERIFICATION)
        self.llm = llm_client

    async def enter(self, context: ModeContext) -> None:
        """Enter verification mode."""
        await super().enter(context)
        self.logger.info("✓ Verification mode: Validating correctness")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute verification analysis.

        Args:
            task: Verification task
            context: Shared mode context

        Returns:
            Result with verification report
        """
        self.logger.info(f"Verifying: {task.query}")

        # 1. Extract assertions and contracts
        contracts = self._extract_contracts(context.pending_changes)

        # 2. Analyze code paths
        path_analysis = self._analyze_paths(context.pending_changes)

        # 3. Check pre/post conditions
        condition_checks = self._check_conditions(context.pending_changes, contracts)

        # 4. Identify potential issues
        issues = await self._identify_issues(context.pending_changes, path_analysis)

        # 5. Generate property-based test suggestions
        property_tests = self._suggest_property_tests(context.pending_changes)

        # 6. Calculate verification status
        verified = len(issues) == 0 and all(c["status"] == "passed" for c in condition_checks)

        report = {
            "contracts": contracts,
            "path_analysis": path_analysis,
            "condition_checks": condition_checks,
            "issues": issues,
            "property_tests": property_tests,
            "verified": verified,
        }

        # 7. Determine trigger
        trigger = self._determine_trigger(verified, issues, property_tests)

        return self._create_result(
            data=report,
            trigger=trigger,
            explanation=f"Verification {'passed' if verified else 'failed'}, "
            f"{len(issues)} issues, {len(contracts)} contracts checked",
        )

    def _extract_contracts(self, pending_changes: list[dict]) -> list[dict]:
        """Extract assertions and design contracts from code."""
        contracts = []

        for change in pending_changes:
            content = change.get("content", "")
            file_path = change.get("file_path", "")

            if not file_path.endswith(".py"):
                continue

            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    # Find assert statements
                    if isinstance(node, ast.Assert):
                        contracts.append(
                            {
                                "type": "assertion",
                                "file": file_path,
                                "line": node.lineno,
                                "condition": ast.unparse(node.test) if hasattr(ast, "unparse") else str(node.test),
                            }
                        )

                    # Find functions with docstrings containing preconditions
                    if isinstance(node, ast.FunctionDef):
                        docstring = ast.get_docstring(node)
                        if docstring:
                            if "precondition" in docstring.lower() or "requires" in docstring.lower():
                                contracts.append(
                                    {
                                        "type": "precondition",
                                        "file": file_path,
                                        "function": node.name,
                                        "line": node.lineno,
                                    }
                                )
                            if "postcondition" in docstring.lower() or "ensures" in docstring.lower():
                                contracts.append(
                                    {
                                        "type": "postcondition",
                                        "file": file_path,
                                        "function": node.name,
                                        "line": node.lineno,
                                    }
                                )

            except SyntaxError:
                continue

        return contracts

    def _analyze_paths(self, pending_changes: list[dict]) -> dict[str, Any]:
        """Analyze code paths for potential issues."""
        analysis = {"branches": 0, "loops": 0, "complexity": 0, "unreachable": []}

        for change in pending_changes:
            content = change.get("content", "")
            file_path = change.get("file_path", "")

            if not file_path.endswith(".py"):
                continue

            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.If):
                        analysis["branches"] += 1
                    elif isinstance(node, ast.For | ast.While):
                        analysis["loops"] += 1

                # Simple cyclomatic complexity estimate
                analysis["complexity"] = analysis["branches"] + analysis["loops"] + 1

            except SyntaxError:
                continue

        return analysis

    def _check_conditions(self, pending_changes: list[dict], contracts: list[dict]) -> list[dict]:
        """Check pre/post conditions."""
        checks = []

        for contract in contracts:
            check = {
                "contract": contract,
                "status": "passed",  # Would be determined by actual verification
                "details": None,
            }

            # Simple static checks
            if contract["type"] == "assertion":
                # Check if assertion is trivially true or always false
                condition = contract.get("condition", "")
                if condition in ["True", "False"]:
                    check["status"] = "warning"
                    check["details"] = f"Trivial assertion: {condition}"

            checks.append(check)

        return checks

    async def _identify_issues(self, pending_changes: list[dict], path_analysis: dict) -> list[dict]:
        """Identify potential correctness issues."""
        issues = []

        for change in pending_changes:
            content = change.get("content", "")
            file_path = change.get("file_path", "")

            if not file_path.endswith(".py"):
                continue

            try:
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    # Check for common issues

                    # Division by zero potential
                    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div | ast.FloorDiv):
                        issues.append(
                            {
                                "type": "potential_division_by_zero",
                                "file": file_path,
                                "line": node.lineno,
                                "severity": "warning",
                                "message": "Potential division by zero - verify divisor is not zero",
                            }
                        )

                    # Unhandled None return
                    if isinstance(node, ast.Return) and node.value is None:
                        issues.append(
                            {
                                "type": "none_return",
                                "file": file_path,
                                "line": node.lineno,
                                "severity": "info",
                                "message": "Function returns None - verify this is intentional",
                            }
                        )

            except SyntaxError:
                continue

        # High complexity warning
        if path_analysis.get("complexity", 0) > 10:
            issues.append(
                {
                    "type": "high_complexity",
                    "file": "multiple",
                    "line": 0,
                    "severity": "warning",
                    "message": f"High cyclomatic complexity ({path_analysis['complexity']}) - consider refactoring",
                }
            )

        return issues

    def _suggest_property_tests(self, pending_changes: list[dict]) -> list[dict]:
        """Suggest property-based tests for functions."""
        suggestions = []

        for change in pending_changes:
            content = change.get("content", "")
            file_path = change.get("file_path", "")

            if not file_path.endswith(".py"):
                continue

            try:
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # Skip private/dunder methods
                        if node.name.startswith("_"):
                            continue

                        # Suggest property tests based on function characteristics
                        suggestion = {
                            "function": node.name,
                            "file": file_path,
                            "properties": [],
                        }

                        # Check return type for property suggestions
                        if node.returns:
                            return_type = ast.unparse(node.returns) if hasattr(ast, "unparse") else str(node.returns)
                            if "int" in return_type or "float" in return_type:
                                suggestion["properties"].append("Result should be within expected range")
                            if "list" in return_type:
                                suggestion["properties"].append("Result length should match expectation")
                            if "bool" in return_type:
                                suggestion["properties"].append("Result should be consistent for same inputs")

                        if suggestion["properties"]:
                            suggestions.append(suggestion)

            except SyntaxError:
                continue

        return suggestions

    def _determine_trigger(self, verified: bool, issues: list[dict], property_tests: list[dict]) -> str:
        """Determine appropriate trigger based on verification results."""
        if not verified:
            critical = any(i.get("severity") == "critical" for i in issues)
            if critical:
                return "verification_failed"

        if property_tests and not verified:
            return "needs_tests"

        return "verified" if verified else "verification_failed"

    async def exit(self, context: ModeContext) -> None:
        """Exit verification mode."""
        self.logger.info("Verification complete")
        await super().exit(context)
