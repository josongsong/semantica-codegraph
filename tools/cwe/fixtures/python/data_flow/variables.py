"""Python Data Flow: Variable Dependencies"""


def data_flow_example(x: int, y: int) -> int:
    """Variable data flow"""
    a = x + y
    b = a * 2
    c = b - x
    result = c + y
    return result


def closure_example(multiplier: int):
    """Closure with variable capture"""

    def multiply(x: int) -> int:
        return x * multiplier

    return multiply


def variable_shadowing(x: int) -> int:
    """Variable shadowing"""
    result = x * 2
    if x > 0:
        result = x + 10  # Shadows outer result
    return result
