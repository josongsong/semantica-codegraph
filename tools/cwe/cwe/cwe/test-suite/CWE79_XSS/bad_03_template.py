"""CWE-79: XSS - BAD (Template injection)"""

from flask import render_template_string, request


def greet():
    name = request.args.get("name")  # SOURCE

    # BAD: User input directly in template
    template = f"<h1>Hello {name}!</h1>"
    return render_template_string(template)  # SINK: XSS via template
