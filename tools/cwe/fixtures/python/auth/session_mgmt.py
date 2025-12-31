"""
Session Management Fixtures

CWE-613: Insufficient Session Expiration
CVE-2020-8184: Session fixation
"""

from flask import Flask, redirect, request, session

app = Flask(__name__)


# ===================================================
# VULNERABLE: Session not invalidated (CWE-613)
# ===================================================


@app.route("/logout")
def logout_vulnerable():
    """
    ❌ HIGH: Session not cleared on logout

    CVE-2020-8184: Old session remains valid.
    """
    # Session not cleared!
    return redirect("/")


def login_session_fixation_vulnerable(username):
    """
    ❌ HIGH: Session fixation

    User-controlled session ID allows fixation attacks.
    """
    session_id = request.args.get("sid")  # User-controlled!
    session["user_id"] = username
    return session_id


# ===================================================
# SECURE: Proper session management
# ===================================================


@app.route("/logout")
def logout_secure():
    """
    ✅ SECURE: Session properly invalidated
    """
    session.clear()  # Clear all session data
    return redirect("/")


def login_secure(username):
    """
    ✅ SECURE: Session regeneration
    """
    # Clear old session
    session.clear()

    # Create new session
    session["user_id"] = username
    session.permanent = False

    return True
