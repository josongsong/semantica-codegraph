"""CWE-502: Insecure Deserialization - GOOD"""

import json

from flask import request


def load_session():
    data = request.get_data()

    # GOOD: JSON instead of pickle
    session = json.loads(data)
    return session
