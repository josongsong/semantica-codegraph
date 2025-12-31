"""CWE-434: Unrestricted Upload of File with Dangerous Type - BAD

Vulnerable: Client-side extension check only (easily bypassed).
"""

import os

from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/upload", methods=["POST"])
def upload_with_client_extension():
    """BAD: Only checking extension from filename (client-controlled)."""
    file = request.files.get("file")  # SOURCE

    if not file:
        return jsonify({"error": "No file"}), 400

    # BAD: Extension from filename is client-controlled
    # Attacker: "malicious.php.jpg" or "malicious.jpg" with PHP content
    if file.filename.endswith((".jpg", ".jpeg", ".png", ".gif")):
        file.save(f"/uploads/{file.filename}")  # SINK
        return jsonify({"status": "uploaded"})

    return jsonify({"error": "Only images allowed"}), 400


@app.route("/upload/v2", methods=["POST"])
def upload_with_split_extension():
    """BAD: Extension check that can be bypassed with double extension."""
    file = request.files.get("file")  # SOURCE

    if not file:
        return jsonify({"error": "No file"}), 400

    # BAD: Can be bypassed with "shell.php.jpg"
    # Some servers process .php regardless of final extension
    ext = file.filename.rsplit(".", 1)[-1].lower()
    allowed = {"jpg", "jpeg", "png", "gif"}

    if ext in allowed:
        file.save(f"/uploads/{file.filename}")  # SINK
        return jsonify({"status": "uploaded"})

    return jsonify({"error": "Invalid extension"}), 400


@app.route("/upload/v3", methods=["POST"])
def upload_content_type_only():
    """BAD: Only checking Content-Type header (also client-controlled)."""
    file = request.files.get("file")  # SOURCE

    if not file:
        return jsonify({"error": "No file"}), 400

    # BAD: Content-Type is set by client, easily spoofed
    content_type = file.content_type
    allowed_types = {"image/jpeg", "image/png", "image/gif"}

    if content_type in allowed_types:
        file.save(f"/uploads/{file.filename}")  # SINK
        return jsonify({"status": "uploaded"})

    return jsonify({"error": "Invalid content type"}), 400


if __name__ == "__main__":
    app.run()
