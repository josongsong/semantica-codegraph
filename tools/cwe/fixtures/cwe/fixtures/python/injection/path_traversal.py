"""
Path Traversal Test Fixtures

CWE-22: Path Traversal
CVE-2019-11510: Pulse Secure Path Traversal
CVE-2021-41773: Apache HTTP Server Path Traversal
"""

import os
from pathlib import Path

# ==================================================
# VULNERABLE: Direct concatenation
# ==================================================


def path_traversal_vulnerable_1(filename: str) -> str:
    """
    ❌ CRITICAL: Direct path concatenation

    Real attack: filename = "../../../etc/passwd"
    Result: Reads /etc/passwd
    """
    # VULNERABLE: String concatenation
    file_path = f"/var/uploads/{filename}"

    with open(file_path) as f:  # SINK: open()
        return f.read()


def path_traversal_vulnerable_2(user_file: str):
    """
    ❌ CRITICAL: os.path.join still vulnerable

    Real attack: user_file = "/etc/passwd"
    Result: Absolute path overrides base
    """
    # VULNERABLE: Absolute path bypasses join
    file_path = os.path.join("/safe/dir", user_file)

    return open(file_path).read()  # SINK


def path_traversal_vulnerable_3(doc_id: str):
    """
    ❌ CRITICAL: Flask send_file

    CVE-2019-11510: Path traversal in file download
    """
    from flask import send_file

    # VULNERABLE
    file_path = f"/documents/{doc_id}.pdf"
    return send_file(file_path)  # SINK: send_file


def path_traversal_vulnerable_4(image_name: str):
    """
    ❌ CRITICAL: pathlib Path division
    """
    # VULNERABLE: Path division doesn't validate
    base = Path("/var/www/images")
    image_path = base / image_name

    return image_path.read_bytes()  # SINK: Path.read_bytes


def path_traversal_vulnerable_5(log_file: str):
    """
    ❌ CRITICAL: Multiple directory levels

    Real attack: log_file = "../../../../../../etc/shadow"
    """
    # VULNERABLE
    log_path = f"/var/log/app/{log_file}"

    with open(log_path) as f:  # SINK
        return f.readlines()


# ==================================================
# VULNERABLE: URL-encoded attacks
# ==================================================


def path_traversal_vulnerable_6(encoded_path: str):
    """
    ❌ CRITICAL: URL-encoded traversal

    Real attack: encoded_path = "..%2F..%2F..%2Fetc%2Fpasswd"
    Result: Decodes to ../../../etc/passwd
    """
    from urllib.parse import unquote

    # VULNERABLE: Decode then use
    decoded = unquote(encoded_path)
    file_path = f"/uploads/{decoded}"

    return open(file_path).read()  # SINK


# ==================================================
# SAFE: Path canonicalization (BEST PRACTICE)
# ==================================================


def path_traversal_safe_1_realpath(filename: str) -> str:
    """
    ✅ SECURE: os.path.realpath() validation
    """
    base_dir = "/var/uploads"

    # Construct path
    file_path = os.path.join(base_dir, filename)

    # SAFE: Canonicalize and validate
    real_path = os.path.realpath(file_path)

    if not real_path.startswith(base_dir):
        raise ValueError("Path traversal detected")

    with open(real_path) as f:
        return f.read()


def path_traversal_safe_2_abspath(user_file: str):
    """
    ✅ SECURE: os.path.abspath() validation
    """
    base_dir = "/safe/dir"

    file_path = os.path.join(base_dir, user_file)
    abs_path = os.path.abspath(file_path)

    # SAFE: Validate resolved path
    if not abs_path.startswith(os.path.abspath(base_dir)):
        raise ValueError("Invalid path")

    return open(abs_path).read()


def path_traversal_safe_3_pathlib_resolve(doc_id: str):
    """
    ✅ SECURE: pathlib Path.resolve()
    """
    base_dir = Path("/documents")

    # Construct path
    doc_path = base_dir / f"{doc_id}.pdf"

    # SAFE: Resolve and validate
    resolved = doc_path.resolve()

    if not resolved.is_relative_to(base_dir):
        raise ValueError("Path traversal attempt")

    return resolved.read_bytes()


