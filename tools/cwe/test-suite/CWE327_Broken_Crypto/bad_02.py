"""CWE-327: Broken Crypto - BAD (DES)"""

from Crypto.Cipher import DES


def encrypt_data(data: bytes, key: bytes) -> bytes:
    # BAD: DES is deprecated
    cipher = DES.new(key, DES.MODE_ECB)  # SINK: weak algorithm
    return cipher.encrypt(data)
