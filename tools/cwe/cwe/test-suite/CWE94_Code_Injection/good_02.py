"""CWE-94: Code Injection - GOOD (sandbox)"""

from flask import request
from RestrictedPython import compile_restricted, safe_globals


def run_script():
    code = request.json.get("code")

    # GOOD: Restricted execution environment
    byte_code = compile_restricted(code, "<string>", "exec")
    exec(byte_code, safe_globals)
