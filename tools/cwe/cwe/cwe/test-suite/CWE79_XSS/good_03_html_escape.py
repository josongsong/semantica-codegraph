"""CWE-79: XSS - GOOD (HTML escape)"""

from flask import request
from markupsafe import escape


def greet():
    name = request.args.get("name")  # SOURCE

    # GOOD: Escape HTML entities
    safe_name = escape(name)
    return f"<h1>Hello {safe_name}!</h1>"
