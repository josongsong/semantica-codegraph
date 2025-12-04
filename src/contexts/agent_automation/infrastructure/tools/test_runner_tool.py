"""
Test Runner Tool

Executes tests and reports results for the agent.

Features:
- Run pytest tests with various options
- Parse test results into structured format
- Support for test discovery
- Timeout handling for long-running tests
- Coverage report integration
"""

import asyncio
import re
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from src.common.observability import get_logger
from src.contexts.agent_automation.infrastructure.tools.base import BaseTool

logger = get_logger(__name__)
# ============================================================
# Input/Output Schemas
# ============================================================


class RunTestsInput(BaseModel):
    """Input for running tests."""

    scope: str | None = Field(None, description="Test scope (file path, directory, or test name pattern)")
    marker: str | None = Field(None, description="Pytest marker to filter tests (e.g., 'unit', 'integration')")
    keyword: str | None = Field(None, description="Keyword expression to filter tests")
    verbose: bool = Field(False, description="Verbose output")
    coverage: bool = Field(False, description="Run with coverage report")
    fail_fast: bool = Field(False, description="Stop on first failure")
    timeout: int = Field(300, description="Timeout in seconds", ge=1, le=3600)


class TestCaseResult(BaseModel):
    """Result of a single test case."""

    name: str = Field(..., description="Test name (fully qualified)")
    file_path: str = Field(..., description="Test file path")
    status: Literal["passed", "failed", "skipped", "error", "xfailed", "xpassed"] = Field(
        ..., description="Test status"
    )
    duration: float = Field(0.0, description="Test duration in seconds")
    message: str | None = Field(None, description="Error message or skip reason")
    traceback: str | None = Field(None, description="Full traceback if failed")
    line_number: int | None = Field(None, description="Line number of test function")


class CoverageInfo(BaseModel):
    """Coverage information."""

    total_statements: int = Field(0, description="Total statements")
    covered_statements: int = Field(0, description="Covered statements")
    coverage_percent: float = Field(0.0, description="Coverage percentage")
    missing_lines: dict[str, list[int]] = Field(default_factory=dict, description="Missing lines by file")


class RunTestsOutput(BaseModel):
    """Output from running tests."""

    success: bool = Field(..., description="Whether test run completed successfully")
    passed: int = Field(0, description="Number of passed tests")
    failed: int = Field(0, description="Number of failed tests")
    skipped: int = Field(0, description="Number of skipped tests")
    errors: int = Field(0, description="Number of tests with errors")
    xfailed: int = Field(0, description="Number of expected failures")
    xpassed: int = Field(0, description="Number of unexpected passes")
    total: int = Field(0, description="Total number of tests")
    duration: float = Field(0.0, description="Total duration in seconds")
    tests: list[TestCaseResult] = Field(default_factory=list, description="Individual test results")
    coverage: CoverageInfo | None = Field(None, description="Coverage info if requested")
    output: str = Field("", description="Raw pytest output")
    error: str | None = Field(None, description="Error message if run failed")


class DiscoverTestsInput(BaseModel):
    """Input for test discovery."""

    directory: str = Field("tests", description="Directory to search for tests")
    pattern: str = Field("test_*.py", description="File pattern for test files")


class TestFileInfo(BaseModel):
    """Information about a test file."""

    path: str = Field(..., description="Test file path")
    test_count: int = Field(0, description="Number of tests in file")
    test_names: list[str] = Field(default_factory=list, description="List of test names")


class DiscoverTestsOutput(BaseModel):
    """Output from test discovery."""

    success: bool = Field(..., description="Whether discovery succeeded")
    total_files: int = Field(0, description="Total number of test files")
    total_tests: int = Field(0, description="Total number of tests")
    files: list[TestFileInfo] = Field(default_factory=list, description="Test files found")
    error: str | None = Field(None, description="Error message if failed")


# ============================================================
# Test Runner Tool Implementation
# ============================================================


