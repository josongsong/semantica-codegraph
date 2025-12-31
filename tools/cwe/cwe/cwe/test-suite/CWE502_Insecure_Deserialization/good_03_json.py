"""CWE-502: Insecure Deserialization - GOOD (JSON only)"""

import json

from flask import request


def load_object():
    data = request.get_data()  # SOURCE

    # GOOD: json.loads only handles data, no code execution
    obj = json.loads(data)  # SAFE: standard JSON
    return str(obj)
