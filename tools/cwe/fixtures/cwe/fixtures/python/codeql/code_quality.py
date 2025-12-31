"""CodeQL Scenario: Code Quality Issues"""


def unused_variable_example():
    """Function with unused variables"""
    x = 10  # Used

    return x


def dead_code_example(condition: bool):
    """Function with dead code"""
    if condition:
        return "active"
    else:
        return "inactive"

    # DEAD CODE - unreachable
    print("This will never execute")
    return "never"


def complex_condition_example(a: int, b: int, c: int, d: int):
    """Complex nested conditions - should be simplified"""
    # COMPLEX: Too many nested conditions
    if a > 0:
        if b > 0:
            if c > 0:
                if d > 0:
                    return "all positive"
                else:
                    return "d not positive"
            else:
                return "c not positive"
        else:
            return "b not positive"
    else:
        return "a not positive"


def duplicate_code_1(x: int) -> int:
    """Duplicate code pattern 1"""
    result = 0
    result += x * 2
    result += x * 3
    result += 10
    return result


def duplicate_code_2(y: int) -> int:
    """Duplicate code pattern 2 - DUPLICATE"""
    result = 0
    result += y * 2
    result += y * 3
    result += 10
    return result


def resource_leak_example(filename: str):
    """Potential resource leak"""
    # ISSUE: File not properly closed
    f = open(filename)
    content = f.read()
    # Missing: f.close()
    return content


def exception_handling_issue():
    """Poor exception handling"""
    try:
        risky_operation()
    except:  # ISSUE: Bare except
        pass  # ISSUE: Silent failure


def risky_operation():
    """Simulated risky operation"""
    raise ValueError("Error")


class UnusedClass:
    """Class that is never instantiated - UNUSED"""

    def method(self):
        return "unused"


def always_true_condition(x: int):
    """Condition that is always true"""
    if x or True:  # ISSUE: Always true
        return "always"
    return "never"


def redundant_comparison(x: int):
    """Redundant comparison"""
    if x > 10 and x > 5:  # REDUNDANT: x > 10 implies x > 5
        return "redundant"
    return "ok"
