"""CWE-434: Unrestricted Upload of File with Dangerous Type - BAD

Vulnerable: Direct file save without any validation.
"""

import os

from flask import Flask, jsonify, request

app = Flask(__name__)
UPLOAD_FOLDER = "/var/www/uploads"


@app.route("/upload", methods=["POST"])
def upload_file():
    """BAD: Direct file save without validation."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]  # SOURCE: Uploaded file

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    # VULNERABILITY: Direct save without any validation
    file.save(os.path.join(UPLOAD_FOLDER, file.filename))  # SINK

    return jsonify({"status": "uploaded", "filename": file.filename})


@app.route("/upload/avatar", methods=["POST"])
def upload_avatar():
    """BAD: Avatar upload without type check."""
    file = request.files.get("avatar")  # SOURCE

    if file:
        # VULNERABILITY: Saving directly to public folder
        # Attacker could upload malicious.php, malicious.py, etc.
        filepath = f"/var/www/static/avatars/{file.filename}"
        file.save(filepath)  # SINK

        return jsonify({"avatar_url": f"/static/avatars/{file.filename}"})

    return jsonify({"error": "No file"}), 400


@app.route("/upload/document", methods=["POST"])
def upload_document():
    """BAD: Document upload preserving original filename."""
    file = request.files.get("document")  # SOURCE

    if file:
        # VULNERABILITY: Path traversal possible via filename
        # filename could be "../../../etc/passwd"
        destination = os.path.join("/uploads/documents", file.filename)
        file.save(destination)  # SINK

        return jsonify({"status": "uploaded"})

    return jsonify({"error": "No file"}), 400


if __name__ == "__main__":
    app.run()
