"""
CWE-328: Use of Weak Hash - GOOD Example 02
Mitigation: Using SHA-256 or stronger for non-password hashing
"""

import hashlib
import hmac


def hash_data_integrity(data: str, key: str) -> str:
    """GOOD: SHA-256 for data integrity verification."""
    # SOURCE: data
    return hashlib.sha256(data.encode()).hexdigest()  # SAFE: SHA-256


def create_secure_token(secret: str, data: str) -> str:
    """GOOD: Using HMAC-SHA256 for token generation."""
    # SOURCE: secret
    return hmac.new(secret.encode(), data.encode(), hashlib.sha256).hexdigest()  # SAFE: HMAC-SHA256
