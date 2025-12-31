"""
CWE-330: Use of Insufficiently Random Values - BAD Example 02
Vulnerability: Using time-based or sequential values for tokens
"""

import random
import time


def generate_api_key() -> str:
    """BAD: Time-based token is predictable."""
    # SOURCE: security context - API key
    timestamp = str(int(time.time()))  # SINK: Predictable time-based
    return f"api_{timestamp}_{random.randint(1000, 9999)}"  # SINK: Weak random


def generate_order_id() -> str:
    """BAD: Sequential with weak randomness."""
    # SOURCE: security context
    base = int(time.time() * 1000)  # SINK: Time-based
    suffix = random.randint(0, 999)  # SINK: Weak random
    return f"ORD-{base}-{suffix}"
