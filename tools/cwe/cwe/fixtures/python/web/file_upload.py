"""
Unrestricted File Upload Test Fixtures

CWE-434: Unrestricted Upload of File with Dangerous Type
CVE-2018-19518: PHP file upload RCE
CVE-2020-9484: Tomcat file upload deserialization
"""

import mimetypes
import os
from pathlib import Path

from werkzeug.utils import secure_filename

# ==================================================
# VULNERABLE: No validation
# ==================================================


def file_upload_vulnerable_1(uploaded_file):
    """
    ❌ CRITICAL: No file type validation

    Real attack: Upload shell.php, access via web
    Result: Remote code execution
    """
    # VULNERABLE: No validation
    filename = uploaded_file.filename

    # SINK: Save without checks
    uploaded_file.save(f"/var/www/uploads/{filename}")

    return "File uploaded"


def file_upload_vulnerable_2(file_data, filename: str):
    """
    ❌ CRITICAL: Client-side extension check only
    """
    # VULNERABLE: Extension can be spoofed
    if not filename.endswith(".jpg"):
        return "Only JPG allowed"

    # SINK: Attacker can upload shell.php.jpg
    with open(f"/uploads/{filename}", "wb") as f:
        f.write(file_data)


def file_upload_vulnerable_3(uploaded_file):
    """
    ❌ CRITICAL: Path traversal in filename

    Real attack: filename = "../../var/www/html/shell.php"
    """
    # VULNERABLE: No path sanitization
    filename = uploaded_file.filename

    # SINK: Path traversal
    uploaded_file.save(f"/uploads/{filename}")


# ==================================================
# VULNERABLE: Weak validation
# ==================================================


def file_upload_vulnerable_4(uploaded_file):
    """
    ❌ HIGH: Extension check bypass

    Real attack: shell.php.jpg (double extension)
    """
    filename = uploaded_file.filename

    # VULNERABLE: Only checks if .jpg exists
    if ".jpg" in filename:
        # SINK: shell.php.jpg passes
        uploaded_file.save(f"/uploads/{filename}")
        return "Uploaded"

    return "Invalid file type"


def file_upload_vulnerable_5(uploaded_file):
    """
    ❌ HIGH: MIME type spoofing

    Real attack: Set Content-Type: image/jpeg for PHP file
    """
    # VULNERABLE: MIME type from client
    if uploaded_file.content_type != "image/jpeg":
        return "Only JPEG allowed"

    # SINK: MIME type can be spoofed
    uploaded_file.save(f"/uploads/{uploaded_file.filename}")


def file_upload_vulnerable_6(uploaded_file):
    """
    ❌ HIGH: Case sensitivity bypass

    Real attack: shell.PHP (uppercase)
    """
    filename = uploaded_file.filename

    # VULNERABLE: Case-sensitive check
    if filename.endswith(".php"):
        return "PHP not allowed"

    # SINK: .PHP, .pHp bypass
    uploaded_file.save(f"/uploads/{filename}")


# ==================================================
# SAFE: Extension allowlist (BEST PRACTICE)
# ==================================================


def file_upload_safe_1_allowlist(uploaded_file):
    """
    ✅ SECURE: Extension allowlist
    """
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".pdf"}

    filename = uploaded_file.filename
    ext = Path(filename).suffix.lower()

    # SAFE: Allowlist check
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("File type not allowed")

    # Sanitize filename
    safe_name = secure_filename(filename)

    uploaded_file.save(f"/uploads/{safe_name}")

    return "File uploaded"


def file_upload_safe_2_secure_filename(uploaded_file):
    """
    ✅ SECURE: werkzeug.secure_filename()
    """
    from werkzeug.utils import secure_filename

    # SAFE: Removes path components and dangerous chars
    safe_name = secure_filename(uploaded_file.filename)

    # Validate extension
    ext = Path(safe_name).suffix.lower()
    if ext not in {".jpg", ".png", ".pdf"}:
        raise ValueError("Invalid file type")

    uploaded_file.save(f"/uploads/{safe_name}")


# ==================================================
# SAFE: Content validation
# ==================================================


def file_upload_safe_3_magic_bytes(uploaded_file):
    """
    ✅ SECURE: Magic bytes validation
    """
    import imghdr

    # Read file content
    file_data = uploaded_file.read()

    # SAFE: Check actual file type (magic bytes)
    file_type = imghdr.what(None, h=file_data)

    if file_type not in ["jpeg", "png", "gif"]:
        raise ValueError("Invalid image file")

    # Generate safe filename
    import uuid

    safe_name = f"{uuid.uuid4()}.{file_type}"

    with open(f"/uploads/{safe_name}", "wb") as f:
        f.write(file_data)


def file_upload_safe_4_pillow_validation(uploaded_file):
    """
    ✅ SECURE: PIL/Pillow image validation
    """
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow not installed. Install with: pip install codegraph[cwe]")

    try:
        # SAFE: Pillow validates image format
        img = Image.open(uploaded_file)
        img.verify()

        # Re-open after verify
        uploaded_file.seek(0)
        img = Image.open(uploaded_file)

        # Validate dimensions
        if img.width > 5000 or img.height > 5000:
            raise ValueError("Image too large")

        # Save with sanitized name
        import uuid

        safe_name = f"{uuid.uuid4()}.{img.format.lower()}"
        img.save(f"/uploads/{safe_name}")

    except Exception as e:
        raise ValueError("Invalid image file")


# ==================================================
# SAFE: Content-Type validation
# ==================================================


