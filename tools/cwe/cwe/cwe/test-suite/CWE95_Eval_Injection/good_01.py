"""CWE-95: Eval Injection - GOOD"""


def evaluate_safe():
    # GOOD: no eval with user input
    result = eval("1 + 1")
    return result
