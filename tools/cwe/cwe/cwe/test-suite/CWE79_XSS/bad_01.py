"""CWE-79: XSS - BAD"""

from flask import render_template_string, request


def greet():
    name = request.args.get("name")  # SOURCE: user input

    # BAD: Unescaped user input in HTML
    html = f"<h1>Hello, {name}!</h1>"
    return render_template_string(html)  # SINK: XSS
