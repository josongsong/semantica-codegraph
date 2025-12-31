"""CWE-502: Insecure Deserialization - BAD (jsonpickle)"""

import jsonpickle
from flask import request


def load_object():
    data = request.get_data()  # SOURCE

    # BAD: jsonpickle can execute arbitrary code
    obj = jsonpickle.decode(data)  # SINK: insecure deserialization
    return str(obj)
