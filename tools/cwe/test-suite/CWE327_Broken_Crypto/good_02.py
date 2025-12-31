"""CWE-327: Broken Crypto - GOOD (AES-GCM)"""

from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes


def encrypt_data(data: bytes, key: bytes) -> tuple[bytes, bytes, bytes]:
    # GOOD: AES-GCM with random nonce
    nonce = get_random_bytes(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(data)
    return nonce, ciphertext, tag
