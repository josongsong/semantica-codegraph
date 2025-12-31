"""CWE-434: Unrestricted Upload of File with Dangerous Type - GOOD

Safe: Extension whitelist + MIME type validation + secure filename.
"""

import os
from uuid import uuid4

import magic
from flask import Flask, jsonify, request
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = "/var/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_mime_type(file_content: bytes) -> str | None:
    """Validate file's actual MIME type from content."""
    mime = magic.from_buffer(file_content, mime=True)
    return mime if mime in ALLOWED_MIMES else None


@app.route("/upload", methods=["POST"])
def upload_file():
    """GOOD: Multiple layers of validation."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    # SANITIZER 1: Extension whitelist
    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400

    # SANITIZER 2: Read content for MIME check
    file_content = file.read()
    file.seek(0)  # Reset for save

    # SANITIZER 3: File size check
    if len(file_content) > MAX_FILE_SIZE:
        return jsonify({"error": "File too large"}), 400

    # SANITIZER 4: MIME type validation from actual content
    mime_type = validate_mime_type(file_content)
    if not mime_type:
        return jsonify({"error": "Invalid file content"}), 400

    # SANITIZER 5: Secure filename (removes path traversal)
    filename = secure_filename(file.filename)

    # SANITIZER 6: Generate unique filename
    ext = filename.rsplit(".", 1)[1].lower()
    unique_filename = f"{uuid4()}.{ext}"

    # Safe to save
    filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
    file.save(filepath)

    return jsonify({"status": "uploaded", "filename": unique_filename, "mime_type": mime_type})


if __name__ == "__main__":
    app.run()
