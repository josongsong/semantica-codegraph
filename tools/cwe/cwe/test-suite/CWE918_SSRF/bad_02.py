"""CWE-918: SSRF via urllib - BAD"""

import urllib.request

from flask import request


def proxy_request():
    target_url = request.args.get("target")  # SOURCE: request param

    # BAD: Direct URL open
    response = urllib.request.urlopen(target_url)  # SINK: SSRF
    return response.read()
