"""
CWE-328: Use of Weak Hash - GOOD Example 01
Mitigation: Using bcrypt for password hashing
"""

import bcrypt


def store_password(username: str, password: str) -> dict:
    """GOOD: bcrypt is designed for password hashing with adaptive cost."""
    # SOURCE: password from user
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode(), salt)  # SAFE: Strong hash
    return {"username": username, "password_hash": password_hash.decode()}


def verify_password(stored_hash: str, password: str) -> bool:
    """GOOD: Using bcrypt for password verification."""
    # SOURCE: password input
    return bcrypt.checkpw(password.encode(), stored_hash.encode())  # SAFE
