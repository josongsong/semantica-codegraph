"""CWE-78: OS Command Injection - BAD (shell=True)"""

import subprocess

from flask import request


def run_command():
    cmd = request.args.get("cmd")  # SOURCE

    # BAD: shell=True with user input
    result = subprocess.run(cmd, shell=True, capture_output=True)
    return result.stdout.decode()
