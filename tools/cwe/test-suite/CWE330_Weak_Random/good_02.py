"""
CWE-330: Use of Insufficiently Random Values - GOOD Example 02
Mitigation: Using os.urandom or SystemRandom
"""

import base64
import os
import random


def generate_api_key() -> str:
    """GOOD: Using os.urandom for API key."""
    # SOURCE: security context - API key
    random_bytes = os.urandom(24)  # SAFE: Secure random
    return f"api_{base64.urlsafe_b64encode(random_bytes).decode()}"


def generate_secure_id() -> str:
    """GOOD: Using SystemRandom for cryptographic randomness."""
    # SOURCE: security context
    secure_random = random.SystemRandom()  # SAFE: Cryptographically secure
    chars = "0123456789abcdef"
    return "".join(secure_random.choice(chars) for _ in range(32))
