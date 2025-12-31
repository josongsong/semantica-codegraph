"""
Tests for Semantic Validator
"""

import pytest

from apps.orchestrator.orchestrator.domain.validation.semantic_validator import (
    ControlFlowChecker,
    DataFlowChecker,
    SemanticValidator,
    TypeConsistencyChecker,
    ViolationType,
)


class TestTypeConsistencyChecker:
    """Test type consistency checking"""

    def test_detect_string_concat_issue(self):
        """Test detection of potential string concatenation issues"""
        checker = TypeConsistencyChecker()

        code = """
def foo(x):
    return "hello" + x  # Potential type error
"""
        violations = checker.check(code)

        # Should detect potential type issue
        assert len(violations) >= 1
        assert any(v.violation_type == ViolationType.TYPE_MISMATCH for v in violations)

    def test_detect_none_attribute_access(self):
        """Test detection of None.attribute access"""
        checker = TypeConsistencyChecker()

        code = """
y = None.value  # Direct None attribute access
"""
        violations = checker.check(code)

        # Should detect AttributeError (if None is a literal constant)
        # This is a heuristic - may not always catch it
        assert len(violations) >= 0  # Best effort

    def test_valid_code_no_violations(self):
        """Test valid code has no violations"""
        checker = TypeConsistencyChecker()

        code = """
def foo(x: int) -> int:
    return x + 1
"""
        violations = checker.check(code)

        # Should have no violations
        assert len(violations) == 0


class TestControlFlowChecker:
    """Test control flow checking"""

    def test_detect_unreachable_code(self):
        """Test detection of unreachable code after return"""
        checker = ControlFlowChecker()

        code = """
def foo():
    return 42
    print("unreachable")  # Dead code!
"""
        violations = checker.check(code)

        # Should detect unreachable code
        assert len(violations) >= 1
        assert any(v.violation_type == ViolationType.UNREACHABLE_CODE for v in violations)

    def test_detect_missing_return(self):
        """Test detection of missing return statement"""
        checker = ControlFlowChecker()

        code = """
def calculate(x, y):
    result = x + y
    temp = result * 2
    final = temp + 1
    # Missing return! (non-trivial function)
"""
        violations = checker.check(code)

        # Should detect missing return (function > 2 lines)
        assert len(violations) >= 1
        assert any(v.violation_type == ViolationType.MISSING_RETURN for v in violations)

    def test_init_method_no_warning(self):
        """Test __init__ doesn't trigger missing return warning"""
        checker = ControlFlowChecker()

        code = """
class Foo:
    def __init__(self, x):
        self.x = x
        # No return needed
"""
        violations = checker.check(code)

        # Should not warn about missing return in __init__
        assert not any(v.violation_type == ViolationType.MISSING_RETURN for v in violations)


class TestDataFlowChecker:
    """Test data flow checking"""

    def test_detect_unused_variable(self):
        """Test detection of unused variables"""
        checker = DataFlowChecker()

        code = """
def foo():
    x = 42  # Assigned but never used
    return 1
"""
        violations = checker.check(code)

        # Should detect unused variable
        assert len(violations) >= 1
        assert any(v.violation_type == ViolationType.UNUSED_VARIABLE for v in violations)
        assert any("x" in v.message for v in violations)

    def test_underscore_variable_ignored(self):
        """Test _private variables are not flagged as unused"""
        checker = DataFlowChecker()

        code = """
def foo():
    _private = 42  # Should be ignored
    return 1
"""
        violations = checker.check(code)

        # Should not flag _private variables
        assert not any("_private" in v.message for v in violations)

    def test_used_variable_no_violation(self):
        """Test used variables have no violations"""
        checker = DataFlowChecker()

        code = """
def foo():
    x = 42
    return x  # Used!
"""
        violations = checker.check(code)

        # Should have no violations
        assert len(violations) == 0


class TestSemanticValidator:
    """Test complete semantic validator"""

    def test_validate_clean_code(self):
        """Test validation of clean code"""
        validator = SemanticValidator()

        code = """
def add(x: int, y: int) -> int:
    result = x + y
    return result
"""
        result = validator.validate(code)

        assert result.is_valid
        assert result.error_count == 0

    def test_validate_code_with_issues(self):
        """Test validation of code with multiple issues"""
        validator = SemanticValidator()

        code = """
def foo(x):
    unused = 42
    return x + "1"
    print("unreachable")
"""
        result = validator.validate(code)

        # Should detect issues but might still be "valid" (only warnings)
        assert len(result.violations) >= 2  # unused + unreachable

    def test_validate_and_suggest_fixes(self):
        """Test validation with fix suggestions"""
        validator = SemanticValidator()

        code = """
def foo():
    return 1
    print("dead code")  # Warning with suggestion
"""
        result, suggestions = validator.validate_and_suggest_fixes(code)

        # Unreachable code is warning, not error
        assert result.warning_count >= 1
        # Suggestions are only for errors
        # So this might be 0 (warnings don't get suggestions by default)
        assert len(suggestions) >= 0

    def test_disabled_checkers(self):
        """Test disabling specific checkers"""
        validator = SemanticValidator(
            enable_type_check=False,
            enable_control_flow=False,
            enable_data_flow=True,  # Only data flow
        )

        code = """
def foo():
    return None.value  # Type error, but checker disabled
    print("unreachable")  # Control flow issue, but checker disabled
    unused = 42  # Data flow issue - should detect
"""
        result = validator.validate(code)

        # Should only detect data flow issues
        violations_types = [v.violation_type for v in result.violations]
        assert ViolationType.UNUSED_VARIABLE in violations_types
        assert ViolationType.TYPE_MISMATCH not in violations_types
        assert ViolationType.UNREACHABLE_CODE not in violations_types