def file_upload_safe_5_mime_check(uploaded_file):
    """
    ✅ SECURE: Server-side MIME type detection
    """
    try:
        import magic
    except ImportError:
        raise ImportError("python-magic not installed. Install with: pip install codegraph[cwe]")

    # Read file
    file_data = uploaded_file.read()

    # SAFE: Detect MIME type from content
    mime = magic.from_buffer(file_data, mime=True)

    ALLOWED_MIMES = {"image/jpeg", "image/png", "image/gif", "application/pdf"}

    if mime not in ALLOWED_MIMES:
        raise ValueError("File type not allowed")

    # Save with UUID
    import uuid

    ext = mimetypes.guess_extension(mime)
    safe_name = f"{uuid.uuid4()}{ext}"

    with open(f"/uploads/{safe_name}", "wb") as f:
        f.write(file_data)


# ==================================================
# SAFE: Separate storage
# ==================================================


def file_upload_safe_6_separate_storage(uploaded_file):
    """
    ✅ SECURE: Store outside web root
    """
    # SAFE: Store outside web-accessible directory
    UPLOAD_DIR = "/var/data/uploads"  # NOT /var/www/

    # Validate and sanitize
    safe_name = secure_filename(uploaded_file.filename)
    ext = Path(safe_name).suffix.lower()

    if ext not in {".jpg", ".png", ".pdf"}:
        raise ValueError("Invalid file type")

    # Generate unique name
    import uuid

    unique_name = f"{uuid.uuid4()}{ext}"

    file_path = os.path.join(UPLOAD_DIR, unique_name)
    uploaded_file.save(file_path)

    return unique_name


# ==================================================
# SAFE: Virus scanning
# ==================================================


def file_upload_safe_7_virus_scan(uploaded_file):
    """
    ✅ SECURE: Virus scanning (defense in depth)
    """
    try:
        import clamd
    except ImportError:
        raise ImportError("clamd not installed. Install with: pip install codegraph[cwe]")

    # Read file
    file_data = uploaded_file.read()

    # SAFE: Scan for malware
    cd = clamd.ClamdUnixSocket()
    scan_result = cd.scan_stream(file_data)

    if scan_result and scan_result.get("stream") != ("OK", None):
        raise ValueError("Malware detected")

    # Continue with other validations
    return file_upload_safe_3_magic_bytes(uploaded_file)


# ==================================================
# SAFE: Size limits
# ==================================================


def file_upload_safe_8_size_limit(uploaded_file):
    """
    ✅ SECURE: File size validation
    """
    MAX_SIZE = 5 * 1024 * 1024  # 5MB

    # Check size
    uploaded_file.seek(0, os.SEEK_END)
    size = uploaded_file.tell()
    uploaded_file.seek(0)

    if size > MAX_SIZE:
        raise ValueError("File too large")

    # Continue with validation
    return file_upload_safe_1_allowlist(uploaded_file)


# ==================================================
# SAFE: Django FileField
# ==================================================


def file_upload_safe_9_django():
    """
    ✅ SECURE: Django FileField with validators
    """
    from django.core.validators import FileExtensionValidator
    from django.db import models

    class Document(models.Model):
        # SAFE: Django validates extension
        file = models.FileField(
            upload_to="uploads/", validators=[FileExtensionValidator(allowed_extensions=["pdf", "jpg", "png"])]
        )


# ==================================================
# SAFE: Flask-Uploads
# ==================================================


def file_upload_safe_10_flask_uploads():
    """
    ✅ SECURE: Flask-Uploads extension
    """
    from flask import Flask
    from flask_uploads import IMAGES, UploadSet, configure_uploads

    app = Flask(__name__)

    # SAFE: Flask-Uploads handles validation
    photos = UploadSet("photos", IMAGES)
    configure_uploads(app, photos)

    def upload_photo(uploaded_file):
        # SAFE: Only allows image types
        filename = photos.save(uploaded_file)
        return filename


# ==================================================
# SAFE: Complete validation pipeline
# ==================================================


def file_upload_safe_11_complete(uploaded_file):
    """
    ✅ SECURE: Complete validation pipeline

    Defense in depth: Multiple layers of validation
    """
    import uuid

    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow not installed. Install with: pip install codegraph[cwe]")

    # 1. Size check
    MAX_SIZE = 5 * 1024 * 1024
    uploaded_file.seek(0, os.SEEK_END)
    if uploaded_file.tell() > MAX_SIZE:
        raise ValueError("File too large")
    uploaded_file.seek(0)

    # 2. Extension allowlist
    filename = secure_filename(uploaded_file.filename)
    ext = Path(filename).suffix.lower()
    ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif"}

    if ext not in ALLOWED_EXTS:
        raise ValueError("File type not allowed")

    # 3. Magic bytes validation
    file_data = uploaded_file.read()
    import imghdr

    file_type = imghdr.what(None, h=file_data)

    if file_type not in ["jpeg", "png", "gif"]:
        raise ValueError("Invalid image")

    # 4. Image validation with Pillow
    from io import BytesIO

    img = Image.open(BytesIO(file_data))
    img.verify()

    # 5. Dimension check
    img = Image.open(BytesIO(file_data))
    if img.width > 5000 or img.height > 5000:
        raise ValueError("Image too large")

    # 6. Generate unique filename
    unique_name = f"{uuid.uuid4()}.{file_type}"

    # 7. Save outside web root
    UPLOAD_DIR = "/var/data/uploads"
    file_path = os.path.join(UPLOAD_DIR, unique_name)

    with open(file_path, "wb") as f:
        f.write(file_data)

    # 8. Set restrictive permissions
    os.chmod(file_path, 0o644)

    return unique_name
