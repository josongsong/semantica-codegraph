"""CodeQL Scenario: Security Patterns and Vulnerabilities"""

import hashlib
import pickle
import secrets


# Insecure deserialization
def insecure_pickle(data: bytes):
    """Insecure deserialization - VULNERABLE"""
    # VULNERABLE: Arbitrary code execution
    return pickle.loads(data)


# Weak cryptography
def weak_hash(password: str) -> str:
    """Weak hashing algorithm - VULNERABLE"""
    # VULNERABLE: MD5 is cryptographically broken
    return hashlib.md5(password.encode()).hexdigest()


def weak_random():
    """Weak random number generation - VULNERABLE"""
    import random

    # VULNERABLE: Not cryptographically secure
    return random.randint(1000, 9999)


# Information exposure
def expose_sensitive_info(user):
    """Information exposure in error - VULNERABLE"""
    try:
        process_user(user)
    except Exception as e:
        # VULNERABLE: Exposing stack trace
        print(f"Error processing user {user}: {str(e)}")
        raise


def process_user(user):
    """Simulated user processing"""
    raise ValueError(f"Database error: Invalid user {user}")


# SSRF (Server-Side Request Forgery)
def ssrf_vulnerable(url: str):
    """SSRF vulnerability - VULNERABLE"""
    import requests

    # VULNERABLE: No URL validation
    response = requests.get(url)
    return response.text


# Hardcoded credentials
class DatabaseConfig:
    """Hardcoded credentials - VULNERABLE"""

    # VULNERABLE: Hardcoded password
    DB_PASSWORD = "admin123"
    API_KEY = "sk_test_abc123"
    SECRET_TOKEN = "secret_token_12345"


# Safe versions
def secure_hash(password: str, salt: bytes = None) -> tuple[str, bytes]:
    """Secure password hashing"""
    if salt is None:
        salt = secrets.token_bytes(32)

    # SAFE: Use strong algorithm with salt
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
    return key.hex(), salt


def secure_random() -> int:
    """Cryptographically secure random"""
    # SAFE: Use secrets module
    return secrets.randbelow(10000)


def ssrf_safe(url: str):
    """SSRF with validation - SAFE"""
    from urllib.parse import urlparse

    import requests

    # SAFE: Validate URL
    parsed = urlparse(url)
    allowed_hosts = ["api.example.com", "trusted.com"]

    if parsed.hostname not in allowed_hosts:
        raise ValueError("Untrusted host")

    response = requests.get(url, timeout=5)
    return response.text


# XSS (Cross-Site Scripting)
def xss_vulnerable(user_input: str) -> str:
    """XSS vulnerability in HTML generation"""
    # VULNERABLE: No escaping
    return f"<div>Hello {user_input}</div>"


def xss_safe(user_input: str) -> str:
    """XSS safe with escaping"""
    import html

    # SAFE: Proper escaping
    escaped = html.escape(user_input)
    return f"<div>Hello {escaped}</div>"


# Race condition
class RaceConditionExample:
    """Race condition in counter - VULNERABLE"""

    def __init__(self):
        self.counter = 0

    def increment(self):
        """Not thread-safe - VULNERABLE"""
        temp = self.counter
        temp += 1
        self.counter = temp


# Safe version with lock
from threading import Lock


class ThreadSafeCounter:
    """Thread-safe counter - SAFE"""

    def __init__(self):
        self.counter = 0
        self.lock = Lock()

    def increment(self):
        """Thread-safe increment - SAFE"""
        with self.lock:
            self.counter += 1
