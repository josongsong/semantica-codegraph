"""CWE-78: OS Command Injection - GOOD"""

import subprocess


def process_file(filename: str) -> None:
    user_input = input("Enter filename: ")

    # GOOD: Use subprocess with list arguments (no shell)
    subprocess.run(["cat", user_input], check=True)
