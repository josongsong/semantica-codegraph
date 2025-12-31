"""
Server-Side Request Forgery (SSRF) Test Fixtures

CWE-918: SSRF
CVE-2019-5736: Docker SSRF
CVE-2021-21295: Netty SSRF
"""

import ipaddress
from urllib.parse import urlparse

import requests

# ==================================================
# VULNERABLE: Direct URL fetch
# ==================================================


def ssrf_vulnerable_1_requests(url: str):
    """
    ❌ CRITICAL: Unvalidated URL fetch

    Real attack: url = "http://169.254.169.254/latest/meta-data/"
    Result: Accesses AWS metadata service, leaks credentials
    """
    # VULNERABLE: No URL validation
    response = requests.get(url)  # SINK: requests.get

    return response.text


def ssrf_vulnerable_2_urllib(url: str):
    """
    ❌ CRITICAL: urllib SSRF
    """
    from urllib.request import urlopen

    # VULNERABLE
    response = urlopen(url)  # SINK: urlopen

    return response.read()


def ssrf_vulnerable_3_image_fetch(image_url: str):
    """
    ❌ CRITICAL: Image proxy SSRF

    Real attack: image_url = "file:///etc/passwd"
    Result: Reads local files
    """
    # VULNERABLE: No protocol validation
    response = requests.get(image_url)  # SINK

    return response.content


# ==================================================
# VULNERABLE: URL redirection
# ==================================================


def ssrf_vulnerable_4_redirect(url: str):
    """
    ❌ CRITICAL: Following redirects to internal services

    Real attack:
        1. url = "http://attacker.com/redirect"
        2. Redirects to "http://localhost:6379/CONFIG SET dir /var/www/"
    Result: Redis exploitation
    """
    # VULNERABLE: Follows redirects
    response = requests.get(url, allow_redirects=True)  # SINK

    return response.text


def ssrf_vulnerable_5_webhook(webhook_url: str):
    """
    ❌ CRITICAL: Webhook SSRF
    """
    # VULNERABLE: User-controlled webhook
    payload = {"event": "user_created", "data": {}}

    requests.post(webhook_url, json=payload)  # SINK


# ==================================================
# VULNERABLE: DNS rebinding
# ==================================================


def ssrf_vulnerable_6_dns_rebinding(url: str):
    """
    ❌ CRITICAL: DNS rebinding attack

    Real attack:
        1. attacker.com initially resolves to 1.2.3.4 (public IP)
        2. Validation passes
        3. DNS changes to 127.0.0.1
        4. Request goes to localhost
    """
    # VULNERABLE: Time-of-check time-of-use
    parsed = urlparse(url)

    # Check hostname (TOCTOU vulnerability)
    if parsed.hostname == "localhost":
        raise ValueError("Localhost not allowed")

    # SINK: DNS can change between check and use
    response = requests.get(url)

    return response.text


# ==================================================
# SAFE: URL allowlist (BEST PRACTICE)
# ==================================================


def ssrf_safe_1_allowlist(url: str):
    """
    ✅ SECURE: Allowlist of domains
    """
    ALLOWED_DOMAINS = {"api.example.com", "cdn.example.com", "images.example.com"}

    parsed = urlparse(url)

    # SAFE: Allowlist check
    if parsed.hostname not in ALLOWED_DOMAINS:
        raise ValueError("Domain not allowed")

    # Additional checks
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Invalid protocol")

    response = requests.get(url, timeout=5)

    return response.text


def ssrf_safe_2_protocol_validation(url: str):
    """
    ✅ SECURE: Protocol validation
    """
    parsed = urlparse(url)

    # SAFE: Only allow HTTP/HTTPS
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only HTTP/HTTPS allowed")

    # Block private IPs
    if is_private_ip(parsed.hostname):
        raise ValueError("Private IP not allowed")

    response = requests.get(url, timeout=5)

    return response.text


# ==================================================
# SAFE: IP address validation
# ==================================================


def ssrf_safe_3_ip_blocklist(url: str):
    """
    ✅ SECURE: Block private/internal IPs
    """
    parsed = urlparse(url)

    # Resolve hostname to IP
    import socket

    try:
        ip = socket.gethostbyname(parsed.hostname)
    except socket.gaierror:
        raise ValueError("Invalid hostname")

    # SAFE: Block private IPs
    ip_obj = ipaddress.ip_address(ip)

    if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
        raise ValueError("Private IP not allowed")

    # Block cloud metadata IPs
    BLOCKED_IPS = {
        "169.254.169.254",  # AWS/Azure/GCP metadata
        "fd00:ec2::254",  # AWS IPv6 metadata
    }

    if ip in BLOCKED_IPS:
        raise ValueError("Blocked IP")

    response = requests.get(url, timeout=5)

    return response.text


