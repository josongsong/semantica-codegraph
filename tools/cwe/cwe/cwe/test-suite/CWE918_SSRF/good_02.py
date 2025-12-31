"""CWE-918: SSRF - GOOD (IP validation)"""

import ipaddress
import socket
import urllib.request
from urllib.parse import urlparse

from flask import abort, request


def is_internal_ip(hostname: str) -> bool:
    """Check if hostname resolves to internal IP"""
    try:
        ip = socket.gethostbyname(hostname)
        return ipaddress.ip_address(ip).is_private
    except socket.gaierror:
        return True  # Fail closed


def proxy_request():
    target_url = request.args.get("target")
    parsed = urlparse(target_url)

    # GOOD: Block internal IPs
    if is_internal_ip(parsed.hostname):
        abort(403, "Internal hosts not allowed")

    response = urllib.request.urlopen(target_url)
    return response.read()
