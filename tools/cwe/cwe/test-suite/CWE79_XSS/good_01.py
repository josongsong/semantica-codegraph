"""CWE-79: XSS - GOOD"""

from flask import render_template_string, request
from markupsafe import escape


def greet():
    name = request.args.get("name")

    # GOOD: HTML escape user input
    safe_name = escape(name)
    html = f"<h1>Hello, {safe_name}!</h1>"
    return render_template_string(html)
