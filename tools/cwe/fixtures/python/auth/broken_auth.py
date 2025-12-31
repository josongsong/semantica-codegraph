"""
Broken Authentication Fixtures

CWE-287: Improper Authentication
CVE-2021-21972: VMware auth bypass
"""

from flask import Flask

app = Flask(__name__)


# ===================================================
# VULNERABLE: Missing authentication (CWE-287)
# ===================================================


@app.route("/admin")
def admin_panel_vulnerable():
    """
    ❌ CRITICAL: No authentication check

    CVE-2021-21972: Missing auth allows unauthorized access.
    """
    return "Admin Panel - Sensitive Data"


@app.route("/delete_user/<user_id>")
def delete_user_vulnerable(user_id):
    """
    ❌ CRITICAL: Critical action without auth
    """
    # No auth check!
    return f"User {user_id} deleted"


# ===================================================
# SECURE: Proper authentication
# ===================================================


def login_required(f):
    """Auth decorator"""

    def wrapper(*args, **kwargs):
        # Check authentication
        return f(*args, **kwargs)

    return wrapper


@app.route("/admin")
@login_required
def admin_panel_secure():
    """
    ✅ SECURE: Authentication required
    """
    return "Admin Panel - Authorized"
