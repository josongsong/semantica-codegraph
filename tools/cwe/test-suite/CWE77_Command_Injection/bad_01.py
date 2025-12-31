"""
CWE-77: Command Injection - BAD Example 01
Vulnerability: String interpolation in os.system calls
"""

import os

from flask import Flask, request

app = Flask(__name__)


@app.route("/ping")
def ping_host():
    """BAD: Direct string interpolation in os.system."""
    host = request.args.get("host")  # SOURCE

    # SINK: Command injection via string formatting
    os.system(f"ping -c 4 {host}")  # SINK: Vulnerable

    return f"Pinged {host}"


@app.route("/lookup")
def dns_lookup():
    """BAD: User input in command execution."""
    domain = request.args.get("domain")  # SOURCE

    # SINK: Vulnerable to command injection
    result = os.popen(f"nslookup {domain}").read()  # SINK

    return f"<pre>{result}</pre>"
