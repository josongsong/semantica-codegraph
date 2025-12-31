"""CWE-338: Weak PRNG - BAD"""

import random


def generate_token():
    seed = input("Seed: ")
    # BAD: predictable seed
    random.seed(seed)
    token = random.randint(1000, 9999)
    return token
