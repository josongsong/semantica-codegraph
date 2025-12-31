"""CWE-94: Code Injection - GOOD"""

import ast


def calculate():
    expression = input("Enter expression: ")

    # GOOD: ast.literal_eval for safe evaluation
    result = ast.literal_eval(expression)
    return result
