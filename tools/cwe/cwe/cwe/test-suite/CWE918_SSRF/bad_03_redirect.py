"""CWE-918: SSRF - BAD (Following redirects)"""

import requests
from flask import request


def fetch_url():
    url = request.args.get("url")  # SOURCE

    # BAD: Following redirects can lead to internal resources
    response = requests.get(url, allow_redirects=True)
    return response.text  # SINK: SSRF
