"""CWE-502: Insecure Deserialization - BAD"""

import pickle

from flask import request


def load_session():
    data = request.get_data()  # SOURCE: request body

    # BAD: pickle.loads on untrusted data
    session = pickle.loads(data)  # SINK: RCE via deserialization
    return session
