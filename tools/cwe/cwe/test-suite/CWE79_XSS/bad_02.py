"""CWE-79: XSS via Markup - BAD"""

from flask import request
from markupsafe import Markup


def show_comment():
    comment = request.form.get("comment")  # SOURCE: form data

    # BAD: Marking user input as safe
    safe_comment = Markup(comment)  # SINK: XSS via Markup
    return f"<div>{safe_comment}</div>"
