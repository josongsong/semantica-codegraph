"""CWE-78: OS Command Injection - BAD"""

import os


def process_file(filename: str) -> None:
    user_input = input("Enter filename: ")  # SOURCE: user input

    # BAD: Direct use of user input in shell command
    os.system(user_input)  # SINK: command injection - direct pass
