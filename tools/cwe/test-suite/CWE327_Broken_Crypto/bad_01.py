"""CWE-327: Broken Crypto - BAD (MD5)"""

from Crypto.Hash import MD5


def hash_password(password: str) -> str:
    # BAD: MD5 is broken for password hashing
    h = MD5.new()  # SINK: weak algorithm
    h.update(password.encode())
    return h.hexdigest()
