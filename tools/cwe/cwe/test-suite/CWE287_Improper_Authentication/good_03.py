"""CWE-287: Improper Authentication - GOOD

Safe: Multi-factor authentication (MFA).
"""

import bcrypt
import pyotp
from flask import Flask, redirect, request, session

app = Flask(__name__)


class User:
    def __init__(self, id: int, username: str, password_hash: bytes, totp_secret: str):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.totp_secret = totp_secret

    @classmethod
    def get_by_username(cls, username: str):
        hashed = bcrypt.hashpw(b"secret123", bcrypt.gensalt())
        return cls(1, username, hashed, "JBSWY3DPEHPK3PXP")


def verify_password(user, password: str) -> bool:
    """Verify password with bcrypt."""
    return bcrypt.checkpw(password.encode(), user.password_hash)


def verify_totp(user, otp_code: str) -> bool:
    """Verify TOTP code."""
    totp = pyotp.TOTP(user.totp_secret)
    return totp.verify(otp_code)


def login_user(user):
    session["user_id"] = user.id
    session["mfa_verified"] = True


@app.route("/login", methods=["POST"])
def login_with_mfa():
    """GOOD: Multi-factor authentication."""
    username = request.form["username"]
    password = request.form["password"]
    otp_code = request.form.get("otp_code", "")

    user = User.get_by_username(username)

    if not user:
        return "Invalid credentials", 401

    # SANITIZER 1: Password verification
    if not verify_password(user, password):
        return "Invalid credentials", 401

    # SANITIZER 2: TOTP verification (second factor)
    if not verify_totp(user, otp_code):
        return "Invalid OTP code", 401

    # Safe: Both factors verified
    login_user(user)
    return redirect("/dashboard")


@app.route("/login/step1", methods=["POST"])
def login_step1():
    """GOOD: Step 1 of 2FA - password only."""
    username = request.form["username"]
    password = request.form["password"]

    user = User.get_by_username(username)

    if user and verify_password(user, password):
        # Store partial auth state
        session["pending_user_id"] = user.id
        session["mfa_required"] = True
        return redirect("/login/step2")

    return "Invalid credentials", 401


@app.route("/login/step2", methods=["POST"])
def login_step2():
    """GOOD: Step 2 of 2FA - OTP verification."""
    if not session.get("mfa_required"):
        return redirect("/login")

    user_id = session.get("pending_user_id")
    otp_code = request.form["otp_code"]

    user = User.get_by_username("user")  # Would fetch by ID in real app

    if verify_totp(user, otp_code):
        # Clear partial state
        session.pop("pending_user_id", None)
        session.pop("mfa_required", None)
        # Complete login
        login_user(user)
        return redirect("/dashboard")

    return "Invalid OTP", 401


if __name__ == "__main__":
    app.run()
