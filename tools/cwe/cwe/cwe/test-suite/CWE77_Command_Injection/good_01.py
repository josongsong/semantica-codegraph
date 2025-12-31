"""
CWE-77: Command Injection - GOOD Example 01
Mitigation: Using subprocess with list arguments
"""

import subprocess

from flask import Flask, request

app = Flask(__name__)


@app.route("/ping")
def ping_host():
    """GOOD: Using subprocess with list arguments (no shell)."""
    host = request.args.get("host")  # SOURCE

    # SAFE: List arguments prevent injection
    result = subprocess.run(
        ["ping", "-c", "4", host],
        shell=False,
        capture_output=True,
        text=True,  # SAFE: List args  # SAFE: No shell
    )

    return f"<pre>{result.stdout}</pre>"


@app.route("/lookup")
def dns_lookup():
    """GOOD: subprocess.run with list arguments."""
    domain = request.args.get("domain")  # SOURCE

    # SAFE: No shell interpretation
    result = subprocess.run(["nslookup", domain], capture_output=True, text=True)  # SAFE: List args

    return f"<pre>{result.stdout}</pre>"
