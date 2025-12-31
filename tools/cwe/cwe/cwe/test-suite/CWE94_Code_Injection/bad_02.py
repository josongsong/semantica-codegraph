"""CWE-94: Code Injection via exec - BAD"""

from flask import request


def run_script():
    code = request.json.get("code")  # SOURCE: request body

    # BAD: exec with user input
    exec(code)  # SINK: code injection
