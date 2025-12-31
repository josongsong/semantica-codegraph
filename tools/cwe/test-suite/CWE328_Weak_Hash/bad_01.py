"""
CWE-328: Use of Weak Hash - BAD Example 01
Vulnerability: Using MD5 to hash passwords
"""

import hashlib


def store_password(username: str, password: str) -> dict:
    """BAD: MD5 is cryptographically broken for password storage."""
    # SOURCE: password from user
    password_hash = hashlib.md5(password.encode()).hexdigest()  # SINK: Weak hash
    return {"username": username, "password_hash": password_hash}


def verify_password(stored_hash: str, password: str) -> bool:
    """BAD: Verifying with weak MD5 hash."""
    # SOURCE: password input
    input_hash = hashlib.md5(password.encode()).hexdigest()  # SINK: Weak hash
    return input_hash == stored_hash