def path_traversal_safe_4_is_relative_to(image_name: str):
    """
    ✅ SECURE: Python 3.9+ is_relative_to()
    """
    base = Path("/var/www/images")
    image_path = (base / image_name).resolve()

    # SAFE: Python 3.9+ method
    if not image_path.is_relative_to(base):
        raise ValueError("Invalid path")

    return image_path.read_bytes()


# ==================================================
# SAFE: Basename extraction
# ==================================================


def path_traversal_safe_5_basename(filename: str) -> str:
    """
    ✅ SECURE: Extract basename only

    Removes all directory components.
    """
    # SAFE: Only use filename part
    safe_name = os.path.basename(filename)

    file_path = f"/var/uploads/{safe_name}"

    with open(file_path) as f:
        return f.read()


def path_traversal_safe_6_pathlib_name(user_file: str):
    """
    ✅ SECURE: pathlib Path.name
    """
    # SAFE: Extract name component
    safe_name = Path(user_file).name

    file_path = Path("/safe/dir") / safe_name

    return file_path.read_text()


# ==================================================
# SAFE: Allowlist validation
# ==================================================


def path_traversal_safe_7_allowlist(doc_id: str):
    """
    ✅ SECURE: Allowlist of valid IDs
    """
    import re

    # SAFE: Only alphanumeric IDs
    if not re.match(r"^[a-zA-Z0-9_-]+$", doc_id):
        raise ValueError("Invalid document ID")

    file_path = f"/documents/{doc_id}.pdf"

    with open(file_path, "rb") as f:
        return f.read()


def path_traversal_safe_8_extension_check(filename: str):
    """
    ✅ SECURE: Extension validation
    """
    # Validate extension
    allowed_extensions = {".txt", ".pdf", ".jpg", ".png"}
    ext = os.path.splitext(filename)[1].lower()

    if ext not in allowed_extensions:
        raise ValueError("Invalid file type")

    # SAFE: Basename + extension check
    safe_name = os.path.basename(filename)
    file_path = f"/uploads/{safe_name}"

    return open(file_path, "rb").read()


# ==================================================
# SAFE: Chroot/jail pattern
# ==================================================


def path_traversal_safe_9_chroot_pattern(user_path: str):
    """
    ✅ SECURE: Chroot-style validation
    """
    import os.path

    base_dir = "/var/chroot/user_files"

    # Join and normalize
    full_path = os.path.normpath(os.path.join(base_dir, user_path))

    # SAFE: Ensure within jail
    if not full_path.startswith(base_dir + os.sep):
        raise ValueError("Path outside jail")

    return open(full_path).read()


# ==================================================
# SAFE: Flask secure_filename
# ==================================================


def path_traversal_safe_10_flask_secure(filename: str):
    """
    ✅ SECURE: Flask's secure_filename()
    """
    from werkzeug.utils import secure_filename

    # SAFE: Removes path components and dangerous chars
    safe_name = secure_filename(filename)

    file_path = f"/uploads/{safe_name}"

    with open(file_path, "rb") as f:
        return f.read()


# ==================================================
# EDGE CASE: Symlink attacks
# ==================================================


def path_traversal_edge_case_1_symlink():
    """
    ⚠️ WARNING: Symlink attack

    Even with path validation, symlinks can bypass checks.
    """
    # Check if path is symlink
    file_path = "/uploads/user_file.txt"

    if os.path.islink(file_path):
        raise ValueError("Symlinks not allowed")

    # Additional check: resolve and validate
    real_path = os.path.realpath(file_path)
    if not real_path.startswith("/uploads"):
        raise ValueError("Invalid path")

    return open(real_path).read()


# ==================================================
# Real-world patterns
# ==================================================


def path_traversal_safe_11_django_storage(filename: str):
    """
    ✅ SECURE: Django FileSystemStorage
    """
    from django.core.files.storage import FileSystemStorage

    # SAFE: Django handles path validation
    storage = FileSystemStorage(location="/media/uploads")

    if not storage.exists(filename):
        raise ValueError("File not found")

    with storage.open(filename) as f:
        return f.read()
