"""CWE-287: Improper Authentication - GOOD

Safe: Proper password verification with bcrypt.
"""

import bcrypt
from flask import Flask, redirect, request, session

app = Flask(__name__)


class User:
    def __init__(self, id: int, username: str, password_hash: bytes):
        self.id = id
        self.username = username
        self.password_hash = password_hash

    @classmethod
    def get_by_username(cls, username: str):
        # Mock: returns user with bcrypt-hashed password
        hashed = bcrypt.hashpw(b"secret123", bcrypt.gensalt())
        return cls(1, username, hashed)


def login_user(user):
    session["user_id"] = user.id


@app.route("/login", methods=["POST"])
def login():
    """GOOD: Proper bcrypt password verification."""
    username = request.form["username"]
    password = request.form["password"]

    user = User.get_by_username(username)

    if user:
        # SANITIZER: Proper password verification with bcrypt
        if bcrypt.checkpw(password.encode("utf-8"), user.password_hash):
            login_user(user)  # Safe: Only after verification
            return redirect("/dashboard")

    return "Invalid credentials", 401


@app.route("/login/v2", methods=["POST"])
def login_with_rate_limit():
    """GOOD: With rate limiting."""
    username = request.form["username"]
    password = request.form["password"]

    # Additional protection: rate limiting
    if is_rate_limited(username):
        return "Too many attempts", 429

    user = User.get_by_username(username)

    if user and bcrypt.checkpw(password.encode(), user.password_hash):
        reset_rate_limit(username)
        login_user(user)
        return redirect("/dashboard")

    increment_failed_attempts(username)
    return "Invalid credentials", 401


def is_rate_limited(username: str) -> bool:
    return False


def reset_rate_limit(username: str):
    pass


def increment_failed_attempts(username: str):
    pass


if __name__ == "__main__":
    app.run()
