"""CWE-79: XSS - GOOD (template auto-escape)"""

from flask import render_template, request


def show_comment():
    comment = request.form.get("comment")

    # GOOD: Jinja2 auto-escapes by default
    return render_template("comment.html", comment=comment)
