"""
Query Engine Exceptions

AI-friendly error messages for Query DSL.
"""


class QueryEngineError(Exception):
    """Base exception for Query Engine"""

    pass


class InvalidQueryError(QueryEngineError):
    """
    Invalid query construction

    Raised when:
    - Invalid type connectivity (e.g., Module >> Var)
    - Invalid operator usage
    - Malformed query structure
    """

    def __init__(self, message: str, suggestion: str | None = None):
        self.message = message
        self.suggestion = suggestion
        full_message = message
        if suggestion:
            full_message += f"\n💡 Suggestion: {suggestion}"
        super().__init__(full_message)


class QueryTimeoutError(QueryEngineError):
    """
    Query execution timeout

    Raised when query exceeds timeout limit.
    """

    def __init__(self, timeout_ms: int, elapsed_ms: int):
        self.timeout_ms = timeout_ms
        self.elapsed_ms = elapsed_ms
        super().__init__(f"Query timeout: {elapsed_ms}ms > {timeout_ms}ms limit")


class PathLimitExceededError(QueryEngineError):
    """
    Path limit exceeded

    Raised when number of paths exceeds limit.
    """

    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(f"Path limit exceeded: {limit} paths")


class NodeLimitExceededError(QueryEngineError):
    """
    Node limit exceeded

    Raised when traversal visits too many nodes.
    """

    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(f"Node limit exceeded: {limit} nodes visited")
