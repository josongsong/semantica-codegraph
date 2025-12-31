"""
CWE-77: Command Injection - GOOD Example 02
Mitigation: Using shlex.quote for shell escaping
"""

import os
import shlex
import subprocess

from flask import Flask, request

app = Flask(__name__)

# Allowlist of valid commands
ALLOWED_FORMATS = {"png", "jpg", "gif", "pdf"}


@app.route("/convert")
def convert_file():
    """GOOD: Input validation and shlex.quote."""
    filename = request.args.get("file")  # SOURCE
    format_type = request.args.get("format")  # SOURCE

    # SAFE: Allowlist validation
    if format_type not in ALLOWED_FORMATS:
        return "Invalid format", 400

    # SAFE: shlex.quote escapes shell metacharacters
    safe_filename = shlex.quote(filename)
    cmd = f"convert {safe_filename} -format {format_type} output.{format_type}"
    subprocess.run(cmd, shell=True)  # SAFE: Input escaped

    return "Conversion started"


@app.route("/backup")
def create_backup():
    """GOOD: Using subprocess with list args."""
    path = request.form.get("path")  # SOURCE

    # SAFE: List arguments without shell
    result = subprocess.run(["tar", "-czf", "backup.tar.gz", path], capture_output=True)  # SAFE

    return "Backup created" if result.returncode == 0 else "Failed"
