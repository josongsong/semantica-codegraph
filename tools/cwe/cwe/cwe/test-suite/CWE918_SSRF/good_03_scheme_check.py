"""CWE-918: SSRF - GOOD (Scheme and host validation)"""

from urllib.parse import urlparse

import requests
from flask import abort, request

ALLOWED_HOSTS = {"api.example.com", "cdn.example.com"}


def fetch_url():
    url = request.args.get("url")  # SOURCE

    parsed = urlparse(url)

    # GOOD: Validate scheme and host
    if parsed.scheme not in ("http", "https"):
        abort(400, "Invalid scheme")

    if parsed.hostname not in ALLOWED_HOSTS:
        abort(403, "Host not allowed")

    response = requests.get(url, allow_redirects=False)
    return response.text  # SAFE: validated
