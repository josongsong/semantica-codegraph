"""
OAuth/SAML Vulnerability Fixtures

CVE-2016-5697: OAuth redirect_uri bypass
CVE-2017-11427: SAML signature bypass
"""

from flask import Flask, redirect, request

app = Flask(__name__)


# ===================================================
# VULNERABLE: OAuth redirect_uri not validated
# ===================================================


@app.route("/oauth/callback")
def oauth_callback_vulnerable():
    """
    ❌ CRITICAL: Open redirect via redirect_uri

    CVE-2016-5697: Attacker can steal tokens via redirect.
    """
    redirect_uri = request.args.get("redirect_uri")
    access_token = generate_token()

    # No validation!
    return redirect(f"{redirect_uri}?access_token={access_token}")


def parse_saml_vulnerable(saml_response):
    """
    ❌ CRITICAL: SAML signature not verified

    CVE-2017-11427: Attacker can forge SAML responses.
    """
    # No signature verification!
    user_data = decode_saml(saml_response)
    return user_data


# ===================================================
# SECURE: Proper OAuth/SAML validation
# ===================================================

ALLOWED_REDIRECTS = ["https://app.example.com", "https://api.example.com"]


@app.route("/oauth/callback")
def oauth_callback_secure():
    """
    ✅ SECURE: Redirect URI validated
    """
    redirect_uri = request.args.get("redirect_uri")

    # Validate redirect_uri
    if redirect_uri not in ALLOWED_REDIRECTS:
        return "Invalid redirect_uri", 400

    generate_token()

    # Don't put token in URL!
    return redirect(redirect_uri)


def parse_saml_secure(saml_response):
    """
    ✅ SECURE: SAML signature verified
    """
    # Verify signature
    if not verify_saml_signature(saml_response):
        raise ValueError("Invalid SAML signature")

    user_data = decode_saml(saml_response)
    return user_data


# Mock functions
def generate_token():
    return "token123"


def decode_saml(response):
    return {"user": "test"}


def verify_saml_signature(response):
    return True
