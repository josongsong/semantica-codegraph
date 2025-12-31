"""CWE-78: OS Command Injection - GOOD (Allowlist)"""

import subprocess

from flask import request

ALLOWED_COMMANDS = {"ls", "pwd", "whoami", "date"}


def run_command():
    cmd = request.args.get("cmd")  # SOURCE

    # GOOD: Allowlist validation
    if cmd not in ALLOWED_COMMANDS:
        return "Command not allowed"

    result = subprocess.run([cmd], capture_output=True)
    return result.stdout.decode()
