"""CWE-78: OS Command Injection via subprocess - BAD"""

import subprocess

from flask import request


def run_command():
    cmd = request.args.get("cmd")  # SOURCE: request parameter

    # BAD: shell=True with user input
    subprocess.call(cmd, shell=True)  # SINK: command injection
