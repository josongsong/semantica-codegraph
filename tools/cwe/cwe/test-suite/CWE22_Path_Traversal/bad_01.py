"""CWE-22: Path Traversal - BAD"""

from flask import request, send_file


def download_file():
    filename = request.args.get("file")  # SOURCE: user input

    # BAD: Direct use of user input in file path
    file_path = f"/var/uploads/{filename}"
    return send_file(open(file_path, "rb"))  # SINK: path traversal
