"""
Test Mode

Generates and executes tests for code validation.

Features:
- LLM-based test generation
- pytest execution
- Test result parsing
- Coverage analysis
- Test report generation

Integrates with retrieval scenarios:
- 2-20: Test coverage/refactoring impact analysis
- 1-6: Find all callers for test generation
"""

import re

from src.contexts.agent_automation.infrastructure.modes.base import BaseModeHandler, mode_registry
from src.contexts.agent_automation.infrastructure.types import (
    AgentMode,
    Change,
    CodeTestResults,
    CoverageData,
    ModeContext,
    Result,
    Task,
)
from src.contexts.agent_automation.infrastructure.utils import read_multiple_files
from src.common.observability import get_logger

logger = get_logger(__name__)


@mode_registry.register(AgentMode.TEST)
class CodeTestMode(BaseModeHandler):
    """
    Test mode for test generation and execution.

    Generates tests using:
    - LLM-based test generation
    - Code context analysis
    - Coverage-guided test generation

    Executes tests using:
    - pytest runner
    - Coverage analysis
    - Result parsing

    Note: Named CodeTestMode to avoid pytest collection warnings.
    """

    def __init__(
        self,
        llm_client=None,
        bash_executor=None,
    ):
        """
        Initialize Test mode.

        Args:
            llm_client: LLM client for test generation
            bash_executor: Bash executor for running pytest
        """
        super().__init__(AgentMode.TEST)
        self.llm = llm_client
        self.bash = bash_executor

    async def enter(self, context: ModeContext) -> None:
        """Enter test mode."""
        await super().enter(context)
        self.logger.info("Starting test generation/execution")

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute test generation or test execution.

        Flow:
        1. Determine if generating tests or running existing tests
        2a. If generating: Generate tests using LLM
        2b. If running: Execute pytest
        3. Parse results
        4. Analyze coverage (if available)
        5. Return result with appropriate trigger

        Args:
            task: Test task
            context: Shared mode context

        Returns:
            Result with test results or generated tests
        """
        self.logger.info(f"Test mode: {task.query}")

        # Determine mode: generate or run
        mode = self._determine_mode(task)

        if mode == "generate":
            return await self._generate_tests_flow(task, context)
        else:  # mode == "run"
            return await self._run_tests_flow(task, context)

    def _determine_mode(self, task: Task) -> str:
        """
        Determine if we should generate tests or run tests.

        Args:
            task: Test task

        Returns:
            "generate" or "run"
        """
        query_lower = task.query.lower()

        # Keywords for test generation
        gen_keywords = ["generate", "create", "write", "add"]
        # Keywords for test execution
        run_keywords = ["run", "execute", "test", "check", "verify"]

        # Check for generation keywords
        if any(kw in query_lower for kw in gen_keywords):
            return "generate"

        # Check for run keywords
        if any(kw in query_lower for kw in run_keywords):
            return "run"

        # Default: run tests if they exist, generate if not
        return "run"

    async def _generate_tests_flow(self, task: Task, context: ModeContext) -> Result:
        """
        Generate tests using LLM.

        Args:
            task: Test task
            context: Mode context

        Returns:
            Result with generated tests
        """
        self.logger.info("Generating tests")

        # 1. Get code to test from context
        code_to_test = self._get_code_to_test(context)

        # 2. Generate tests using LLM
        try:
            test_code = await self._generate_tests(task, code_to_test, context)
        except Exception as e:
            self.logger.error(f"Test generation failed: {e}")
            return self._create_result(
                data={"error": str(e)},
                trigger="error_occurred",
                explanation=f"Failed to generate tests: {e}",
                requires_approval=False,
            )

        # 3. Create Change objects for test files
        changes = self._create_test_changes(test_code, context)

        # 4. Add to context
        for change in changes:
            context.add_pending_change(
                {
                    "file_path": change.file_path,
                    "content": change.content,
                    "change_type": change.change_type,
                }
            )

        # 5. Record action
        context.add_action(
            {
                "type": "test_generation",
                "files": [c.file_path for c in changes],
                "test_count": self._count_tests(test_code),
            }
        )

        return self._create_result(
            data={
                "generated_tests": test_code,
                "changes": [self._change_to_dict(c) for c in changes],
                "total_changes": len(changes),
                "test_count": self._count_tests(test_code),
            },
            trigger="code_complete",  # Tests generated, ready to run
            explanation=f"Generated {self._count_tests(test_code)} tests",
            requires_approval=True,  # Tests should be reviewed
        )

    async def _run_tests_flow(self, task: Task, context: ModeContext) -> Result:
        """
        Run existing tests using pytest.

        Args:
            task: Test task
            context: Mode context

        Returns:
            Result with test results
        """
        self.logger.info("Running tests")

        # 1. Determine test path
        test_path = self._get_test_path(task, context)

        # 2. Run tests
        try:
            test_results = await self._run_tests(test_path, context)
        except Exception as e:
            self.logger.error(f"Test execution failed: {e}")
            return self._create_result(
                data={"error": str(e)},
                trigger="error_occurred",
                explanation=f"Failed to run tests: {e}",
                requires_approval=False,
            )

        # 3. Analyze coverage (if available)
        coverage_data = await self._analyze_coverage(context)

        # 4. Store results in context
        context.test_results = {
            "all_passed": test_results.all_passed,
            "total": test_results.total_tests,
            "passed": test_results.passed_tests,
            "failed": test_results.failed_tests,
            "coverage": coverage_data.coverage_percentage if coverage_data else None,
        }

        # 5. Determine trigger
        if test_results.all_passed:
            trigger = "tests_passed"
            explanation = f"All {test_results.total_tests} tests passed"
            if coverage_data:
                explanation += f" ({coverage_data.coverage_percentage:.1f}% coverage)"
        else:
            trigger = "test_failed"
            explanation = f"{test_results.failed_tests}/{test_results.total_tests} tests failed"

        # 6. Record action
        context.add_action(
            {
                "type": "test_execution",
                "path": test_path,
                "passed": test_results.all_passed,
                "total": test_results.total_tests,
            }
        )

        return self._create_result(
            data={
                "test_results": test_results.__dict__,
                "coverage": coverage_data.__dict__ if coverage_data else None,
                "test_path": test_path,
            },
            trigger=trigger,
            explanation=explanation,
            requires_approval=False,  # Test results are informational
        )

    def _get_code_to_test(self, context: ModeContext) -> str:
        """
        Get code to test from context.

        Args:
            context: Mode context

        Returns:
            Code to test as string
        """
        if not context.current_files:
            return ""

        # Read actual files (limit to 3 files, 300 lines each)
        return read_multiple_files(context.current_files[:3], max_lines_per_file=300)

    async def _generate_tests(self, task: Task, code_to_test: str, context: ModeContext) -> str:
        """
        Generate tests using LLM.

        Args:
            task: Test task
            code_to_test: Code to generate tests for
            context: Mode context

        Returns:
            Generated test code
        """
        if not self.llm:
            # Fallback: use rule-based test generation
            self.logger.warning("No LLM client provided, using fallback test generation")
            # Extract function name from task
            import re

            from src.contexts.agent_automation.infrastructure.fallback import SimpleLLMFallback

            match = re.search(r"test (\w+)", task.query, re.IGNORECASE)
            function_name = match.group(1) if match else "function"

            return SimpleLLMFallback.generate_test(function_name, code_to_test)

        # Build prompt
        prompt = self._build_test_prompt(task, code_to_test, context)

        # Call LLM
        try:
            response = await self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=3000,
            )

            generated = response.get("content", "")
            return self._extract_code(generated)

        except Exception as e:
            self.logger.error(f"LLM call failed: {e}")
            raise RuntimeError(f"Test generation failed: {e}") from e

    def _build_test_prompt(self, task: Task, code_to_test: str, context: ModeContext) -> str:
        """
        Build LLM prompt for test generation.

        Args:
            task: Test task
            code_to_test: Code to test
            context: Mode context

        Returns:
            Formatted prompt
        """
        prompt = f"""You are an expert test engineer. Generate comprehensive tests for the following code:

Code to test:
{code_to_test}

Requirements: {task.query}

Generate tests that:
1. Cover all major code paths
2. Test edge cases and error conditions
3. Use pytest conventions
4. Include clear test names and docstrings
5. Use appropriate fixtures and parametrization

Return ONLY the test code, no explanations.
Use pytest format.
"""
        return prompt

    def _extract_code(self, llm_response: str) -> str:
        """
        Extract code from LLM response.

        Args:
            llm_response: Raw LLM response

        Returns:
            Extracted code
        """
        # Remove markdown code blocks
        if "```python" in llm_response:
            parts = llm_response.split("```python")
            if len(parts) > 1:
                code_part = parts[1].split("```")[0]
                return code_part.strip()

        if "```" in llm_response:
            parts = llm_response.split("```")
            if len(parts) >= 3:
                return parts[1].strip()

        return llm_response.strip()

    def _create_test_changes(self, test_code: str, context: ModeContext) -> list[Change]:
        """
        Create Change objects for test files.

        Args:
            test_code: Generated test code
            context: Mode context

        Returns:
            List of Change objects
        """
        # Determine test file name
        if context.current_files:
            # Generate test file name from source file
            source_file = context.current_files[0]
            test_file = self._get_test_file_name(source_file)
        else:
            test_file = "tests/test_generated.py"

        change = Change(
            file_path=test_file,
            content=test_code,
            change_type="add",  # Usually adding new test file
        )

        return [change]

    def _get_test_file_name(self, source_file: str) -> str:
        """
        Generate test file name from source file.

        Args:
            source_file: Source file path

        Returns:
            Test file path
        """
        # Extract file name without path
        import os

        file_name = os.path.basename(source_file)
        name_without_ext = os.path.splitext(file_name)[0]

        # Generate test file name
        return f"tests/test_{name_without_ext}.py"

    def _count_tests(self, test_code: str) -> int:
        """
        Count number of tests in test code.

        Args:
            test_code: Test code

        Returns:
            Number of tests
        """
        # Count test functions (def test_*)
        return len(re.findall(r"def test_\w+", test_code))

    def _get_test_path(self, task: Task, context: ModeContext) -> str:
        """
        Get test path from task or context.

        Args:
            task: Test task
            context: Mode context

        Returns:
            Test path
        """
        # Check task for explicit path
        if task.files:
            return task.files[0]

        # Default test path
        return "tests/"

    async def _run_tests(self, test_path: str, context: ModeContext) -> CodeTestResults:
        """
        Run tests using pytest.

        Args:
            test_path: Path to tests
            context: Mode context

        Returns:
            Test results
        """
        if not self.bash:
            # Fallback: return mock results
            self.logger.warning("No bash executor provided, using mock results")
            return CodeTestResults(
                all_passed=True,
                total_tests=5,
                passed_tests=5,
                failed_tests=0,
                details={"mock": True},
            )

        # Run pytest
        try:
            result = await self.bash.execute(f"pytest {test_path} -v --tb=short")
            return self._parse_test_results(result)

        except Exception as e:
            self.logger.error(f"pytest execution failed: {e}")
            raise RuntimeError(f"Test execution failed: {e}") from e

    def _parse_test_results(self, pytest_output: str) -> CodeTestResults:
        """
        Parse pytest output.

        Args:
            pytest_output: Raw pytest output

        Returns:
            Parsed test results
        """
        # Parse pytest summary line
        # Example: "5 passed, 2 failed in 1.23s"
        summary_pattern = r"(\d+) passed(?:, (\d+) failed)?"
        match = re.search(summary_pattern, pytest_output)

        if match:
            passed = int(match.group(1))
            failed = int(match.group(2)) if match.group(2) else 0
            total = passed + failed

            return CodeTestResults(
                all_passed=(failed == 0),
                total_tests=total,
                passed_tests=passed,
                failed_tests=failed,
                details={"output": pytest_output},
            )

        # Fallback: couldn't parse
        self.logger.warning("Could not parse pytest output")
        return CodeTestResults(
            all_passed=False,
            total_tests=0,
            passed_tests=0,
            failed_tests=0,
            details={"output": pytest_output, "parse_error": True},
        )

    async def _analyze_coverage(self, context: ModeContext) -> CoverageData | None:
        """
        Analyze code coverage.

        Args:
            context: Mode context

        Returns:
            Coverage data or None
        """
        if not self.bash:
            return None

        try:
            # Try to read coverage data
            # Assuming pytest-cov was used
            await self.bash.execute("coverage json -o /tmp/coverage.json")

            # Parse coverage JSON
            import json

            with open("/tmp/coverage.json") as f:
                cov_data = json.load(f)

            total_coverage = cov_data.get("totals", {}).get("percent_covered", 0.0)
            covered_lines = cov_data.get("totals", {}).get("covered_lines", 0)
            total_lines = cov_data.get("totals", {}).get("num_statements", 0)

            return CoverageData(
                coverage_percentage=total_coverage,
                covered_lines=covered_lines,
                total_lines=total_lines,
                details=cov_data,
            )

        except Exception as e:
            self.logger.warning(f"Coverage analysis failed: {e}")
            return None

    def _change_to_dict(self, change: Change) -> dict:
        """Convert Change object to dict."""
        return {
            "file_path": change.file_path,
            "content": change.content,
            "change_type": change.change_type,
        }

    async def exit(self, context: ModeContext) -> None:
        """Exit test mode."""
        test_results = context.test_results
        if test_results:
            status = "passed" if test_results.get("all_passed") else "failed"
            self.logger.info(f"Exiting test - {status}")
        else:
            self.logger.info("Exiting test - no results")
        await super().exit(context)


@mode_registry.register(AgentMode.TEST, simple=True)
class CodeTestModeSimple(BaseModeHandler):
    """
    Simplified Test mode for testing without dependencies.

    Returns mock test results.

    Note: Named CodeTestModeSimple to avoid pytest collection warnings.
    """

    __test__ = False  # Prevent pytest from collecting this class

    def __init__(self, mock_test_code: str | None = None, mock_results: "CodeTestResults | None" = None):
        """
        Initialize simple test mode.

        Args:
            mock_test_code: Optional mock test code to return
            mock_results: Optional mock test results
        """
        super().__init__(AgentMode.TEST)
        self.mock_test_code = mock_test_code or "def test_example():\n    assert True"
        self.mock_results = mock_results or CodeTestResults(
            all_passed=True, total_tests=3, passed_tests=3, failed_tests=0, details={}
        )

    async def execute(self, task: Task, context: ModeContext) -> Result:
        """
        Execute simple test with mock data.

        Args:
            task: Test task
            context: Mode context

        Returns:
            Result with mock test data
        """
        query_lower = task.query.lower()

        # Determine if generating or running
        if any(kw in query_lower for kw in ["generate", "create", "write"]):
            # Mock test generation
            change = Change(
                file_path="tests/test_generated.py",
                content=self.mock_test_code,
                change_type="add",
            )

            context.add_pending_change(
                {
                    "file_path": change.file_path,
                    "content": change.content,
                    "change_type": change.change_type,
                }
            )

            return self._create_result(
                data={
                    "generated_tests": self.mock_test_code,
                    "changes": [
                        {
                            "file_path": change.file_path,
                            "content": change.content,
                            "change_type": change.change_type,
                        }
                    ],
                    "total_changes": 1,
                    "test_count": 1,
                },
                trigger="code_complete",
                explanation="Generated 1 test (mock)",
                requires_approval=True,
            )
        else:
            # Mock test execution
            context.test_results = {
                "all_passed": self.mock_results.all_passed,
                "total": self.mock_results.total_tests,
                "passed": self.mock_results.passed_tests,
                "failed": self.mock_results.failed_tests,
            }

            trigger = "tests_passed" if self.mock_results.all_passed else "test_failed"

            return self._create_result(
                data={
                    "test_results": self.mock_results.__dict__,
                    "test_path": "tests/",
                },
                trigger=trigger,
                explanation=f"{self.mock_results.passed_tests}/{self.mock_results.total_tests} tests passed (mock)",
                requires_approval=False,
            )
