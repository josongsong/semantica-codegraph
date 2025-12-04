"""pytest-testmon integration for incremental testing."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.infra.observability import get_logger

logger = get_logger(__name__)


@dataclass
class TestResult:
    """Test execution result."""

    success: bool
    total_tests: int
    passed: int
    failed: int
    skipped: int
    duration_seconds: float
    changed_tests_only: bool = False
    output: str = ""
    error: str | None = None


class IncrementalTestRunner:
    """Incremental test runner using pytest-testmon.

    Runs only tests affected by changed files, dramatically
    reducing test execution time for large codebases.
    """

    def __init__(self, repo_path: Path):
        """Initialize testmon runner.

        Args:
            repo_path: Repository root path
        """
        self.repo_path = repo_path

    async def run_affected_tests(
        self,
        changed_files: list[str],
        test_dir: str = "tests",
    ) -> TestResult:
        """Run tests affected by changed files.

        Args:
            changed_files: List of changed file paths
            test_dir: Test directory (default: "tests")

        Returns:
            TestResult
        """
        logger.info(
            "running_affected_tests",
            changed_files_count=len(changed_files),
            test_dir=test_dir,
        )

        # Run pytest with testmon
        cmd = [
            "pytest",
            "--testmon",  # Enable testmon
            "-v",  # Verbose
            "--tb=short",  # Short traceback
            test_dir,
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            # Parse pytest output
            test_result = self._parse_pytest_output(result.stdout + result.stderr)
            test_result.changed_tests_only = True
            test_result.success = result.returncode == 0

            logger.info(
                "tests_completed",
                total=test_result.total_tests,
                passed=test_result.passed,
                failed=test_result.failed,
                skipped=test_result.skipped,
                changed_only=True,
            )

            return test_result

        except subprocess.TimeoutExpired:
            logger.error("test_run_timeout")
            return TestResult(
                success=False,
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                duration_seconds=300.0,
                error="Test execution timeout (5 minutes)",
            )

        except Exception as e:
            logger.error("test_run_failed", error=str(e))
            return TestResult(
                success=False,
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                duration_seconds=0.0,
                error=str(e),
            )

    async def run_all_tests(self, test_dir: str = "tests") -> TestResult:
        """Run all tests (fallback when testmon not available).

        Args:
            test_dir: Test directory

        Returns:
            TestResult
        """
        logger.info("running_all_tests", test_dir=test_dir)

        cmd = [
            "pytest",
            "-v",
            "--tb=short",
            test_dir,
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout for full test suite
            )

            test_result = self._parse_pytest_output(result.stdout + result.stderr)
            test_result.success = result.returncode == 0

            logger.info(
                "tests_completed",
                total=test_result.total_tests,
                passed=test_result.passed,
                failed=test_result.failed,
                all_tests=True,
            )

            return test_result

        except Exception as e:
            logger.error("test_run_failed", error=str(e))
            return TestResult(
                success=False,
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                duration_seconds=0.0,
                error=str(e),
            )

    async def clear_testmon_cache(self) -> None:
        """Clear testmon cache to force full test run."""
        testmon_db = self.repo_path / ".testmondata"
        if testmon_db.exists():
            testmon_db.unlink()
            logger.info("testmon_cache_cleared")

    def _parse_pytest_output(self, output: str) -> TestResult:
        """Parse pytest output to extract test counts.

        Args:
            output: pytest stdout/stderr

        Returns:
            TestResult with parsed counts
        """
        lines = output.split("\n")

        # Look for summary line like: "5 passed, 1 failed, 2 skipped in 1.23s"
        total_tests = 0
        passed = 0
        failed = 0
        skipped = 0
        duration = 0.0

        for line in lines:
            if " passed" in line or " failed" in line:
                # Parse summary line
                parts = line.split(",")
                for part in parts:
                    part = part.strip()
                    if " passed" in part:
                        passed = int(part.split()[0])
                    elif " failed" in part:
                        failed = int(part.split()[0])
                    elif " skipped" in part:
                        skipped = int(part.split()[0])
                    elif " in " in part and "s" in part:
                        # Extract duration like "1.23s"
                        try:
                            duration = float(part.split("in")[1].strip().rstrip("s"))
                        except (ValueError, IndexError):
                            pass

                total_tests = passed + failed + skipped
                break

        return TestResult(
            success=False,  # Will be set by caller
            total_tests=total_tests,
            passed=passed,
            failed=failed,
            skipped=skipped,
            duration_seconds=duration,
            output=output,
        )
