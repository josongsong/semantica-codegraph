"""CWE-78: OS Command Injection via SSH - GOOD (allowlist)"""

import paramiko
from flask import abort, request

ALLOWED_COMMANDS = {"ls", "pwd", "whoami", "uptime"}


def execute_remote():
    cmd = request.args.get("cmd")  # SOURCE: HTTP request

    # GOOD: Allowlist validation
    if cmd not in ALLOWED_COMMANDS:
        abort(403)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("server.example.com", username="admin", password="secret")

    # SAFE: Only allowlisted commands
    stdin, stdout, stderr = client.exec_command(cmd)

    return stdout.read().decode()
