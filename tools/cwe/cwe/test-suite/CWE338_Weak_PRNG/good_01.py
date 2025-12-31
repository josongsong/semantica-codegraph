"""CWE-338: Weak PRNG - GOOD"""

import secrets


def generate_token_safe():
    # GOOD: cryptographically secure
    token = secrets.randbelow(10000)
    return token
