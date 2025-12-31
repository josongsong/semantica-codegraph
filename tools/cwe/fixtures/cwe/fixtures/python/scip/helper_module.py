"""SCIP Helper: Module for cross-file testing"""


class HelperClass:
    """Helper class for cross-file references"""

    def transform(self, value: int) -> int:
        return value * 2


def helper_function(x: int) -> int:
    """Helper function"""
    return x + 10
