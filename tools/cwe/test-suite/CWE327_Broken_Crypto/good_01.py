"""CWE-327: Broken Crypto - GOOD"""

import bcrypt


def hash_password(password: str) -> bytes:
    # GOOD: bcrypt with salt
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode(), salt)
