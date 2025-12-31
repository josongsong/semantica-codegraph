"""CWE-78: OS Command Injection - GOOD (allowlist)"""

import subprocess

from flask import request

ALLOWED_COMMANDS = {"ls", "pwd", "whoami"}


def run_command():
    cmd = request.args.get("cmd")

    # GOOD: Allowlist validation
    if cmd in ALLOWED_COMMANDS:
        subprocess.call([cmd], shell=False)
