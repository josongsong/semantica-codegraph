"""CWE-434: Unrestricted Upload of File with Dangerous Type - GOOD

Safe: Secure filename + storage outside web root.
"""

import os
from hashlib import sha256
from uuid import uuid4

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Store OUTSIDE web root - not directly accessible via URL
UPLOAD_FOLDER = "/var/app-data/uploads"  # Not in /var/www/
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt"}


def get_safe_filename(original_filename: str) -> tuple[str, str]:
    """Generate a safe, unique filename."""
    # SANITIZER: Remove path traversal and special chars
    safe_name = secure_filename(original_filename)

    if not safe_name or "." not in safe_name:
        raise ValueError("Invalid filename")

    ext = safe_name.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Extension not allowed: {ext}")

    # Generate unique ID
    unique_id = str(uuid4())
    unique_filename = f"{unique_id}.{ext}"

    return unique_filename, safe_name


def store_file_metadata(unique_filename: str, original_name: str, user_id: int):
    """Store file metadata in database."""
    # Would save to database in real app
    pass


@app.route("/upload", methods=["POST"])
def upload_document():
    """GOOD: Secure upload with multiple protections."""
    file = request.files.get("file")
    user_id = request.form.get("user_id", 0)

    if not file or file.filename == "":
        return jsonify({"error": "No file provided"}), 400

    try:
        # SANITIZER: Get safe filename
        unique_filename, original_name = get_safe_filename(file.filename)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    # Ensure upload directory exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Save with unique filename (not original)
    filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
    file.save(filepath)

    # Store metadata for later retrieval
    store_file_metadata(unique_filename, original_name, int(user_id))

    return jsonify({"status": "uploaded", "file_id": unique_filename.split(".")[0]})


@app.route("/download/<file_id>")
def download_file(file_id: str):
    """Serve file through application (not direct access)."""
    # SANITIZER: Validate file_id format (UUID)
    try:
        from uuid import UUID

        UUID(file_id)
    except ValueError:
        return jsonify({"error": "Invalid file ID"}), 400

    # Find file with this ID
    for filename in os.listdir(UPLOAD_FOLDER):
        if filename.startswith(file_id):
            return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

    return jsonify({"error": "File not found"}), 404


if __name__ == "__main__":
    app.run()