class TestRunnerTool(BaseTool[RunTestsInput, RunTestsOutput]):
    """
    Test runner tool for executing pytest tests.

    Features:
    - Run tests with various filters (scope, markers, keywords)
    - Parse structured results from pytest output
    - Support coverage reporting
    - Handle timeouts gracefully
    - Test discovery

    Usage:
        tool = TestRunnerTool(project_root="/path/to/project")

        # Run all tests
        result = await tool.execute(RunTestsInput())

        # Run specific test file
        result = await tool.execute(RunTestsInput(scope="tests/test_foo.py"))

        # Run with coverage
        result = await tool.execute(RunTestsInput(coverage=True))
    """

    name = "test_runner"
    description = (
        "Run tests using pytest. Supports filtering by scope, markers, and keywords. "
        "Returns structured results with pass/fail counts and individual test outcomes."
    )
    input_schema = RunTestsInput
    output_schema = RunTestsOutput

    def __init__(
        self,
        project_root: str | None = None,
        python_path: str = "python",
        default_timeout: int = 300,
    ):
        """
        Initialize test runner.

        Args:
            project_root: Root directory of the project
            python_path: Path to Python interpreter
            default_timeout: Default timeout in seconds
        """
        super().__init__()
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.python_path = python_path
        self.default_timeout = default_timeout

    async def _execute(self, input_data: RunTestsInput) -> RunTestsOutput:
        """Execute test run."""
        return await self.run_tests(
            scope=input_data.scope,
            marker=input_data.marker,
            keyword=input_data.keyword,
            verbose=input_data.verbose,
            coverage=input_data.coverage,
            fail_fast=input_data.fail_fast,
            timeout=input_data.timeout,
        )

    async def run_tests(
        self,
        scope: str | None = None,
        marker: str | None = None,
        keyword: str | None = None,
        verbose: bool = False,
        coverage: bool = False,
        fail_fast: bool = False,
        timeout: int | None = None,
    ) -> RunTestsOutput:
        """
        Run pytest tests.

        Args:
            scope: Test scope (file, directory, or pattern)
            marker: Pytest marker filter
            keyword: Keyword expression filter
            verbose: Verbose output
            coverage: Run with coverage
            fail_fast: Stop on first failure
            timeout: Timeout in seconds

        Returns:
            RunTestsOutput with test results
        """
        timeout = timeout or self.default_timeout

        # Build pytest command
        cmd = [self.python_path, "-m", "pytest"]

        # Add JSON output for parsing
        cmd.extend(["--tb=short", "-q"])

        if verbose:
            cmd.append("-v")

        if fail_fast:
            cmd.append("-x")

        if marker:
            cmd.extend(["-m", marker])

        if keyword:
            cmd.extend(["-k", keyword])

        if coverage:
            cmd.extend(["--cov", "--cov-report=term-missing"])

        if scope:
            cmd.append(scope)

        logger.info(f"Running: {' '.join(cmd)}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(self.project_root),
            )

            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
            output = stdout.decode("utf-8")

            # Parse results
            return self._parse_pytest_output(output, coverage)

        except asyncio.TimeoutError:
            return RunTestsOutput(
                success=False,
                error=f"Test run timed out after {timeout}s",
                output="",
            )
        except Exception as e:
            return RunTestsOutput(success=False, error=str(e), output="")

    def _parse_pytest_output(self, output: str, has_coverage: bool = False) -> RunTestsOutput:
        """
        Parse pytest output into structured result.

        Args:
            output: Raw pytest output
            has_coverage: Whether coverage was enabled

        Returns:
            RunTestsOutput with parsed results
        """
        tests: list[TestCaseResult] = []
        passed = failed = skipped = errors = xfailed = xpassed = 0
        duration = 0.0
        coverage_info = None

        # Parse summary line (e.g., "5 passed, 2 failed, 1 skipped in 1.23s")
        summary_match = re.search(
            r"(?:=+\s*)?"
            r"(?:(\d+)\s+passed)?"
            r"(?:,?\s*(\d+)\s+failed)?"
            r"(?:,?\s*(\d+)\s+skipped)?"
            r"(?:,?\s*(\d+)\s+error)?"
            r"(?:,?\s*(\d+)\s+xfailed)?"
            r"(?:,?\s*(\d+)\s+xpassed)?"
            r"(?:\s+in\s+([\d.]+)s)?",
            output,
        )

        if summary_match:
            passed = int(summary_match.group(1) or 0)
            failed = int(summary_match.group(2) or 0)
            skipped = int(summary_match.group(3) or 0)
            errors = int(summary_match.group(4) or 0)
            xfailed = int(summary_match.group(5) or 0)
            xpassed = int(summary_match.group(6) or 0)
            if summary_match.group(7):
                duration = float(summary_match.group(7))

        # Parse individual test results
        # Format: "test_file.py::test_name PASSED/FAILED/SKIPPED"
        test_pattern = re.compile(
            r"^([\w/\\.]+\.py)::(\w+(?:::\w+)*)\s+(PASSED|FAILED|SKIPPED|ERROR|XFAIL|XPASS)",
            re.MULTILINE,
        )

        for match in test_pattern.finditer(output):
            file_path = match.group(1)
            test_name = match.group(2)
            status_str = match.group(3).lower()

            # Map status
            status_map = {
                "passed": "passed",
                "failed": "failed",
                "skipped": "skipped",
                "error": "error",
                "xfail": "xfailed",
                "xpass": "xpassed",
            }
            status = status_map.get(status_str, "error")

            # Try to find error message for failed tests
            message = None
            traceback = None
            if status in ("failed", "error"):
                # Look for error message after the test
                error_pattern = re.compile(
                    rf"{re.escape(test_name)}.*?(?:AssertionError|Error|Exception):\s*(.+?)(?:\n|$)",
                    re.DOTALL,
                )
                error_match = error_pattern.search(output)
                if error_match:
                    message = error_match.group(1).strip()[:500]  # Limit length

            tests.append(
                TestCaseResult(
                    name=f"{file_path}::{test_name}",
                    file_path=file_path,
                    status=status,
                    message=message,
                    traceback=traceback,
                )
            )

        # Parse coverage if present
        if has_coverage:
            coverage_info = self._parse_coverage(output)

        total = passed + failed + skipped + errors + xfailed + xpassed
        success = failed == 0 and errors == 0

        return RunTestsOutput(
            success=success,
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            xfailed=xfailed,
            xpassed=xpassed,
            total=total,
            duration=duration,
            tests=tests,
            coverage=coverage_info,
            output=output,
        )

    def _parse_coverage(self, output: str) -> CoverageInfo | None:
        """
        Parse coverage information from pytest output.

        Args:
            output: Raw pytest output with coverage

        Returns:
            CoverageInfo or None
        """
        # Look for TOTAL line in coverage report
        # Format: "TOTAL    1234    567    54%"
        total_match = re.search(
            r"TOTAL\s+(\d+)\s+(\d+)\s+(\d+)%",
            output,
        )

        if not total_match:
            return None

        total_statements = int(total_match.group(1))
        missing = int(total_match.group(2))
        coverage_percent = float(total_match.group(3))
        covered_statements = total_statements - missing

        # Parse missing lines per file
        # Format: "src/foo.py    100    10    90%    5-10, 20"
        missing_lines: dict[str, list[int]] = {}
        file_pattern = re.compile(
            r"^([\w/\\.]+\.py)\s+\d+\s+\d+\s+\d+%\s+([\d,\s-]+)$",
            re.MULTILINE,
        )

        for match in file_pattern.finditer(output):
            file_path = match.group(1)
            lines_str = match.group(2).strip()
            if lines_str:
                lines = self._parse_line_ranges(lines_str)
                if lines:
                    missing_lines[file_path] = lines

        return CoverageInfo(
            total_statements=total_statements,
            covered_statements=covered_statements,
            coverage_percent=coverage_percent,
            missing_lines=missing_lines,
        )

    def _parse_line_ranges(self, lines_str: str) -> list[int]:
        """
        Parse line ranges like "5-10, 20, 30-35" into list of line numbers.

        Args:
            lines_str: String with line ranges

        Returns:
            List of individual line numbers
        """
        lines = []
        parts = lines_str.split(",")

        for part in parts:
            part = part.strip()
            if "-" in part:
                try:
                    start, end = part.split("-")
                    lines.extend(range(int(start), int(end) + 1))
                except ValueError:
                    pass
            else:
                try:
                    lines.append(int(part))
                except ValueError:
                    pass

        return lines

    async def discover_tests(
        self,
        directory: str = "tests",
        pattern: str = "test_*.py",
    ) -> DiscoverTestsOutput:
        """
        Discover tests in a directory.

        Args:
            directory: Directory to search
            pattern: File pattern for test files

        Returns:
            DiscoverTestsOutput with discovered tests
        """
        cmd = [
            self.python_path,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            directory,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.project_root),
            )

            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=60)
            output = stdout.decode("utf-8")

            # Parse collected tests
            files: dict[str, list[str]] = {}

            for line in output.strip().split("\n"):
                line = line.strip()
                if "::" in line:
                    parts = line.split("::")
                    if len(parts) >= 2:
                        file_path = parts[0]
                        test_name = "::".join(parts[1:])

                        if file_path not in files:
                            files[file_path] = []
                        files[file_path].append(test_name)

            file_infos = [
                TestFileInfo(
                    path=path,
                    test_count=len(tests),
                    test_names=tests,
                )
                for path, tests in files.items()
            ]

            total_tests = sum(f.test_count for f in file_infos)

            return DiscoverTestsOutput(
                success=True,
                total_files=len(files),
                total_tests=total_tests,
                files=file_infos,
            )

        except asyncio.TimeoutError:
            return DiscoverTestsOutput(success=False, error="Test discovery timed out")
        except Exception as e:
            return DiscoverTestsOutput(success=False, error=str(e))

    async def run_single_test(self, test_path: str, timeout: int = 60) -> TestCaseResult:
        """
        Run a single test and return its result.

        Args:
            test_path: Full test path (e.g., "tests/test_foo.py::test_bar")
            timeout: Timeout in seconds

        Returns:
            TestCaseResult for the single test
        """
        result = await self.run_tests(scope=test_path, timeout=timeout)

        if result.tests:
            return result.tests[0]

        # If no test result found, return error
        return TestCaseResult(
            name=test_path,
            file_path=test_path.split("::")[0],
            status="error",
            message=result.error or "Test not found",
        )
