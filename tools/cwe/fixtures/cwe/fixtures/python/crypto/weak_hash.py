"""
Weak Hash Algorithm Fixtures

CVE-2004-2761: MD5 collision attacks
CVE-2020-22218: SHA1 deprecation
"""

import hashlib

from Crypto.Hash import MD5

# ==================================================
# VULNERABLE: MD5 usage (CVE-2004-2761)
# ==================================================


def md5_password_hash_vulnerable(password: str) -> str:
    """
    ❌ CRITICAL: Using MD5 for password hashing

    CVE-2004-2761: MD5 is broken due to collision attacks.
    Attackers can create two different inputs with same hash.
    """
    return hashlib.md5(password.encode()).hexdigest()


def md5_file_integrity_vulnerable(file_content: bytes) -> str:
    """
    ❌ CRITICAL: Using MD5 for file integrity

    MD5 collisions allow attackers to create malicious files
    with the same hash as legitimate ones.
    """
    md5_hash = hashlib.md5()
    md5_hash.update(file_content)
    return md5_hash.hexdigest()


def md5_with_pycrypto_vulnerable(data: str) -> str:
    """
    ❌ CRITICAL: Using MD5 from PyCrypto
    """
    h = MD5.new()
    h.update(data.encode())
    return h.hexdigest()


# ==================================================
# VULNERABLE: SHA1 usage (CVE-2020-22218)
# ==================================================


def sha1_signature_vulnerable(message: str, key: str) -> str:
    """
    ❌ HIGH: Using SHA1 for digital signatures

    CVE-2020-22218: SHA1 is deprecated and considered weak.
    SHAttered attack demonstrated practical SHA1 collisions.
    """
    return hashlib.sha1((message + key).encode()).hexdigest()


def sha1_git_like_hash_vulnerable(content: bytes) -> str:
    """
    ❌ HIGH: Using SHA1 (similar to old Git)

    Git migrated away from SHA1 due to security concerns.
    """
    sha1_hash = hashlib.sha1()
    sha1_hash.update(content)
    return sha1_hash.hexdigest()


# ==================================================
# SECURE: SHA256+ usage
# ==================================================


def sha256_password_hash_secure(password: str, salt: bytes) -> str:
    """
    ✅ SECURE: Using SHA256 with salt

    Note: For passwords, use specialized functions like
    bcrypt, scrypt, or Argon2. This is just better than MD5.
    """
    return hashlib.sha256(salt + password.encode()).hexdigest()


def sha3_file_integrity_secure(file_content: bytes) -> str:
    """
    ✅ SECURE: Using SHA3-256 for file integrity

    SHA3 is the latest standard with no known vulnerabilities.
    """
    return hashlib.sha3_256(file_content).hexdigest()


def blake2_fast_hash_secure(data: bytes) -> str:
    """
    ✅ SECURE: Using BLAKE2b for fast hashing

    BLAKE2 is faster than SHA-2 and more secure than MD5.
    """
    return hashlib.blake2b(data).hexdigest()
