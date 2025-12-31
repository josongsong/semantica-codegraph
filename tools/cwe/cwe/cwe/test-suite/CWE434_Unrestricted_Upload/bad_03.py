"""CWE-434: Unrestricted Upload of File with Dangerous Type - BAD

Vulnerable: Path traversal in filename.
"""

import os
import shutil

from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/upload", methods=["POST"])
def upload_path_traversal():
    """BAD: Path traversal via filename."""
    file = request.files.get("file")  # SOURCE

    if not file:
        return jsonify({"error": "No file"}), 400

    # VULNERABILITY: filename could be "../../etc/cron.d/malicious"
    # This would write outside the intended directory
    upload_path = os.path.join("/var/uploads", file.filename)
    file.save(upload_path)  # SINK: Path traversal

    return jsonify({"path": upload_path})


@app.route("/upload/profile", methods=["POST"])
def upload_profile_image():
    """BAD: User-controlled subdirectory."""
    file = request.files.get("file")  # SOURCE
    username = request.form.get("username")  # SOURCE

    if not file:
        return jsonify({"error": "No file"}), 400

    # VULNERABILITY: username could contain "../" for path traversal
    user_dir = f"/uploads/profiles/{username}"
    os.makedirs(user_dir, exist_ok=True)

    filepath = os.path.join(user_dir, file.filename)
    file.save(filepath)  # SINK

    return jsonify({"status": "uploaded"})


@app.route("/upload/overwrite", methods=["POST"])
def upload_with_overwrite():
    """BAD: Can overwrite existing files."""
    file = request.files.get("file")  # SOURCE
    target_path = request.form.get("path")  # SOURCE: User controls destination!

    if not file or not target_path:
        return jsonify({"error": "Missing file or path"}), 400

    # VULNERABILITY: User controls the entire path
    # Could overwrite config files, scripts, etc.
    file.save(target_path)  # SINK: Arbitrary file write

    return jsonify({"status": "uploaded", "path": target_path})


if __name__ == "__main__":
    app.run()
