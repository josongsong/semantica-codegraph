"""CWE-22: Path Traversal - GOOD"""

import os

from flask import abort, request, send_file

UPLOAD_DIR = "/var/uploads"


def download_file():
    filename = request.args.get("file")

    # GOOD: Resolve and validate path
    file_path = os.path.realpath(os.path.join(UPLOAD_DIR, filename))
    if not file_path.startswith(os.path.realpath(UPLOAD_DIR)):
        abort(403)
    return send_file(file_path)
