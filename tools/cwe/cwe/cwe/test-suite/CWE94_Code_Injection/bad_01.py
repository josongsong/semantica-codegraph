"""CWE-94: Code Injection via eval - BAD"""


def calculate():
    expression = input("Enter expression: ")  # SOURCE: user input

    # BAD: eval with user input
    result = eval(expression)  # SINK: code injection
    return result
