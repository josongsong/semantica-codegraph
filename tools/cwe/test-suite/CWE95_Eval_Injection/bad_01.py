"""CWE-95: Eval Injection - BAD"""


def evaluate():
    user_input = input("Expression: ")
    # BAD: eval with user input
    result = eval(user_input)
    return result
