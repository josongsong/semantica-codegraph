"""CWE-22: Path Traversal - BAD (os.path.join doesn't sanitize)"""

import os

from flask import request, send_file


def download():
    filename = request.args.get("file")  # SOURCE

    # BAD: os.path.join doesn't prevent traversal
    # "../../../etc/passwd" still works
    file_path = os.path.join("/var/uploads", filename)

    return send_file(file_path)  # SINK: path traversal
