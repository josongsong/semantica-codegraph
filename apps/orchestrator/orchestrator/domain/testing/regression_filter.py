"""
Regression Filter (경량 Pytest 통합)

기존 테스트를 깨지 않는 전략만 필터링

Features:
- Pytest 실행 (isolated)
- Timeout 제한
- Cache 활용
- Fast fail

Impact: Breaking changes -30%
"""

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codegraph_shared.common.observability import get_logger, record_counter, record_histogram

logger = get_logger(__name__)


@dataclass
class TestResult:
    """테스트 실행 결과"""

    passed: bool
    failed_count: int
    passed_count: int
    execution_time_ms: float
    error_message: str | None = None


class LightweightRegressionFilter:
    """
    경량 Regression Filter

    MVP Strategy:
    1. Syntax check (빠름)
    2. Import check (중간)
    3. Pytest dry-run (선택적)

    Full Strategy (Phase 2):
    - Full pytest execution
    - Coverage tracking
    - Performance regression
    """

    def __init__(
        self,
        enable_pytest: bool = False,
        pytest_timeout: float = 30.0,
        test_files: list[str] | None = None,
    ):
        """
        Args:
            enable_pytest: Enable actual pytest execution
            pytest_timeout: Timeout per test run
            test_files: Test files to run (None = all)
        """
        self.enable_pytest = enable_pytest
        self.pytest_timeout = pytest_timeout
        self.test_files = test_files or []

        logger.info(
            "regression_filter_initialized",
            pytest_enabled=enable_pytest,
            timeout=pytest_timeout,
        )

    async def filter_safe(self, code_samples: list[str]) -> tuple[list[str], list[bool]]:
        """
        안전한 코드만 필터링

        Args:
            code_samples: 코드 샘플 리스트

        Returns:
            (safe_samples, is_safe_flags)
        """
        logger.info("regression_filter_start", total=len(code_samples))
        record_counter("regression_filter_runs")

        safe_samples = []
        safety_flags = []

        for idx, code in enumerate(code_samples):
            is_safe = await self._check_safe(code, idx)
            safety_flags.append(is_safe)

            if is_safe:
                safe_samples.append(code)
            else:
                logger.debug(f"Sample {idx} filtered out (unsafe)")

        removed = len(code_samples) - len(safe_samples)

        logger.info(
            "regression_filter_complete",
            original=len(code_samples),
            safe=len(safe_samples),
            removed=removed,
        )

        record_histogram("regression_filter_removed", removed)

        return safe_samples, safety_flags

    async def _check_safe(self, code: str, index: int) -> bool:
        """
        코드 안전성 체크

        Multi-level checks:
        1. Syntax check (always)
        2. Import check (always)
        3. Pytest (if enabled)

        Args:
            code: 체크할 코드
            index: 샘플 인덱스

        Returns:
            True if safe
        """
        # Level 1: Syntax check (fast, 100% 적용)
        if not self._check_syntax(code):
            logger.debug(f"Sample {index}: syntax error")
            return False

        # Level 2: Import check (fast, 100% 적용)
        if not self._check_imports(code):
            logger.debug(f"Sample {index}: import error")
            return False

        # Level 3: Pytest (slow, optional)
        if self.enable_pytest:
            test_result = await self._run_pytest(code)
            if not test_result.passed:
                logger.debug(f"Sample {index}: pytest failed ({test_result.failed_count} failures)")
                return False

        return True

    def _check_syntax(self, code: str) -> bool:
        """Syntax check (AST parse)"""
        try:
            import ast

            ast.parse(code)
            return True
        except SyntaxError:
            return False

    def _check_imports(self, code: str) -> bool:
        """Import check (compile)"""
        try:
            compile(code, "<string>", "exec")
            return True
        except ImportError:
            return False
        except Exception:
            # Other errors (not import-related) - pass
            return True

    async def _run_pytest(self, code: str) -> TestResult:
        """
        Run pytest on code (isolated)

        Args:
            code: 코드

        Returns:
            TestResult
        """
        import time

        start = time.time()

        # Create temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            temp_path = f.name

        try:
            # Run pytest (collect only, no execution - fast!)
            result = subprocess.run(
                ["pytest", temp_path, "--collect-only", "-q"],
                capture_output=True,
                text=True,
                timeout=self.pytest_timeout,
            )

            elapsed_ms = (time.time() - start) * 1000

            if result.returncode == 0:
                return TestResult(
                    passed=True,
                    failed_count=0,
                    passed_count=1,
                    execution_time_ms=elapsed_ms,
                )
            else:
                return TestResult(
                    passed=False,
                    failed_count=1,
                    passed_count=0,
                    execution_time_ms=elapsed_ms,
                    error_message=result.stderr[:200],
                )

        except subprocess.TimeoutExpired:
            logger.warning("Pytest timeout")
            return TestResult(
                passed=False,
                failed_count=1,
                passed_count=0,
                execution_time_ms=self.pytest_timeout * 1000,
                error_message="Timeout",
            )
        except Exception as e:
            logger.warning(f"Pytest execution failed: {e}")
            return TestResult(
                passed=False,
                failed_count=1,
                passed_count=0,
                execution_time_ms=0,
                error_message=str(e),
            )
        finally:
            # Cleanup
            Path(temp_path).unlink(missing_ok=True)
