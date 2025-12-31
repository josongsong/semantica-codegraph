"""CWE-918: SSRF - GOOD"""

from urllib.parse import urlparse

import requests
from flask import abort, request

ALLOWED_HOSTS = {"api.example.com", "cdn.example.com"}


def fetch_url():
    url = request.args.get("url")

    # GOOD: Validate URL host against allowlist
    parsed = urlparse(url)
    if parsed.hostname not in ALLOWED_HOSTS:
        abort(403, "Host not allowed")

    response = requests.get(url)
    return response.text
