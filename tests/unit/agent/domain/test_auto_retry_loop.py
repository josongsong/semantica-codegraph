"""
Tests for Auto-Retry Loop (Devin-style)
"""

import pytest

from apps.orchestrator.orchestrator.domain.feedback.auto_retry_loop import (
    AutoRetryLoop,
    CompleteAutoRetryLoop,
    ConvergenceDetector,
    ErrorClassifier,
    ErrorType,
    RetryAttempt,
)


class TestErrorClassifier:
    """Test error classification"""

    def test_syntax_error(self):
        """Test syntax error classification"""
        classifier = ErrorClassifier()

        error = "SyntaxError: invalid syntax"
        assert classifier.classify(error) == ErrorType.SYNTAX

    def test_import_error(self):
        """Test import error classification"""
        classifier = ErrorClassifier()

        error = "ModuleNotFoundError: No module named 'json'"
        assert classifier.classify(error) == ErrorType.IMPORT

    def test_name_error(self):
        """Test name error classification"""
        classifier = ErrorClassifier()

        error = "NameError: name 'variable' is not defined"
        assert classifier.classify(error) == ErrorType.NAME

    def test_type_error(self):
        """Test type error classification"""
        classifier = ErrorClassifier()

        error = "TypeError: unsupported operand type(s) for +: 'int' and 'str'"
        assert classifier.classify(error) == ErrorType.TYPE

    def test_unknown_error(self):
        """Test unknown error classification"""
        classifier = ErrorClassifier()

        error = "Some random error"
        assert classifier.classify(error) == ErrorType.UNKNOWN


class TestConvergenceDetector:
    """Test convergence detection"""

    def test_same_error_repetition(self):
        """Test detection of same error 3 times"""
        detector = ConvergenceDetector()

        attempts = [
            RetryAttempt(1, "code1", ErrorType.SYNTAX, "error A", "fix", False, 10),
            RetryAttempt(2, "code2", ErrorType.SYNTAX, "error A", "fix", False, 10),
            RetryAttempt(3, "code3", ErrorType.SYNTAX, "error A", "fix", False, 10),
        ]

        is_stuck, reason = detector.detect(attempts)

        assert is_stuck
        assert reason == "STUCK_SAME_ERROR"

    def test_oscillation(self):
        """Test detection of A → B → A oscillation"""
        detector = ConvergenceDetector()

        attempts = [
            RetryAttempt(1, "code_a", ErrorType.SYNTAX, "error", "fix", False, 10),
            RetryAttempt(2, "code_b", ErrorType.SYNTAX, "error", "fix", False, 10),
            RetryAttempt(3, "code_a", ErrorType.SYNTAX, "error", "fix", False, 10),  # Back to A
        ]

        is_stuck, reason = detector.detect(attempts)

        assert is_stuck
        assert reason == "STUCK_OSCILLATING"

    def test_not_stuck(self):
        """Test normal progression (not stuck)"""
        detector = ConvergenceDetector()

        attempts = [
            RetryAttempt(1, "code1", ErrorType.SYNTAX, "error A", "fix", False, 10),
            RetryAttempt(2, "code2", ErrorType.IMPORT, "error B", "fix", False, 10),
        ]

        is_stuck, reason = detector.detect(attempts)

        assert not is_stuck


@pytest.mark.asyncio
class TestAutoRetryLoop:
    """Test Auto-Retry Loop"""

    async def test_immediate_success(self):
        """Test immediate success (no retry needed)"""
        retry_loop = AutoRetryLoop(max_retries=5)

        call_count = [0]

        def execute_fn(code):
            call_count[0] += 1
            return True, "success", ""  # Immediate success

        def fix_fn(code, error_type, error_msg):
            return code  # No fix needed

        result = await retry_loop.execute_with_retry(
            initial_code="print('hello')",
            execute_fn=execute_fn,
            fix_fn=fix_fn,
        )

        assert result.success
        assert result.total_attempts == 1
        assert call_count[0] == 1

    async def test_retry_until_success(self):
        """Test retry until success"""
        retry_loop = AutoRetryLoop(max_retries=5)

        attempts = [0]

        def execute_fn(code):
            attempts[0] += 1
            # Succeed on 3rd attempt
            if attempts[0] >= 3:
                return True, "success", ""
            return False, "", "error"

        def fix_fn(code, error_type, error_msg):
            return code + f"_fixed_{attempts[0]}"

        result = await retry_loop.execute_with_retry(
            initial_code="code",
            execute_fn=execute_fn,
            fix_fn=fix_fn,
        )

        assert result.success
        assert result.total_attempts == 3
        assert attempts[0] == 3

    async def test_max_retries_exhausted(self):
        """Test max retries reached"""
        retry_loop = AutoRetryLoop(max_retries=3, enable_convergence_detection=False)  # Disable convergence

        def execute_fn(code):
            return False, "", "persistent error"  # Always fail

        def fix_fn(code, error_type, error_msg):
            return code + "_fixed"  # Actually change code

        result = await retry_loop.execute_with_retry(
            initial_code="code",
            execute_fn=execute_fn,
            fix_fn=fix_fn,
        )

        assert not result.success
        assert result.total_attempts == 3
        assert result.convergence_reason == "MAX_RETRIES_REACHED"

    async def test_convergence_detection(self):
        """Test convergence detection stops early"""
        retry_loop = AutoRetryLoop(max_retries=10, enable_convergence_detection=True)

        def execute_fn(code):
            return False, "", "same error"  # Always same error

        def fix_fn(code, error_type, error_msg):
            return code  # No actual fix (same code)

        result = await retry_loop.execute_with_retry(
            initial_code="code",
            execute_fn=execute_fn,
            fix_fn=fix_fn,
        )

        # Should stop early due to no change
        assert not result.success
        assert result.total_attempts < 10  # Stopped early
        # Could be STUCK_NO_CHANGE or STUCK_SAME_ERROR
        assert result.convergence_reason in ["STUCK_NO_CHANGE", "STUCK_SAME_ERROR"]


@pytest.mark.asyncio
class TestCompleteAutoRetryLoop:
    """Test complete auto-retry with built-in fixes"""

    async def test_auto_fix_import_error(self):
        """Test automatic import error fixing"""
        retry_loop = CompleteAutoRetryLoop(max_retries=3)

        attempts = [0]

        def execute_fn(code):
            attempts[0] += 1
            # First attempt: import error
            # Second attempt: should have import
            if "import json" in code:
                return True, "success", ""
            return False, "", "ModuleNotFoundError: No module named 'json'"

        result = await retry_loop.execute_with_auto_fix(
            initial_code="data = json.dumps({'key': 'value'})",
            execute_fn=execute_fn,
        )

        assert result.success
        assert "import json" in result.final_code
        assert result.total_attempts == 2  # Fixed on 2nd attempt
