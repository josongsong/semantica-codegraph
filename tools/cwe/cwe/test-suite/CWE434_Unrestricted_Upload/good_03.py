"""CWE-434: Unrestricted Upload of File with Dangerous Type - GOOD

Safe: Content scanning and image processing.
"""

import io
import os
from uuid import uuid4

import magic
from flask import Flask, jsonify, request
from PIL import Image
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = "/var/uploads/images"
MAX_IMAGE_SIZE = (1920, 1080)  # Max dimensions
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def validate_image_content(file_content: bytes) -> bool:
    """Validate that file is actually an image."""
    try:
        # SANITIZER: Try to open as image
        img = Image.open(io.BytesIO(file_content))
        img.verify()  # Verify it's a valid image
        return True
    except Exception:
        return False


def process_and_sanitize_image(file_content: bytes) -> bytes:
    """Re-encode image to strip any embedded code."""
    # SANITIZER: Re-encode the image
    # This removes any embedded scripts or malicious data
    img = Image.open(io.BytesIO(file_content))

    # Convert to RGB if necessary (removes alpha channel exploits)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Resize if too large
    if img.size[0] > MAX_IMAGE_SIZE[0] or img.size[1] > MAX_IMAGE_SIZE[1]:
        img.thumbnail(MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)

    # Re-encode to new bytes
    output = io.BytesIO()
    img.save(output, format="JPEG", quality=85)
    return output.getvalue()


def scan_for_malware(file_content: bytes) -> bool:
    """Scan file for malware signatures."""
    # SANITIZER: Check for common malware patterns
    dangerous_patterns = [
        b"<?php",
        b"<%",
        b"<script",
        b"#!/",
        b"eval(",
        b"exec(",
        b"import os",
        b"import subprocess",
    ]

    for pattern in dangerous_patterns:
        if pattern in file_content.lower() if isinstance(file_content, str) else pattern in file_content:
            return False  # Malware detected

    return True  # Clean


@app.route("/upload/image", methods=["POST"])
def upload_image():
    """GOOD: Full image validation and sanitization."""
    file = request.files.get("file")

    if not file or file.filename == "":
        return jsonify({"error": "No file provided"}), 400

    # Read content
    file_content = file.read()

    # SANITIZER 1: Size check
    if len(file_content) > MAX_FILE_SIZE:
        return jsonify({"error": "File too large"}), 400

    # SANITIZER 2: MIME type from content
    mime_type = magic.from_buffer(file_content, mime=True)
    if not mime_type.startswith("image/"):
        return jsonify({"error": "Not an image file"}), 400

    # SANITIZER 3: Malware scan
    if not scan_for_malware(file_content):
        return jsonify({"error": "Potentially malicious content detected"}), 400

    # SANITIZER 4: Validate it's a real image
    if not validate_image_content(file_content):
        return jsonify({"error": "Invalid image content"}), 400

    # SANITIZER 5: Re-encode to sanitize
    try:
        sanitized_content = process_and_sanitize_image(file_content)
    except Exception as e:
        return jsonify({"error": f"Image processing failed: {str(e)}"}), 400

    # SANITIZER 6: Generate unique filename
    unique_filename = f"{uuid4()}.jpg"

    # Save sanitized image
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filepath = os.path.join(UPLOAD_FOLDER, unique_filename)

    with open(filepath, "wb") as f:
        f.write(sanitized_content)

    return jsonify({"status": "uploaded", "filename": unique_filename, "size": len(sanitized_content)})


if __name__ == "__main__":
    app.run()
