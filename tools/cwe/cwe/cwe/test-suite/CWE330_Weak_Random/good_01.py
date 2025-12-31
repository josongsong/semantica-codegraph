"""
CWE-330: Use of Insufficiently Random Values - GOOD Example 01
Mitigation: Using secrets module for security tokens
"""

import secrets


def generate_session_token() -> str:
    """GOOD: secrets module is cryptographically secure."""
    # SOURCE: security context - session token
    return secrets.token_urlsafe(32)  # SAFE: Secure random


def generate_password_reset_token() -> str:
    """GOOD: Using secrets for password reset token."""
    # SOURCE: security context - password reset
    return secrets.token_hex(20)  # SAFE: Secure random