def ssrf_safe_4_cidr_blocklist(url: str):
    """
    ✅ SECURE: CIDR range blocking
    """
    import socket

    parsed = urlparse(url)

    # Resolve IP
    ip = socket.gethostbyname(parsed.hostname)
    ip_obj = ipaddress.ip_address(ip)

    # SAFE: Block private ranges
    BLOCKED_RANGES = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("169.254.0.0/16"),  # Link-local
        ipaddress.ip_network("::1/128"),  # IPv6 loopback
        ipaddress.ip_network("fc00::/7"),  # IPv6 private
    ]

    for blocked_range in BLOCKED_RANGES:
        if ip_obj in blocked_range:
            raise ValueError("IP in blocked range")

    response = requests.get(url, timeout=5)

    return response.text


# ==================================================
# SAFE: Disable redirects
# ==================================================


def ssrf_safe_5_no_redirects(url: str):
    """
    ✅ SECURE: Disable redirect following
    """
    # Validate URL
    if not is_safe_url(url):
        raise ValueError("Invalid URL")

    # SAFE: Disable redirects
    response = requests.get(url, allow_redirects=False, timeout=5)

    # Check for redirect
    if response.is_redirect:
        raise ValueError("Redirects not allowed")

    return response.text


def ssrf_safe_6_validate_redirect(url: str):
    """
    ✅ SECURE: Validate redirect targets
    """
    # Initial request without following redirects
    response = requests.get(url, allow_redirects=False, timeout=5)

    # If redirect, validate target
    if response.is_redirect:
        redirect_url = response.headers.get("Location")

        # SAFE: Validate redirect target
        if not is_safe_url(redirect_url):
            raise ValueError("Unsafe redirect target")

        # Follow redirect manually
        response = requests.get(redirect_url, allow_redirects=False, timeout=5)

    return response.text


# ==================================================
# SAFE: Network isolation
# ==================================================


def ssrf_safe_7_proxy(url: str):
    """
    ✅ SECURE: Use egress proxy

    Defense in depth: Route through proxy that blocks internal IPs
    """
    # SAFE: Proxy filters internal requests
    proxies = {"http": "http://egress-proxy:8080", "https": "http://egress-proxy:8080"}

    response = requests.get(url, proxies=proxies, timeout=5)

    return response.text


def ssrf_safe_8_network_policy():
    """
    ✅ SECURE: Network policy (infrastructure level)

    Use Kubernetes NetworkPolicy or AWS Security Groups
    to block internal network access from application pods.
    """
    # Infrastructure-level protection
    network_policy = """
    apiVersion: networking.k8s.io/v1
    kind: NetworkPolicy
    metadata:
      name: deny-internal
    spec:
      podSelector:
        matchLabels:
          app: web
      policyTypes:
      - Egress
      egress:
      - to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
            - 10.0.0.0/8
            - 172.16.0.0/12
            - 192.168.0.0/16
            - 169.254.169.254/32
    """
    return network_policy


# ==================================================
# SAFE: Content-type validation
# ==================================================


def ssrf_safe_9_content_type(url: str):
    """
    ✅ SECURE: Validate response content type
    """
    if not is_safe_url(url):
        raise ValueError("Invalid URL")

    response = requests.get(url, timeout=5, stream=True)

    # SAFE: Check Content-Type before reading
    content_type = response.headers.get("Content-Type", "")

    ALLOWED_TYPES = {"application/json", "application/xml", "text/plain"}

    if not any(ct in content_type for ct in ALLOWED_TYPES):
        raise ValueError("Invalid content type")

    # Limit response size
    MAX_SIZE = 1024 * 1024  # 1MB
    content = response.raw.read(MAX_SIZE + 1)

    if len(content) > MAX_SIZE:
        raise ValueError("Response too large")

    return content


# ==================================================
# SAFE: Timeout and limits
# ==================================================


def ssrf_safe_10_limits(url: str):
    """
    ✅ SECURE: Timeouts and size limits
    """
    if not is_safe_url(url):
        raise ValueError("Invalid URL")

    # SAFE: Multiple safeguards
    response = requests.get(
        url,
        timeout=5,  # Connection timeout
        allow_redirects=False,  # No redirects
        stream=True,  # Stream for size control
    )

    # Limit response size
    MAX_SIZE = 10 * 1024 * 1024  # 10MB
    content = b""

    for chunk in response.iter_content(chunk_size=8192):
        content += chunk
        if len(content) > MAX_SIZE:
            raise ValueError("Response too large")

    return content


# ==================================================
# Helper functions
# ==================================================


def is_private_ip(hostname: str) -> bool:
    """Check if hostname resolves to private IP"""
    import socket

    try:
        ip = socket.gethostbyname(hostname)
        ip_obj = ipaddress.ip_address(ip)

        return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip == "169.254.169.254"
    except (socket.gaierror, ValueError):
        return True  # Fail closed


def is_safe_url(url: str) -> bool:
    """Comprehensive URL validation"""
    parsed = urlparse(url)

    # Check scheme
    if parsed.scheme not in ("http", "https"):
        return False

    # Check for private IPs
    if is_private_ip(parsed.hostname):
        return False

    # Check for suspicious patterns
    if "@" in url:  # URL with credentials
        return False

    return True
