"""CWE-918: SSRF - BAD"""

import requests
from flask import request


def fetch_url():
    url = request.args.get("url")  # SOURCE: user input

    # BAD: Unvalidated URL fetch
    response = requests.get(url)  # SINK: SSRF
    return response.text
