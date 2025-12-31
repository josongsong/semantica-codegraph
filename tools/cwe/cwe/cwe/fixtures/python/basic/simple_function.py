"""Python Basic Scenario: Simple Functions"""


def add(a: int, b: int) -> int:
    """Simple addition function"""
    return a + b


def multiply(x: int, y: int) -> int:
    """Simple multiplication function"""
    result = x * y
    return result


class Calculator:
    """Basic calculator class"""

    def __init__(self):
        self.result = 0

    def calculate(self, a: int, b: int) -> int:
        self.result = a + b
        return self.result
