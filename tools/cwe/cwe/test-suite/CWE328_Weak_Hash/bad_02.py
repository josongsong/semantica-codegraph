"""
CWE-328: Use of Weak Hash - BAD Example 02
Vulnerability: Using SHA1 for password hashing (also weak)
"""

import hashlib


def hash_api_key(api_key: str) -> str:
    """BAD: SHA1 is deprecated for security-sensitive applications."""
    # SOURCE: api_key
    return hashlib.sha1(api_key.encode()).hexdigest()  # SINK: Weak SHA1


def create_token(secret: str, data: str) -> str:
    """BAD: Using SHA1 for token generation."""
    # SOURCE: secret
    combined = f"{secret}:{data}"
    return hashlib.sha1(combined.encode()).hexdigest()  # SINK: Weak SHA1
