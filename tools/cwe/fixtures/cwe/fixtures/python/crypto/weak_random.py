"""
Weak Random Number Generator Fixtures

CVE-2019-16785: Predictable session tokens
CVE-2018-1000117: Weak PRNG in cryptographic operations
"""

import os
import random
import secrets

# ==================================================
# VULNERABLE: random module in security contexts
# ==================================================


def generate_session_token_vulnerable() -> str:
    """
    ❌ HIGH: Using random.random() for session tokens

    CVE-2019-16785: Predictable session tokens allow session hijacking.
    random.random() uses Mersenne Twister which is predictable.
    """
    token = str(random.random())
    return token.replace("0.", "")


def generate_api_key_vulnerable() -> str:
    """
    ❌ HIGH: Using random.randint() for API keys

    Predictable PRNG allows attackers to guess API keys.
    """
    return "".join([str(random.randint(0, 9)) for _ in range(32)])


def generate_csrf_token_vulnerable() -> str:
    """
    ❌ HIGH: Using random.choice() for CSRF tokens

    CVE-2018-1000117: Weak PRNG in security-critical operations.
    """
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join([random.choice(chars) for _ in range(32)])


def generate_password_reset_token_vulnerable(user_id: int) -> str:
    """
    ❌ HIGH: Predictable password reset tokens

    Attackers can predict tokens and hijack accounts.
    """
    random.seed(user_id)  # Even worse: seeded with user_id!
    return str(random.randrange(100000, 999999))


# ==================================================
# ACCEPTABLE: random module for non-security purposes
# ==================================================


def shuffle_playlist(songs: list) -> list:
    """
    ✅ ACCEPTABLE: Using random for non-security purposes

    Shuffling a playlist doesn't require cryptographic randomness.
    """
    shuffled = songs.copy()
    random.shuffle(shuffled)
    return shuffled


def pick_random_color() -> str:
    """
    ✅ ACCEPTABLE: Random choice for UI/UX
    """
    colors = ["red", "blue", "green", "yellow"]
    return random.choice(colors)


# ==================================================
# SECURE: secrets module for security
# ==================================================


def generate_session_token_secure() -> str:
    """
    ✅ SECURE: Using secrets.token_hex()

    secrets module uses OS-provided CSPRNG (cryptographically secure).
    """
    return secrets.token_hex(32)


def generate_api_key_secure() -> str:
    """
    ✅ SECURE: Using secrets.token_urlsafe()

    URL-safe tokens suitable for API keys.
    """
    return secrets.token_urlsafe(32)


def generate_csrf_token_secure() -> str:
    """
    ✅ SECURE: Using os.urandom()

    Direct access to OS random source.
    """
    return os.urandom(32).hex()


def generate_password_reset_token_secure() -> str:
    """
    ✅ SECURE: Using secrets.token_bytes()
    """
    return secrets.token_bytes(32).hex()
