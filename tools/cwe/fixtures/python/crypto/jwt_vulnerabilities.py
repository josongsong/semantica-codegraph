"""
JWT Vulnerability Fixtures

CVE-2015-9235: JWT none algorithm bypass
CVE-2018-0114: JWT key confusion attack
CVE-2019-7644: JWT weak secret key
"""

import datetime

import jwt

# ==================================================
# VULNERABLE: verify=False (CVE-2015-9235)
# ==================================================


def decode_jwt_no_verify_vulnerable(token: str) -> dict:
    """
    ❌ CRITICAL: Decoding JWT without verification

    CVE-2015-9235: Disabling signature verification allows
    attackers to forge tokens with arbitrary claims.
    """
    payload = jwt.decode(token, options={"verify_signature": False})
    return payload


def decode_jwt_verify_false_vulnerable(token: str, secret: str) -> dict:
    """
    ❌ CRITICAL: verify=False bypasses all security
    """
    payload = jwt.decode(token, secret, algorithms=["HS256"], verify=False)
    return payload


# ==================================================
# VULNERABLE: 'none' algorithm (CVE-2015-9235)
# ==================================================


def encode_jwt_none_algorithm_vulnerable(user_id: int) -> str:
    """
    ❌ CRITICAL: Using 'none' algorithm

    'none' algorithm means no signature. Anyone can create tokens!
    """
    payload = {"user_id": user_id, "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)}
    token = jwt.encode(payload, None, algorithm="none")
    return token


def decode_jwt_allow_none_vulnerable(token: str) -> dict:
    """
    ❌ CRITICAL: Allowing 'none' algorithm in decode

    Attackers can change algorithm to 'none' and remove signature.
    """
    payload = jwt.decode(token, algorithms=["HS256", "none"])
    return payload


# ==================================================
# VULNERABLE: Weak secret key (CVE-2019-7644)
# ==================================================


def encode_jwt_weak_secret_vulnerable(user_id: int) -> str:
    """
    ❌ HIGH: Using weak secret key

    CVE-2019-7644: Weak secrets can be brute-forced.
    Common secrets like 'secret', '123456' are in wordlists.
    """
    payload = {"user_id": user_id, "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)}
    token = jwt.encode(payload, "secret", algorithm="HS256")  # Weak!
    return token


def decode_jwt_weak_secret_vulnerable(token: str) -> dict:
    """
    ❌ HIGH: Using short/weak secret
    """
    payload = jwt.decode(token, "12345", algorithms=["HS256"])
    return payload


# ==================================================
# VULNERABLE: Algorithm confusion (CVE-2018-0114)
# ==================================================


def decode_jwt_algorithm_confusion_vulnerable(token: str, public_key: str) -> dict:
    """
    ❌ CRITICAL: Not specifying allowed algorithms

    CVE-2018-0114: Attackers can change RS256 (public key) to
    HS256 (symmetric) and sign with public key as secret.
    """
    # Missing 'algorithms' parameter!
    payload = jwt.decode(token, public_key)
    return payload


# ==================================================
# SECURE: Proper JWT handling
# ==================================================


def encode_jwt_secure(user_id: int, secret_key: str) -> str:
    """
    ✅ SECURE: Strong secret + explicit algorithm

    Best practices:
    - Secret key at least 256 bits (32 bytes)
    - Explicit algorithm specification
    - Short expiration time
    """
    payload = {
        "user_id": user_id,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=15),
        "iat": datetime.datetime.utcnow(),
    }
    token = jwt.encode(payload, secret_key, algorithm="HS256")
    return token


def decode_jwt_secure(token: str, secret_key: str) -> dict:
    """
    ✅ SECURE: Verification enabled + algorithm whitelist
    """
    payload = jwt.decode(
        token,
        secret_key,
        algorithms=["HS256"],  # Explicit whitelist
        options={"verify_signature": True},  # Explicitly enabled
    )
    return payload


def encode_jwt_with_rsa_secure(user_id: int, private_key: str) -> str:
    """
    ✅ SECURE: Using RS256 with private key

    RS256 uses asymmetric keys, more secure than HS256.
    """
    payload = {"user_id": user_id, "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=15)}
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token


def decode_jwt_with_rsa_secure(token: str, public_key: str) -> dict:
    """
    ✅ SECURE: RS256 verification with public key
    """
    payload = jwt.decode(token, public_key, algorithms=["RS256"])  # Only allow RS256, prevent downgrade
    return payload


# ==================================================
# Helper: Generate strong secret
# ==================================================


def generate_jwt_secret_secure() -> str:
    """
    ✅ SECURE: Generating strong random secret
    """
    import secrets

    return secrets.token_urlsafe(32)  # 256 bits
