"""
CWE-77: Command Injection - BAD Example 02
Vulnerability: subprocess with shell=True
"""

import subprocess

from flask import Flask, request

app = Flask(__name__)


@app.route("/convert")
def convert_file():
    """BAD: subprocess with shell=True and user input."""
    filename = request.args.get("file")  # SOURCE
    format_type = request.args.get("format")  # SOURCE

    # SINK: shell=True makes this vulnerable
    cmd = f"convert {filename} -format {format_type} output.{format_type}"
    subprocess.call(cmd, shell=True)  # SINK: Vulnerable

    return "Conversion started"


@app.route("/backup")
def create_backup():
    """BAD: User input in subprocess.run with shell."""
    path = request.form.get("path")  # SOURCE

    # SINK: Command injection
    result = subprocess.run(
        f"tar -czf backup.tar.gz {path}",
        shell=True,
        capture_output=True,  # SINK: shell=True is dangerous
    )

    return "Backup created" if result.returncode == 0 else "Failed"
