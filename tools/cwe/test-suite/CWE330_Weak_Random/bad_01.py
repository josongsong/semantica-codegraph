"""
CWE-330: Use of Insufficiently Random Values - BAD Example 01
Vulnerability: Using random module for security tokens
"""

import random
import string


def generate_session_token() -> str:
    """BAD: random module is not cryptographically secure."""
    # SOURCE: security context - session token
    chars = string.ascii_letters + string.digits
    token = "".join(random.choice(chars) for _ in range(32))  # SINK: Weak random
    return token


def generate_password_reset_token() -> str:
    """BAD: Predictable random for password reset."""
    # SOURCE: security context - password reset
    return "".join(random.choices(string.hexdigits, k=40))  # SINK: Weak random
