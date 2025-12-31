"""CWE-287: Improper Authentication - BAD

Vulnerable: No password verification before login.
"""

from flask import Flask, redirect, request, session

app = Flask(__name__)


class User:
    def __init__(self, id: int, username: str, password_hash: str):
        self.id = id
        self.username = username
        self.password_hash = password_hash

    @classmethod
    def query_filter_by(cls, **kwargs):
        return cls(1, kwargs.get("username", "user"), "hashed_password")


def login_user(user):
    """Set user session."""
    session["user_id"] = user.id


@app.route("/login", methods=["POST"])
def login():
    """BAD: No password verification."""
    username = request.form["username"]  # SOURCE
    password = request.form["password"]  # SOURCE (unused!)

    user = User.query_filter_by(username=username)

    if user:  # BAD: Only checking if user exists, not password!
        login_user(user)  # SINK: Session created without authentication
        return redirect("/dashboard")

    return "User not found", 401


@app.route("/api/login", methods=["POST"])
def api_login():
    """BAD: Returns success without any credential check."""
    data = request.json
    username = data.get("username")  # SOURCE

    user = User.query_filter_by(username=username)
    if user:
        # VULNERABILITY: No password check at all
        return {"token": "fake_token", "user_id": user.id}

    return {"error": "User not found"}, 401


if __name__ == "__main__":
    app.run()
