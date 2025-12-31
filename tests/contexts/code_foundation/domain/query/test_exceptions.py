"""
Query Exceptions Unit Tests

SOTA L11급:
- Base case: 예외 생성, 메시지
- Edge case: None 파라미터
"""

import pytest

from codegraph_engine.code_foundation.domain.query.exceptions import (
    InvalidQueryError,
    NodeLimitExceededError,
    PathLimitExceededError,
    QueryEngineError,
    QueryTimeoutError,
)


class TestInvalidQueryError:
    """InvalidQueryError 테스트"""

    def test_base_case_message_only(self):
        """메시지만"""
        error = InvalidQueryError("Invalid query")

        assert error.message == "Invalid query"
        assert "Invalid query" in str(error)

    def test_base_case_with_suggestion(self):
        """suggestion 포함"""
        error = InvalidQueryError("Invalid query", suggestion="Use Q.Var instead")

        assert error.suggestion == "Use Q.Var instead"
        assert "Suggestion" in str(error)

    def test_edge_case_none_suggestion(self):
        """suggestion이 None"""
        error = InvalidQueryError("Error", suggestion=None)

        assert "Suggestion" not in str(error)


class TestQueryTimeoutError:
    """QueryTimeoutError 테스트"""

    def test_base_case(self):
        """기본"""
        error = QueryTimeoutError(timeout_ms=5000, elapsed_ms=6000)

        assert error.timeout_ms == 5000
        assert error.elapsed_ms == 6000
        assert "6000ms" in str(error)
        assert "5000ms" in str(error)


class TestPathLimitExceededError:
    """PathLimitExceededError 테스트"""

    def test_base_case(self):
        """기본"""
        error = PathLimitExceededError(limit=100)

        assert error.limit == 100
        assert "100" in str(error)


class TestNodeLimitExceededError:
    """NodeLimitExceededError 테스트"""

    def test_base_case(self):
        """기본"""
        error = NodeLimitExceededError(limit=10000)

        assert error.limit == 10000
        assert "10000" in str(error)


class TestExceptionHierarchy:
    """예외 계층 구조 테스트"""

    def test_all_inherit_from_base(self):
        """모든 예외가 QueryEngineError 상속"""
        assert issubclass(InvalidQueryError, QueryEngineError)
        assert issubclass(QueryTimeoutError, QueryEngineError)
        assert issubclass(PathLimitExceededError, QueryEngineError)
        assert issubclass(NodeLimitExceededError, QueryEngineError)

    def test_can_catch_with_base(self):
        """base class로 catch 가능"""
        with pytest.raises(QueryEngineError):
            raise InvalidQueryError("test")
