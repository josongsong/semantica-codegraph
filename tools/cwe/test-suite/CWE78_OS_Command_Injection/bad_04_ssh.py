"""CWE-78: OS Command Injection via SSH - BAD"""

import paramiko
from flask import request


def execute_remote():
    cmd = request.args.get("cmd")  # SOURCE: HTTP request

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("server.example.com", username="admin", password="secret")

    # BAD: User input directly passed to SSH command
    stdin, stdout, stderr = client.exec_command(cmd)  # SINK: SSH command injection

    return stdout.read().decode()
