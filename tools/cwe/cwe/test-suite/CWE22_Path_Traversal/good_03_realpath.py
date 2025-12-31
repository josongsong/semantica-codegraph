"""CWE-22: Path Traversal - GOOD (realpath check)"""

import os

from flask import abort, request, send_file

UPLOAD_DIR = "/var/uploads"


def download():
    filename = request.args.get("file")  # SOURCE

    # GOOD: Resolve real path and check it's within allowed directory
    file_path = os.path.join(UPLOAD_DIR, filename)
    real_path = os.path.realpath(file_path)

    if not real_path.startswith(os.path.realpath(UPLOAD_DIR)):
        abort(403, "Access denied")

    return send_file(real_path)  # SAFE: path validated
